"""Verifier: reject unsupported claims; enforce every claim has evidence_ids present in EvidenceStore."""
from typing import List, Tuple

from openemr_mcp.schemas import EvidenceStore, VisitPrepBrief, VisitPrepSection


def verify_brief(brief: VisitPrepBrief, evidence_store: EvidenceStore) -> Tuple[bool, List[str]]:
    """
    Verify that every claim in the brief references only evidence_ids present in evidence_store.
    Returns (True, []) if all claims are supported; (False, list of invalid evidence_ids) otherwise.
    """
    valid_ids = {i.evidence_id for i in evidence_store.items}
    invalid: List[str] = []
    for section_name in ("top_risks", "changes_since_last_visit", "medication_safety", "care_gaps", "agenda", "abstentions"):
        section = getattr(brief, section_name)
        for c in section.claims:
            for eid in c.evidence_ids:
                if eid not in valid_ids:
                    invalid.append(eid)
    if invalid:
        return (False, invalid)
    return (True, [])
