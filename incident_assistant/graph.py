"""LangGraph workflow: guard_input -> triage -> prefetch -> investigate <-> tools -> report -> verify.

triage plans (planner), investigate calls MCP tools in a loop (executor), verify checks citations (checker).
A follow-up question on the same thread is answered from the stored report and evidence (memory).
"""

import json
import re
from typing import Annotated, TypedDict

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_ollama import ChatOllama
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode

from incident_assistant import prompts
from incident_assistant.config import CHAT_MODEL, MAX_TOOL_CALLS, OLLAMA_URL
from incident_assistant.guards import detect_injection, mask_pii, verify_citations
from incident_assistant.mcp_client import mcp_tools
from incident_assistant.models import EvidenceItem, Incident, InvestigationReport, TriageResult

ERROR_CODE = re.compile(r"\b[A-Z]{3}-\d{4}\b")
TRANSACTION_ID = re.compile(r"\bTX-\d{8}-\d{4}\b")

STATE_TYPES = ["Incident", "TriageResult", "EvidenceItem", "Finding", "InvestigationReport"]
CHECKPOINTER = InMemorySaver(
    serde=JsonPlusSerializer(allowed_msgpack_modules=[("incident_assistant.models", name) for name in STATE_TYPES])
)


class State(TypedDict, total=False):
    incident: Incident
    incident_text: str
    identifiers: dict
    blocked_reason: str | None
    triage: TriageResult
    evidence: list[EvidenceItem]
    messages: Annotated[list, add_messages]
    tool_calls: int
    report: InvestigationReport
    question: str | None
    followups: list[dict]


def llm() -> ChatOllama:
    return ChatOllama(model=CHAT_MODEL, base_url=OLLAMA_URL, temperature=0, reasoning=False)


def render_incident(incident: Incident) -> str:
    fields = incident.model_dump(exclude_none=True)
    return "\n".join(f"{key}: {value}" for key, value in fields.items())


def extract_identifiers(incident: Incident) -> dict:
    text = f"{incident.screen_message or ''} {incident.description}"
    transaction_ids = set(TRANSACTION_ID.findall(text)) | ({incident.transaction_id} if incident.transaction_id else set())
    return {
        "error_codes": sorted(set(ERROR_CODE.findall(text))),
        "transaction_ids": sorted(transaction_ids),
        "customer_id": incident.customer_id,
        "date": incident.reported_at[:10],
    }


def parse_tool_output(content) -> dict:
    """MCP tool results arrive as a JSON string or a list of text blocks."""
    if isinstance(content, list):
        content = "".join(block.get("text", "") for block in content if isinstance(block, dict))
    try:
        return json.loads(content)
    except (TypeError, json.JSONDecodeError):
        return {"ok": False, "results": [], "error": str(content)}


def evidence_from(result: dict) -> list[EvidenceItem]:
    return [EvidenceItem(ref=r["ref"], text=str(r["text"])[:300]) for r in result.get("results", [])]


def collect_evidence(state: State) -> list[EvidenceItem]:
    items = list(state.get("evidence", []))
    for message in state.get("messages", []):
        if isinstance(message, ToolMessage):
            items += evidence_from(parse_tool_output(message.content))
    return list({item.ref: item for item in items}.values())


def format_evidence(items: list[EvidenceItem]) -> str:
    return "\n".join(f"{item.ref} | {item.text}" for item in items) or "(no evidence)"


