"""Deterministic rule engine for visit prep: top risks, changes, care gaps, agenda. No LLM; evidence-linked only."""
import re
from dataclasses import dataclass
from typing import List, Optional, Tuple

from openemr_mcp.schemas import Abstention, Claim, EvidenceItem, EvidenceStore, VisitPrepSection

RISK_PRIORITY_ORDER = ("ldl", "a1c", "bp")
LDL_RISK_THRESHOLD = 160
A1C_RISK_THRESHOLD = 7.0
BP_SYSTOLIC_RISK_THRESHOLD = 140


@dataclass
class RuleEngineResult:
    top_risks: VisitPrepSection
    changes_since_last_visit: VisitPrepSection
    medication_safety: VisitPrepSection
    care_gaps: VisitPrepSection
    agenda: VisitPrepSection
    abstentions: VisitPrepSection


def _parse_evidence_id(evidence_id: str) -> Tuple[str, str, str]:
    parts = evidence_id.split("::")
    if len(parts) >= 5:
        return (parts[1], parts[2], parts[4])
    return ("", "", "")


def _parse_lab_value(summary: str, entity: str) -> Optional[float]:
    if entity in ("ldl", "a1c"):
        m = re.search(r"[\d.]+", summary)
        return float(m.group()) if m else None
    return None


def _parse_bp_systolic(summary: str) -> Optional[int]:
    m = re.search(r"bp\s+(\d+)/\d+", summary, re.I)
    if m:
        return int(m.group(1))
    m = re.search(r"(\d+)\s*/\s*\d+", summary)
    return int(m.group(1)) if m else None


def _latest_per_entity(items: List[EvidenceItem]) -> List[EvidenceItem]:
    by_key: dict = {}
    for item in items:
        source, entity, iso_ts = _parse_evidence_id(item.evidence_id)
        key = (source, entity)
        if key not in by_key or iso_ts > by_key[key][1]:
            by_key[key] = (item, iso_ts)
    out = [v[0] for v in by_key.values()]
    out.sort(key=lambda x: x.evidence_id)
    out.sort(key=lambda x: _parse_evidence_id(x.evidence_id)[2], reverse=True)
    return out


def _risk_claims(store: EvidenceStore) -> List[Claim]:
    latest = _latest_per_entity(store.items)
    claims: List[Claim] = []
    for item in latest:
        source, entity, _ = _parse_evidence_id(item.evidence_id)
        if source == "labs" and entity == "ldl":
            v = _parse_lab_value(item.summary, entity)
            if v is not None and v >= LDL_RISK_THRESHOLD:
                claims.append(Claim(text=f"Elevated LDL ({item.summary.strip()})", evidence_ids=[item.evidence_id]))
        elif source == "labs" and entity == "a1c":
            v = _parse_lab_value(item.summary, entity)
            if v is not None and v >= A1C_RISK_THRESHOLD:
                claims.append(Claim(text=f"Elevated A1c ({item.summary.strip()})", evidence_ids=[item.evidence_id]))
        elif source == "vitals" and entity == "bp":
            v = _parse_bp_systolic(item.summary)
            if v is not None and v >= BP_SYSTOLIC_RISK_THRESHOLD:
                claims.append(Claim(text=f"Elevated BP ({item.summary.strip()})", evidence_ids=[item.evidence_id]))

    def sort_key(c: Claim) -> Tuple[int, str]:
        eid = c.evidence_ids[0]
        _, entity, _ = _parse_evidence_id(eid)
        try:
            prio = RISK_PRIORITY_ORDER.index(entity)
        except ValueError:
            prio = 99
        return (prio, eid)

    claims.sort(key=sort_key)
    return claims


