"""Deterministic guardrails: PII masking, prompt injection check and citation verification."""

import re

from incident_assistant.models import EvidenceItem, InvestigationReport

IBAN = re.compile(r"\bTR\d{2}(?:[ ]?\d{4}){5}[ ]?\d{2}\b")
CARD = re.compile(r"\b(?:\d{4}[ -]?){3}\d{4}\b")
TCKN = re.compile(r"\b[1-9]\d{10}\b")
PHONE = re.compile(r"\b0?5\d{2}[ -]?\d{3}[ -]?\d{2}[ -]?\d{2}\b")
EMAIL = re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.]+\b")

INJECTION_PATTERNS = [
    r"ignore (all |the )?(previous|above) instructions",
    r"disregard (your|the) (rules|instructions)",
    r"(reveal|print|show) (your|the) system prompt",
    r"you are now",
    r"act as (an? )?(admin|developer|dan)",
]


def _mask_keep_last4(match: re.Match) -> str:
    """Replace digits with '*' except the last four, keeping spaces so the input format stays visible."""
    text = match.group(0)
    digits_seen, total = 0, sum(c.isdigit() for c in text)
    masked = []
    for c in text:
        if c.isdigit():
            digits_seen += 1
            masked.append(c if digits_seen > total - 4 else "*")
        else:
            masked.append(c)
    return "".join(masked)


def mask_pii(text: str) -> str:
    text = IBAN.sub(_mask_keep_last4, text)
    text = CARD.sub(_mask_keep_last4, text)
    text = TCKN.sub("[TCKN]", text)
    text = PHONE.sub("[PHONE]", text)
    return EMAIL.sub("[EMAIL]", text)


def detect_injection(text: str) -> str | None:
    lowered = text.lower()
    for pattern in INJECTION_PATTERNS:
        if re.search(pattern, lowered):
            return f"Possible prompt injection detected (pattern: '{pattern}')."
    return None


def _normalize_ref(ref: str) -> str:
    # The model sometimes cites line ranges ("File.java:19-27"); keep the first line.
    return re.sub(r"(:\d+)-\d+$", r"\1", ref.strip().strip("`"))


LOWER_CONFIDENCE = {"high": "medium", "medium": "low", "low": "low"}


def verify_citations(report: InvestigationReport, evidence: list[EvidenceItem]) -> InvestigationReport:
    """Keep only findings backed by evidence the tools actually returned (checker step)."""
    known = {item.ref for item in evidence}
    notes, findings = [], []

    for finding in report.findings:
        refs = [_normalize_ref(r) for r in finding.evidence_refs]
        valid = [r for r in refs if r in known]
        for ref in set(refs) - set(valid):
            notes.append(f"Removed citation not found in collected evidence: {ref}")
        if valid:
            findings.append(finding.model_copy(update={"evidence_refs": valid}))
        else:
            notes.append(f"Dropped unsupported finding: {finding.statement}")

    code_files = {ref.split(":")[1] for ref in known if ref.startswith("code:")}
    affected = [f for f in report.affected_files if f and (f in code_files or any(c.endswith(f) for c in code_files))]

    update = {"findings": findings, "affected_files": affected, "verification_notes": notes}
    if report.status == "needs_clarification":
        pass
    elif not findings:
        update |= {"status": "insufficient_evidence", "confidence": "low"}
        notes.append("No finding is supported by collected evidence.")
    elif notes:
        update["confidence"] = LOWER_CONFIDENCE[report.confidence]

    verified = report.model_copy(update=update)
    for field in ("summary", "root_cause", "suggested_fix"):
        setattr(verified, field, mask_pii(getattr(verified, field)))
    return verified
