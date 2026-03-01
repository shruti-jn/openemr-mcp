"""Deterministic clinical evidence collectors for visit prep: meds, labs, vitals. Facts only, stable evidence_id."""
import hashlib
import re
from typing import Any, List

from openemr_mcp.schemas import EvidenceItem, EvidenceStore


def _hash8(payload: str) -> str:
    """Deterministic 8-char hex hash for evidence_id."""
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:8]


def _normalize_iso_ts(ts: Any) -> str:
    """Normalize timestamp to ISO-8601 with Z suffix if no offset."""
    if ts is None:
        return ""
    s = str(ts).strip()
    if not s:
        return ""
    s = s.replace(" ", "T")
    if "T" in s and "Z" not in s and "+" not in s and "-" not in s[-6:]:
        s = s + "Z"
    return s


def _entity_safe(s: str) -> str:
    """Safe segment for evidence_id (no colons)."""
    return re.sub(r"[:\s]+", "_", (s or "").strip().lower())[:64]


# ---- Medications ----
def collect_medications(payload: dict) -> EvidenceStore:
    """Collect medication entries into EvidenceStore. Empty list => empty store."""
    meds = payload.get("medications") or []
    if not meds:
        return EvidenceStore(items=[])
    items: List[EvidenceItem] = []
    for m in meds:
        drug = (m.get("drug") or "").strip() or "unknown"
        dose = (m.get("dose") or "").strip()
        route = (m.get("route") or "").strip()
        status = (m.get("status") or "").strip()
        effective = _normalize_iso_ts(m.get("effective_date"))
        entity = _entity_safe(drug)
        field = "listing"
        canonical = f"meds|{entity}|{field}|{effective}|{dose}|{route}|{status}"
        h = _hash8(canonical)
        evidence_id = f"ev::meds::{entity}::{field}::{effective}::{h}"
        summary = f"{drug}"
        if dose:
            summary += f" {dose}"
        if route:
            summary += f" {route}"
        if status:
            summary += f" ({status})"
        items.append(
            EvidenceItem(evidence_id=evidence_id, source="meds", summary=summary)
        )
    items.sort(key=lambda x: x.evidence_id)
    items.sort(key=lambda x: x.evidence_id.split("::")[4], reverse=True)
    return EvidenceStore(items=items)


# ---- Labs ----
def collect_labs(payload: dict) -> EvidenceStore:
    """Collect lab results into EvidenceStore. Empty list => empty store."""
    labs = payload.get("labs") or []
    if not labs:
        return EvidenceStore(items=[])
    items = []
    for lab in labs:
        code = _entity_safe(str(lab.get("code") or "unknown"))
        value = lab.get("value")
        if value is None:
            continue
        unit = (str(lab.get("unit") or "")).strip() or "unknown"
        observed = _normalize_iso_ts(lab.get("observed_at"))
        field = "value"
        canonical = f"labs|{code}|{field}|{observed}|{value}|{unit}"
        h = _hash8(canonical)
        evidence_id = f"ev::labs::{code}::{field}::{observed}::{h}"
        summary = f"{code} {value} {unit}".strip()
        items.append(
            EvidenceItem(evidence_id=evidence_id, source="labs", summary=summary)
        )
    items.sort(key=lambda x: x.evidence_id)
    items.sort(key=lambda x: x.evidence_id.split("::")[4], reverse=True)
    return EvidenceStore(items=items)


# ---- Vitals ----
def collect_vitals(payload: dict) -> EvidenceStore:
    """Collect vitals into EvidenceStore. Conflicting readings (same type) all included, ordered by timestamp desc."""
    vitals = payload.get("vitals") or []
    if not vitals:
        return EvidenceStore(items=[])
    items = []
    for v in vitals:
        vtype = _entity_safe(str(v.get("type") or "unknown"))
        unit = (str(v.get("unit") or "")).strip() or "mmHg"
        observed = _normalize_iso_ts(v.get("observed_at"))
        field = "value"
        if "value_systolic" in v and "value_diastolic" in v:
            val_str = f"{v['value_systolic']}/{v['value_diastolic']}"
        else:
            val_str = str(v.get("value", ""))
        canonical = f"vitals|{vtype}|{field}|{observed}|{val_str}|{unit}"
        h = _hash8(canonical)
        evidence_id = f"ev::vitals::{vtype}::{field}::{observed}::{h}"
        summary = f"{vtype} {val_str} {unit}".strip()
        items.append(
            EvidenceItem(evidence_id=evidence_id, source="vitals", summary=summary)
        )
    items.sort(key=lambda x: x.evidence_id)
    items.sort(key=lambda x: x.evidence_id.split("::")[4], reverse=True)
    return EvidenceStore(items=items)


def collect_clinical_evidence(payload: dict) -> EvidenceStore:
    """Merge meds, labs, and vitals into one EvidenceStore. Order: timestamp desc, then evidence_id."""
    stores = [
        collect_medications(payload),
        collect_labs(payload),
        collect_vitals(payload),
    ]
    combined: List[EvidenceItem] = []
    for s in stores:
        combined.extend(s.items)
    combined.sort(key=lambda x: x.evidence_id)
    combined.sort(key=lambda x: x.evidence_id.split("::")[4], reverse=True)
    return EvidenceStore(items=combined)