def build_graph(tools: list):
    tools_by_name = {tool.name: tool for tool in tools}
    tool_node = ToolNode(tools, handle_tool_errors=True)

    def guard_input(state: State) -> dict:
        text = render_incident(state["incident"])
        return {
            "blocked_reason": detect_injection(text),
            "incident_text": mask_pii(text),
            "identifiers": extract_identifiers(state["incident"]),
        }

    async def triage(state: State) -> dict:
        prompt = prompts.TRIAGE.format(incident=state["incident_text"], identifiers=state["identifiers"])
        result: TriageResult = await llm().with_structured_output(TriageResult).ainvoke(prompt)
        ids = state["identifiers"]
        if ids["error_codes"] or ids["transaction_ids"] or ids["customer_id"]:
            return {"triage": result}
        # Nothing to search for: ask the branch instead of guessing.
        questions = result.clarifying_questions or [
            "Which screen or transaction failed?",
            "What error code or message was shown?",
            "Which customer or transaction id is affected?",
        ]
        report = InvestigationReport(
            status="needs_clarification",
            summary="The incident does not contain an error code, transaction id or customer id to investigate.",
            root_cause="Not investigated.",
            findings=[],
            suggested_fix="",
            confidence="low",
            open_questions=questions,
        )
        return {"triage": result, "report": report}

    async def prefetch(state: State) -> dict:
        """Deterministic first step: look up known error codes and transactions before the agent loop."""
        ids, evidence, facts = state["identifiers"], [], []
        calls = [("lookup_error_code", {"code": c}) for c in ids["error_codes"]]
        calls += [("get_transaction", {"transaction_id": t}) for t in ids["transaction_ids"]]
        for name, args in calls:
            result = parse_tool_output(await tools_by_name[name].ainvoke(args))
            evidence += evidence_from(result)
            facts.append(f"{name}({args}) -> {json.dumps(result)[:800]}")
        plan = "\n".join(f"- {step}" for step in state["triage"].plan)
        human = prompts.INVESTIGATE_INPUT.format(
            incident=state["incident_text"], plan=plan, facts="\n".join(facts) or "(none)"
        )
        return {
            "evidence": evidence,
            "tool_calls": 0,
            "messages": [SystemMessage(prompts.INVESTIGATE), HumanMessage(human)],
        }

    async def investigate(state: State) -> dict:
        response = await llm().bind_tools(tools).ainvoke(state["messages"])
        return {"messages": [response]}

    async def run_tools(state: State) -> dict:
        result = await tool_node.ainvoke(state)
        return {"messages": result["messages"], "tool_calls": state["tool_calls"] + len(result["messages"])}

    async def report(state: State) -> dict:
        evidence = collect_evidence(state)
        last = state["messages"][-1]
        notes = last.content if isinstance(last, AIMessage) and not last.tool_calls else "(tool budget reached)"
        prompt = prompts.REPORT.format(
            incident=state["incident_text"], notes=notes, evidence=format_evidence(evidence)
        )
        structured = llm().with_structured_output(InvestigationReport)
        for _ in range(2):  # one retry for malformed structured output
            try:
                return {"report": await structured.ainvoke(prompt)}
            except Exception as error:  # noqa: BLE001 - model output errors vary by provider
                notes = f"Previous attempt failed: {error}"
        return {
            "report": InvestigationReport(
                status="insufficient_evidence",
                summary="The model could not produce a valid report.",
                root_cause="Not determined.",
                findings=[],
                suggested_fix="",
                confidence="low",
                open_questions=["Re-run the investigation."],
            )
        }

    def verify(state: State) -> dict:
        return {"report": verify_citations(state["report"], collect_evidence(state))}

    async def followup(state: State) -> dict:
        if blocked := detect_injection(state["question"]):
            answer = f"Question rejected by input guard: {blocked}"
            return {"followups": state.get("followups", []) + [{"question": state["question"], "answer": answer}]}
        history = "\n".join(f"Q: {f['question']}\nA: {f['answer']}" for f in state.get("followups", []))
        prompt = prompts.FOLLOWUP.format(
            report=state["report"].model_dump_json(indent=2),
            evidence=format_evidence(collect_evidence(state)),
            history=history or "(none)",
            question=mask_pii(state["question"]),
        )
        answer = mask_pii((await llm().ainvoke(prompt)).content)
        return {"followups": state.get("followups", []) + [{"question": state["question"], "answer": answer}]}

    def route_start(state: State) -> str:
        return "followup" if state.get("question") and state.get("report") else "guard_input"

    def route_after_guard(state: State) -> str:
        return END if state["blocked_reason"] else "triage"

    def route_after_triage(state: State) -> str:
        return END if state.get("report") else "prefetch"

    def route_after_investigate(state: State) -> str:
        last = state["messages"][-1]
        # A batch that would exceed the budget is not executed; the report is written from what was collected.
        if last.tool_calls and state["tool_calls"] + len(last.tool_calls) <= MAX_TOOL_CALLS:
            return "tools"
        return "report"

    graph = StateGraph(State)
    graph.add_node("guard_input", guard_input)
    graph.add_node("triage", triage)
    graph.add_node("prefetch", prefetch)
    graph.add_node("investigate", investigate)
    graph.add_node("tools", run_tools)
    graph.add_node("report", report)
    graph.add_node("verify", verify)
    graph.add_node("followup", followup)

    graph.add_conditional_edges(START, route_start, ["guard_input", "followup"])
    graph.add_conditional_edges("guard_input", route_after_guard, ["triage", END])
    graph.add_conditional_edges("triage", route_after_triage, ["prefetch", END])
    graph.add_edge("prefetch", "investigate")
    graph.add_conditional_edges("investigate", route_after_investigate, ["tools", "report"])
    graph.add_edge("tools", "investigate")
    graph.add_edge("report", "verify")
    graph.add_edge("verify", END)
    graph.add_edge("followup", END)
    return graph.compile(checkpointer=CHECKPOINTER)


def tool_trace(state: State) -> list[dict]:
    """Tool calls made by the agent, for display in the UI and CLI."""
    results = {m.tool_call_id: parse_tool_output(m.content) for m in state.get("messages", []) if isinstance(m, ToolMessage)}
    trace = []
    for message in state.get("messages", []):
        for call in getattr(message, "tool_calls", None) or []:
            result = results.get(call["id"], {"ok": False, "error": "Not executed: tool call budget reached."})
            trace.append({
                "tool": call["name"],
                "args": call["args"],
                "ok": result.get("ok", False),
                "results": len(result.get("results", [])),
                "error": result.get("error"),
            })
    return trace


async def investigate_incident(incident: Incident, thread_id: str) -> State:
    async with mcp_tools() as tools:
        graph = build_graph(tools)
        config = {"configurable": {"thread_id": thread_id}, "recursion_limit": 4 * MAX_TOOL_CALLS + 20}
        return await graph.ainvoke({"incident": incident, "question": None}, config)


async def ask_followup(thread_id: str, question: str) -> str:
    async with mcp_tools() as tools:
        graph = build_graph(tools)
        state = await graph.ainvoke({"question": question}, {"configurable": {"thread_id": thread_id}})
        return state["followups"][-1]["answer"]
