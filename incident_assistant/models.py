from typing import Literal

from pydantic import BaseModel, Field


class Incident(BaseModel):
    id: str
    branch: str
    reported_at: str
    channel: str
    description: str
    customer_id: str | None = None
    transaction_id: str | None = None
    screen_message: str | None = None


class TriageResult(BaseModel):
    """Produced by the LLM in the triage step (planner)."""

    category: Literal["transfer", "card", "account", "unknown"]
    service: str | None = Field(None, description="eft-service, card-service or null if unknown")
    plan: list[str] = Field(description="2-5 short investigation steps")
    clarifying_questions: list[str] = Field(
        default_factory=list, description="Questions for the branch if the incident lacks details"
    )


class EvidenceItem(BaseModel):
    ref: str
    text: str


class Finding(BaseModel):
    statement: str
    evidence_refs: list[str] = Field(description="Refs copied exactly from the evidence list")


class InvestigationReport(BaseModel):
    status: Literal["root_cause_identified", "probable_cause", "insufficient_evidence", "needs_clarification"]
    summary: str
    root_cause: str
    findings: list[Finding]
    suggested_fix: str
    affected_files: list[str] = Field(default_factory=list)
    confidence: Literal["high", "medium", "low"]
    open_questions: list[str] = Field(default_factory=list)
    verification_notes: list[str] = Field(default_factory=list, description="Filled by the verify step, not the LLM")
