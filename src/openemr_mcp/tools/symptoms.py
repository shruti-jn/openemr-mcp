"""
Symptom lookup tool.
SYMPTOM_SOURCE: mock (default) | infermedica
"""
import logging
from typing import List, Optional

import httpx

from openemr_mcp.config import settings
from openemr_mcp.schemas import PossibleCondition, SymptomLookupResponse

_log = logging.getLogger("openemr_mcp")

MEDICAL_DISCLAIMER = (
    "DISCLAIMER: This information is for reference purposes only and does not constitute "
    "medical advice or a diagnosis. Always consult a licensed healthcare provider for "
    "evaluation and treatment."
)

_SYMPTOM_DB = [
    {"symptom_keys": {"chest pain", "chest tightness", "shortness of breath", "dyspnea"}, "conditions": [PossibleCondition(name="Acute Coronary Syndrome (Heart Attack)", likelihood="HIGH", urgency="URGENT"), PossibleCondition(name="Pulmonary Embolism", likelihood="MODERATE", urgency="URGENT"), PossibleCondition(name="Unstable Angina", likelihood="MODERATE", urgency="URGENT"), PossibleCondition(name="Aortic Dissection", likelihood="LOW", urgency="URGENT")]},
    {"symptom_keys": {"fever", "cough", "fatigue", "tiredness", "loss of taste", "loss of smell"}, "conditions": [PossibleCondition(name="COVID-19", likelihood="HIGH", urgency="SEE_DOCTOR"), PossibleCondition(name="Influenza (Flu)", likelihood="HIGH", urgency="SEE_DOCTOR"), PossibleCondition(name="Pneumonia", likelihood="MODERATE", urgency="SEE_DOCTOR"), PossibleCondition(name="Common Cold", likelihood="MODERATE", urgency="MONITOR")]},
    {"symptom_keys": {"headache", "nausea", "vomiting", "light sensitivity", "photophobia", "throbbing"}, "conditions": [PossibleCondition(name="Migraine", likelihood="HIGH", urgency="SEE_DOCTOR"), PossibleCondition(name="Tension Headache", likelihood="HIGH", urgency="MONITOR"), PossibleCondition(name="Meningitis", likelihood="LOW", urgency="URGENT")]},
    {"symptom_keys": {"rash", "itching", "hives", "swelling", "urticaria"}, "conditions": [PossibleCondition(name="Allergic Reaction", likelihood="HIGH", urgency="SEE_DOCTOR"), PossibleCondition(name="Contact Dermatitis", likelihood="HIGH", urgency="MONITOR"), PossibleCondition(name="Eczema", likelihood="MODERATE", urgency="MONITOR"), PossibleCondition(name="Anaphylaxis", likelihood="LOW", urgency="URGENT")]},
    {"symptom_keys": {"abdominal pain", "stomach pain", "diarrhea", "nausea", "vomiting"}, "conditions": [PossibleCondition(name="Gastroenteritis", likelihood="HIGH", urgency="MONITOR"), PossibleCondition(name="Food Poisoning", likelihood="HIGH", urgency="MONITOR"), PossibleCondition(name="Appendicitis", likelihood="LOW", urgency="URGENT"), PossibleCondition(name="Irritable Bowel Syndrome", likelihood="MODERATE", urgency="SEE_DOCTOR")]},
    {"symptom_keys": {"joint pain", "joint swelling", "stiffness", "arthralgia"}, "conditions": [PossibleCondition(name="Rheumatoid Arthritis", likelihood="MODERATE", urgency="SEE_DOCTOR"), PossibleCondition(name="Osteoarthritis", likelihood="HIGH", urgency="SEE_DOCTOR"), PossibleCondition(name="Gout", likelihood="MODERATE", urgency="SEE_DOCTOR"), PossibleCondition(name="Lupus", likelihood="LOW", urgency="SEE_DOCTOR")]},
    {"symptom_keys": {"dizziness", "lightheadedness", "fainting", "syncope", "vertigo"}, "conditions": [PossibleCondition(name="Benign Positional Vertigo", likelihood="HIGH", urgency="SEE_DOCTOR"), PossibleCondition(name="Orthostatic Hypotension", likelihood="MODERATE", urgency="SEE_DOCTOR"), PossibleCondition(name="Cardiac Arrhythmia", likelihood="LOW", urgency="URGENT"), PossibleCondition(name="Dehydration", likelihood="MODERATE", urgency="MONITOR")]},
    {"symptom_keys": {"confusion", "altered mental status", "disorientation", "sudden weakness", "slurred speech", "facial droop"}, "conditions": [PossibleCondition(name="Stroke (CVA)", likelihood="HIGH", urgency="URGENT"), PossibleCondition(name="Transient Ischemic Attack (TIA)", likelihood="MODERATE", urgency="URGENT"), PossibleCondition(name="Hypoglycemia", likelihood="MODERATE", urgency="URGENT"), PossibleCondition(name="Septic Encephalopathy", likelihood="LOW", urgency="URGENT")]},
    {"symptom_keys": {"back pain", "lower back pain", "sciatica", "radiating leg pain"}, "conditions": [PossibleCondition(name="Lumbar Muscle Strain", likelihood="HIGH", urgency="MONITOR"), PossibleCondition(name="Herniated Disc", likelihood="MODERATE", urgency="SEE_DOCTOR"), PossibleCondition(name="Sciatica", likelihood="MODERATE", urgency="SEE_DOCTOR"), PossibleCondition(name="Kidney Stone", likelihood="LOW", urgency="SEE_DOCTOR")]},
    {"symptom_keys": {"frequent urination", "painful urination", "dysuria", "blood in urine", "hematuria"}, "conditions": [PossibleCondition(name="Urinary Tract Infection (UTI)", likelihood="HIGH", urgency="SEE_DOCTOR"), PossibleCondition(name="Kidney Infection (Pyelonephritis)", likelihood="MODERATE", urgency="SEE_DOCTOR"), PossibleCondition(name="Bladder Cancer", likelihood="LOW", urgency="SEE_DOCTOR"), PossibleCondition(name="Kidney Stone", likelihood="MODERATE", urgency="SEE_DOCTOR")]},
]

