"""Run the incident assistant from the terminal.

    python cli.py INC-1001
    python cli.py INC-1001 --ask "Which other channels are affected?"
    python cli.py --all
"""

import argparse
import asyncio
import json
import time
import uuid

from incident_assistant.config import INCIDENTS_DIR, RUNTIME_DIR
from incident_assistant.graph import ask_followup, investigate_incident, tool_trace
from incident_assistant.models import Incident


def load_incident(incident_id: str) -> Incident:
    return Incident.model_validate_json((INCIDENTS_DIR / f"{incident_id}.json").read_text())


def print_result(state: dict, seconds: float) -> None:
    print(f"\n=== {state['incident'].id} ({seconds:.0f}s) ===")
    if state.get("blocked_reason"):
        print("BLOCKED:", state["blocked_reason"])
        return
    print("Plan:", *state["triage"].plan, sep="\n  - ")
    print("Tool calls:")
    for step in tool_trace(state):
        print(f"  {step['tool']}({json.dumps(step['args'])}) -> ok={step['ok']} results={step['results']}")
    print(state["report"].model_dump_json(indent=2))


async def run(incident_id: str, question: str | None) -> dict:
    thread_id = f"{incident_id}-{uuid.uuid4().hex[:6]}"
    started = time.time()
    state = await investigate_incident(load_incident(incident_id), thread_id)
    print_result(state, time.time() - started)
    if question and state.get("report"):
        print("\nQ:", question)
        print("A:", await ask_followup(thread_id, question))
    return state


async def run_all() -> None:
    RUNTIME_DIR.mkdir(exist_ok=True)
    summary = {}
    for file in sorted(INCIDENTS_DIR.glob("*.json")):
        state = await run(file.stem, None)
        report = state.get("report")
        summary[file.stem] = {
            "status": report.status if report else "blocked",
            "confidence": report.confidence if report else None,
            "tool_calls": len(tool_trace(state)),
            "report": report.model_dump() if report else None,
        }
    (RUNTIME_DIR / "evaluation.json").write_text(json.dumps(summary, indent=2))
    print("\nSummary:", json.dumps({k: (v["status"], v["confidence"]) for k, v in summary.items()}, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("incident_id", nargs="?")
    parser.add_argument("--ask", help="follow-up question on the same thread")
    parser.add_argument("--all", action="store_true", help="run every incident in data/incidents")
    args = parser.parse_args()
    asyncio.run(run_all() if args.all else run(args.incident_id, args.ask))
