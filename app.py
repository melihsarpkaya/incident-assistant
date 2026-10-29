"""Streamlit UI. Run: streamlit run app.py"""

import asyncio
import json
import uuid
from datetime import datetime

import httpx
import streamlit as st

from incident_assistant.config import CHAT_MODEL, INCIDENTS_DIR, OLLAMA_URL
from incident_assistant.guards import mask_pii
from incident_assistant.graph import ask_followup, collect_evidence, investigate_incident, tool_trace
from incident_assistant.models import Incident

STATUS_STYLE = {
    "root_cause_identified": ("Root cause identified", "green"),
    "probable_cause": ("Probable cause", "orange"),
    "insufficient_evidence": ("Insufficient evidence", "gray"),
    "needs_clarification": ("Needs clarification", "blue"),
}

st.set_page_config(page_title="Branch Incident Assistant", page_icon="🏦", layout="wide")


def ollama_ready() -> bool:
    try:
        return httpx.get(f"{OLLAMA_URL}/api/tags", timeout=2).is_success
    except httpx.HTTPError:
        return False


def sample_incidents() -> dict[str, Incident]:
    files = sorted(INCIDENTS_DIR.glob("*.json"))
    return {f.stem: Incident.model_validate_json(f.read_text()) for f in files}


def custom_incident(text: str) -> Incident:
    return Incident(
        id=f"CUSTOM-{uuid.uuid4().hex[:4].upper()}",
        branch="Custom input",
        reported_at=datetime.now().isoformat(timespec="seconds"),
        channel="BRANCH",
        description=text,
    )


with st.sidebar:
    st.header("Branch incident")
    incidents = sample_incidents()
    choice = st.selectbox("Incident", [*incidents, "Custom incident"])
    if choice == "Custom incident":
        text = st.text_area("Describe the problem", height=160)
        incident = custom_incident(text) if text.strip() else None
    else:
        incident = incidents[choice]
        st.markdown(f"**{incident.branch}** · {incident.reported_at}")
        if incident.screen_message:
            st.markdown(f"Screen: `{incident.screen_message}`")
        st.caption(mask_pii(incident.description))
    start = st.button("Investigate", type="primary", disabled=incident is None, width="stretch")
    st.divider()
    st.caption(f"Model: `{CHAT_MODEL}`")
    st.caption("Ollama: " + ("🟢 reachable" if ollama_ready() else "🔴 not reachable"))

st.title("🏦 Branch Incident Assistant")
st.caption("Investigates branch incidents across logs, source code, transactions and service documentation through MCP tools.")

if start:
    thread_id = f"{incident.id}-{uuid.uuid4().hex[:6]}"
    with st.spinner("Investigating... (local model, this can take a minute)"):
        try:
            st.session_state.result = asyncio.run(investigate_incident(incident, thread_id))
            st.session_state.thread_id = thread_id
            st.session_state.chat = []
        except Exception as error:  # noqa: BLE001 - surface any runtime failure to the user
            st.session_state.result = None
            st.error(f"{type(error).__name__}: {error}. Is Ollama running and was `python ingest.py` executed?")

state = st.session_state.get("result")
if not state:
    st.info("Select an incident and press **Investigate**.")
    st.stop()

if state.get("blocked_reason"):
    st.error(f"Incident rejected by input guard: {state['blocked_reason']}")
    st.stop()

report = state["report"]
evidence = {item.ref: item.text for item in collect_evidence(state)}
label, color = STATUS_STYLE[report.status]

left, right = st.columns([3, 2], gap="large")

with left:
    st.subheader(f"Report · {state['incident'].id}")
    st.markdown(f":{color}-badge[{label}] :violet-badge[Confidence: {report.confidence}]")
    st.markdown(f"**Summary.** {report.summary}")
    st.markdown(f"**Root cause.** {report.root_cause}")
    if report.findings:
        st.markdown("**Findings**")
        for number, finding in enumerate(report.findings, start=1):
            st.markdown(f"{number}. {finding.statement}")
            for ref in finding.evidence_refs:
                with st.expander(f"`{ref}`"):
                    st.code(evidence.get(ref, ""), language=None, wrap_lines=True)
    if report.suggested_fix:
        st.markdown("**Suggested fix**")
        st.success(report.suggested_fix)
    if report.affected_files:
        st.markdown("**Affected files:** " + ", ".join(f"`{f}`" for f in report.affected_files))
    if report.open_questions:
        st.markdown("**Open questions**")
        st.markdown("\n".join(f"- {q}" for q in report.open_questions))
    if report.verification_notes:
        with st.expander("Verification notes (checker step)"):
            st.markdown("\n".join(f"- {n}" for n in report.verification_notes))

with right:
    st.subheader("Investigation")
    st.markdown("**Incident (after PII masking)**")
    st.text(state["incident_text"])
    st.markdown("**Plan (triage)**")
    st.markdown("\n".join(f"{i}. {step}" for i, step in enumerate(state["triage"].plan, start=1)))
    trace = tool_trace(state)
    st.markdown(f"**MCP tool calls ({len(trace)})**")
    for step in trace:
        icon = "✅" if step["ok"] else "⚠️"
        st.markdown(f"{icon} `{step['tool']}` `{json.dumps(step['args'])}` → {step['results']} results")
        if step["error"]:
            st.caption(step["error"])
    with st.expander(f"Collected evidence ({len(evidence)})"):
        st.dataframe([{"ref": ref, "text": text} for ref, text in evidence.items()], hide_index=True)

st.divider()
st.subheader("Follow-up questions")
for message in st.session_state.get("chat", []):
    st.chat_message(message["role"]).markdown(message["content"])

if question := st.chat_input("Ask about this investigation, e.g. 'Which other channels can be affected?'"):
    st.chat_message("user").markdown(question)
    with st.spinner("Thinking..."):
        answer = asyncio.run(ask_followup(st.session_state.thread_id, question))
    st.chat_message("assistant").markdown(answer)
    st.session_state.chat += [{"role": "user", "content": question}, {"role": "assistant", "content": answer}]