def _changes_claims(store: EvidenceStore) -> List[Claim]:
    by_key: dict = {}
    for item in store.items:
        source, entity, iso_ts = _parse_evidence_id(item.evidence_id)
        key = (source, entity)
        if key not in by_key:
            by_key[key] = []
        by_key[key].append((item, iso_ts))
    claims: List[Claim] = []
    for key, pairs in by_key.items():
        pairs.sort(key=lambda p: p[1], reverse=True)
        if len(pairs) < 2:
            continue
        latest_item, _ = pairs[0]
        prev_item, _ = pairs[1]
        source, entity = key
        if source == "labs" and entity in ("ldl", "a1c"):
            v_lat = _parse_lab_value(latest_item.summary, entity)
            v_prev = _parse_lab_value(prev_item.summary, entity)
            if v_lat is not None and v_prev is not None:
                if v_lat > v_prev:
                    claims.append(Claim(text=f"{entity.upper()} increased: {prev_item.summary} -> {latest_item.summary}", evidence_ids=[prev_item.evidence_id, latest_item.evidence_id]))
                elif v_lat < v_prev:
                    claims.append(Claim(text=f"{entity.upper()} improved: {prev_item.summary} -> {latest_item.summary}", evidence_ids=[prev_item.evidence_id, latest_item.evidence_id]))
    claims.sort(key=lambda c: c.evidence_ids[0])
    return claims


def _medication_safety_claims(store: EvidenceStore) -> List[Claim]:
    claims: List[Claim] = []
    for item in store.items:
        source, _, _ = _parse_evidence_id(item.evidence_id)
        if source == "meds":
            claims.append(Claim(text=f"On medication: {item.summary}", evidence_ids=[item.evidence_id]))
    claims.sort(key=lambda c: c.evidence_ids[0])
    return claims


def _care_gaps_claims(store: EvidenceStore) -> List[Claim]:
    claims: List[Claim] = []
    for item in store.items:
        if item.source == "appointments" and "missed" in item.summary.lower():
            claims.append(Claim(text=f"Missed appointment: {item.summary}", evidence_ids=[item.evidence_id]))
    claims.sort(key=lambda c: c.evidence_ids[0])
    return claims


def _agenda_from_rules(top_risks: VisitPrepSection, care_gaps: VisitPrepSection, medication_safety: VisitPrepSection) -> VisitPrepSection:
    claims: List[Claim] = []
    for c in top_risks.claims:
        claims.append(Claim(text=f"Discuss: {c.text}", evidence_ids=list(c.evidence_ids)))
    for c in care_gaps.claims:
        claims.append(Claim(text=f"Address care gap: {c.text}", evidence_ids=list(c.evidence_ids)))
    if medication_safety.claims:
        eids = [eid for c in medication_safety.claims for eid in c.evidence_ids]
        claims.append(Claim(text="Review medications", evidence_ids=eids[:5]))
    claims.sort(key=lambda c: (c.evidence_ids[0], c.text))
    return VisitPrepSection(claims=claims, abstentions=[])


def _abstentions_for_missing(store: EvidenceStore) -> VisitPrepSection:
    abstentions: List[Abstention] = []
    if not store.items:
        abstentions.append(Abstention(reason_code="MISSING_EVIDENCE", message="No clinical evidence available for rule evaluation.", missing_evidence_keys=["labs", "vitals", "meds"]))
    return VisitPrepSection(claims=[], abstentions=abstentions)


def evaluate_visit_prep_rules(evidence_store: EvidenceStore) -> RuleEngineResult:
    top_risks_claims = _risk_claims(evidence_store)
    changes_claims = _changes_claims(evidence_store)
    med_claims = _medication_safety_claims(evidence_store)
    care_gaps_claims = _care_gaps_claims(evidence_store)
    abstentions_section = _abstentions_for_missing(evidence_store)
    top_risks_section = VisitPrepSection(claims=top_risks_claims, abstentions=[])
    changes_section = VisitPrepSection(claims=changes_claims, abstentions=[])
    med_section = VisitPrepSection(claims=med_claims, abstentions=[])
    care_gaps_section = VisitPrepSection(claims=care_gaps_claims, abstentions=[])
    agenda_section = _agenda_from_rules(top_risks_section, care_gaps_section, med_section)
    return RuleEngineResult(
        top_risks=top_risks_section, changes_since_last_visit=changes_section,
        medication_safety=med_section, care_gaps=care_gaps_section,
        agenda=agenda_section, abstentions=abstentions_section,
    )
