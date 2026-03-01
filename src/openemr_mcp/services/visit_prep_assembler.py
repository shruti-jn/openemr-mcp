"""Assembler: build VisitPrepBrief from collectors + rules. Verifier failure => deterministic fallback."""
from typing import List, Tuple

from openemr_mcp.schemas import (
    Abstention,
    EvidenceStore,
    VisitPrepBrief,
    VisitPrepSection,
)
from openemr_mcp.services.visit_prep_rules import evaluate_visit_prep_rules
from openemr_mcp.services.visit_prep_verifier import verify_brief


def _empty_section() -> VisitPrepSection:
    return VisitPrepSection(claims=[], abstentions=[])


def fallback_brief(invalid_evidence_ids: List[str]) -> VisitPrepBrief:
    """
    Deterministic fallback brief when verifier fails. No claims; abstentions section explains failure.
    """
    abstention = Abstention(
        reason_code="VERIFICATION_FAILED",
        message="One or more claims referenced missing evidence; brief replaced with safe fallback.",
        missing_evidence_keys=invalid_evidence_ids if invalid_evidence_ids else [],
    )
    abstentions_section = VisitPrepSection(claims=[], abstentions=[abstention])
    return VisitPrepBrief(
        top_risks=_empty_section(),
        changes_since_last_visit=_empty_section(),
        medication_safety=_empty_section(),
        care_gaps=_empty_section(),
        agenda=_empty_section(),
        abstentions=abstentions_section,
    )


def assemble_brief(evidence_store: EvidenceStore) -> VisitPrepBrief:
    """Build VisitPrepBrief from evidence store using deterministic rules. No LLM."""
    result = evaluate_visit_prep_rules(evidence_store)
    return VisitPrepBrief(
        top_risks=result.top_risks,
        changes_since_last_visit=result.changes_since_last_visit,
        medication_safety=result.medication_safety,
        care_gaps=result.care_gaps,
        agenda=result.agenda,
        abstentions=result.abstentions,
    )


def assemble_and_verify(
    evidence_store: EvidenceStore,
) -> Tuple[VisitPrepBrief, EvidenceStore, bool]:
    """
    Assemble brief from store, verify all claims have evidence in store.
    If verification fails, return deterministic fallback brief and verified=False.
    Returns (brief, evidence_store, verified).
    """
    brief = assemble_brief(evidence_store)
    ok, invalid = verify_brief(brief, evidence_store)
    if not ok:
        brief = fallback_brief(invalid_evidence_ids=invalid)
        return (brief, evidence_store, False)
    return (brief, evidence_store, True)
