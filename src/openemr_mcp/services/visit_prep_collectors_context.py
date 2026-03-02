"""
Visit prep context collectors: appointments, demographics, care-team.
Normalizes into EvidenceStore with source + stable evidence_id. Facts only, no inference.
"""

import hashlib

from openemr_mcp.schemas import EvidenceItem, EvidenceStore


def _hash8(canonical: str) -> str:
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:8]


def _iso_ts_from_appointment(apt: dict) -> str:
    raw = apt.get("start_time") or ""
    if not raw:
        return "1970-01-01T00:00:00Z"
    s = str(raw).strip()
    if "T" in s and ("Z" in s or "+" in s or (len(s) >= 19 and s[10] == "T")):
        return s if "Z" in s or "+" in s else s + "Z"
    if len(s) >= 10 and s[4] == "-":
        return s[:10] + "T00:00:00Z" if len(s) == 10 else s + ("Z" if s[-1] != "Z" else "")
    return "1970-01-01T00:00:00Z"


def collect_appointments(appointments: list[dict]) -> EvidenceStore:
    """
    Collect upcoming/missed appointments with status and dates.
    Each appointment becomes one EvidenceItem. Ordered by start_time descending.
    """
    if not appointments:
        return EvidenceStore(items=[])
    items: list[EvidenceItem] = []
    for apt in appointments:
        apt_id = str(apt.get("appointment_id") or "unknown").strip() or "unknown"
        ts = _iso_ts_from_appointment(apt)
        status = str(apt.get("status") or "unknown").strip() or "unknown"
        reason = (apt.get("reason") or "").strip()
        summary = f"{status} {ts[:10]}"
        if reason:
            summary += f"; {reason}"
        canonical = f"appointments|{apt_id}|summary|{ts}|{summary}"
        h = _hash8(canonical)
        evidence_id = f"ev::appointments::{apt_id}::summary::{ts}::{h}"
        items.append(EvidenceItem(evidence_id=evidence_id, source="appointments", summary=summary))
    items.sort(key=lambda i: (i.evidence_id.split("::")[4], i.evidence_id), reverse=True)
    return EvidenceStore(items=items)


def collect_demographics(demographics: dict | None) -> EvidenceStore:
    """
    Collect demographics fields needed for risk stratification context.
    Only present (non-null, non-empty) fields are emitted. No inference.
    """
    if not demographics or not isinstance(demographics, dict):
        return EvidenceStore(items=[])
    fields_used = ("dob", "sex", "race", "ethnicity", "language", "zip", "patient_id")
    items: list[EvidenceItem] = []
    for field in fields_used:
        val = demographics.get(field)
        if val is None or (isinstance(val, str) and not val.strip()):
            continue
        val_str = str(val).strip()
        ts = val_str[:10] + "T00:00:00Z" if len(val_str) >= 10 and val_str[4] == "-" else "2020-01-01T00:00:00Z"
        entity = "patient"
        summary = f"{field}={val_str}"
        canonical = f"demographics|{entity}|{field}|{ts}|{summary}"
        h = _hash8(canonical)
        evidence_id = f"ev::demographics::{entity}::{field}::{ts}::{h}"
        items.append(EvidenceItem(evidence_id=evidence_id, source="demographics", summary=summary))
    items.sort(key=lambda i: i.evidence_id)
    return EvidenceStore(items=items)


def collect_care_team(care_team: list[dict]) -> EvidenceStore:
    """
    Collect care-team members and ownership metadata.
    Missing is_owner is reported as unknown in summary.
    """
    if not care_team:
        return EvidenceStore(items=[])
    items: list[EvidenceItem] = []
    for i, member in enumerate(care_team):
        member_id = str(member.get("member_id") or f"member_{i}").strip() or f"member_{i}"
        role = str(member.get("role") or "").strip() or "unknown"
        is_owner = member.get("is_owner")
        if is_owner is True:
            owner_str = "owner"
        elif is_owner is False:
            owner_str = "not owner"
        else:
            owner_str = "owner unknown"
        name = (member.get("name") or "").strip()
        summary = f"{role}; {owner_str}"
        if name:
            summary = f"{name}; " + summary
        ts = "2020-01-01T00:00:00Z"
        canonical = f"care_team|{member_id}|member|{ts}|{summary}"
        h = _hash8(canonical)
        evidence_id = f"ev::care_team::{member_id}::member::{ts}::{h}"
        items.append(EvidenceItem(evidence_id=evidence_id, source="care_team", summary=summary))
    items.sort(key=lambda i: i.evidence_id)
    return EvidenceStore(items=items)


def collect_context_evidence(payload: dict) -> EvidenceStore:
    """
    Collect and merge appointments, demographics, and care-team evidence.
    payload: { "appointments": list, "demographics": dict | null, "care_team": list }
    Deterministic order: appointments (date desc), demographics, care_team.
    """
    appointments = payload.get("appointments")
    if not isinstance(appointments, list):
        appointments = []
    demographics = payload.get("demographics")
    care_team = payload.get("care_team")
    if not isinstance(care_team, list):
        care_team = []

    store_app = collect_appointments(appointments)
    store_dem = collect_demographics(demographics)
    store_ct = collect_care_team(care_team)

    all_items: list[EvidenceItem] = []
    all_items.extend(store_app.items)
    all_items.extend(store_dem.items)
    all_items.extend(store_ct.items)
    return EvidenceStore(items=all_items)