_URGENCY_ORDER = {"URGENT": 0, "SEE_DOCTOR": 1, "MONITOR": 2}
_INFERMEDICA_URGENCY_MAP = {"emergency_ambulance": "URGENT", "emergency": "URGENT", "consultation_24": "SEE_DOCTOR", "consultation": "SEE_DOCTOR", "self_care": "MONITOR"}
_INFERMEDICA_BASE = "https://api.infermedica.com/v3"


def _run_mock_check(symptoms: List[str]) -> SymptomLookupResponse:
    normalized = [s.strip().lower() for s in symptoms if s and s.strip()]
    matched_conditions: List[PossibleCondition] = []
    for entry in _SYMPTOM_DB:
        entry_keys = entry["symptom_keys"]
        if any(any(nq in ek or ek in nq for ek in entry_keys) for nq in normalized):
            matched_conditions.extend(entry["conditions"])
    seen: dict = {}
    for cond in matched_conditions:
        if cond.name not in seen:
            seen[cond.name] = cond
        else:
            existing = seen[cond.name]
            if _URGENCY_ORDER[cond.urgency] < _URGENCY_ORDER[existing.urgency]:
                seen[cond.name] = cond
    deduped = sorted(seen.values(), key=lambda c: (_URGENCY_ORDER[c.urgency], c.name))
    urgency_level = deduped[0].urgency if deduped else "MONITOR"
    return SymptomLookupResponse(
        symptoms_checked=[s.strip() for s in symptoms if s and s.strip()],
        possible_conditions=deduped, urgency_level=urgency_level, disclaimer=MEDICAL_DISCLAIMER,
    )


def _run_infermedica_check(symptoms: List[str]) -> Optional[SymptomLookupResponse]:
    app_id = settings.infermedica_app_id
    app_key = settings.infermedica_app_key
    if not app_id or not app_key:
        _log.warning("SYMPTOM_SOURCE=infermedica but credentials not set — falling back to mock")
        return None
    headers = {"App-Id": app_id, "App-Key": app_key, "Content-Type": "application/json"}
    symptom_text = ", ".join(s.strip() for s in symptoms if s and s.strip())
    try:
        parse_resp = httpx.post(f"{_INFERMEDICA_BASE}/parse", headers=headers, json={"text": symptom_text, "age": {"value": 40}}, timeout=8.0)
        parse_resp.raise_for_status()
        mentions = parse_resp.json().get("mentions", [])
    except Exception as exc:
        _log.warning("Infermedica /parse failed: %s", exc)
        return None
    if not mentions:
        return SymptomLookupResponse(symptoms_checked=[s.strip() for s in symptoms if s and s.strip()], possible_conditions=[], urgency_level="MONITOR", disclaimer=MEDICAL_DISCLAIMER)
    evidence = [{"id": m["id"], "choice_id": "present"} for m in mentions if m.get("choice_id") != "absent"]
    try:
        diag_resp = httpx.post(f"{_INFERMEDICA_BASE}/diagnosis", headers=headers, json={"sex": "male", "age": {"value": 40}, "evidence": evidence}, timeout=10.0)
        diag_resp.raise_for_status()
        diag_data = diag_resp.json()
    except Exception as exc:
        _log.warning("Infermedica /diagnosis failed: %s", exc)
        return None
    conditions: List[PossibleCondition] = []
    for item in diag_data.get("conditions", [])[:8]:
        name = item.get("name", "Unknown condition")
        probability = item.get("probability", 0.0)
        likelihood = "HIGH" if probability >= 0.4 else "MODERATE" if probability >= 0.15 else "LOW"
        conditions.append(PossibleCondition(name=name, likelihood=likelihood, urgency="SEE_DOCTOR"))
    urgency_level = "SEE_DOCTOR"
    try:
        triage_resp = httpx.post(f"{_INFERMEDICA_BASE}/triage", headers=headers, json={"sex": "male", "age": {"value": 40}, "evidence": evidence}, timeout=8.0)
        if triage_resp.status_code == 200:
            raw_urgency = triage_resp.json().get("triage_level", "consultation")
            urgency_level = _INFERMEDICA_URGENCY_MAP.get(raw_urgency, "SEE_DOCTOR")
    except Exception:
        pass
    conditions_sorted = sorted(conditions, key=lambda c: (_URGENCY_ORDER.get(c.urgency, 1), c.name))
    return SymptomLookupResponse(symptoms_checked=[s.strip() for s in symptoms if s and s.strip()], possible_conditions=conditions_sorted, urgency_level=urgency_level, disclaimer=MEDICAL_DISCLAIMER)


def run_symptom_lookup(symptoms: List[str]) -> SymptomLookupResponse:
    """Look up possible conditions for a list of symptoms."""
    if settings.symptom_source == "infermedica":
        result = _run_infermedica_check(symptoms)
        if result is not None:
            return result
        _log.warning("Infermedica check failed — falling back to mock")
    return _run_mock_check(symptoms)
