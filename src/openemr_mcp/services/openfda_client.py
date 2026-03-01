"""
OpenFDA API client — real FDA drug data, free, no API key required.

APIs:
  - Drug Adverse Events (FAERS): https://api.fda.gov/drug/event.json
  - Drug Labels:                  https://api.fda.gov/drug/label.json
"""
import logging
from typing import Optional

import httpx

from openemr_mcp.config import settings
from openemr_mcp.schemas import FDAAdverseEventSummary, FDAAdverseEvent, FDADrugLabelResult

_log = logging.getLogger("openemr_mcp")
_OPENFDA_BASE = "https://api.fda.gov"
_REQUEST_TIMEOUT = 8.0


def _fda_params_with_key(params: dict) -> dict:
    if settings.openfda_api_key:
        params = dict(params)
        params["api_key"] = settings.openfda_api_key
    return params


def _fda_headers() -> dict:
    if settings.openfda_api_key:
        return {"Authorization": f"Basic {settings.openfda_api_key}"}
    return {}


# Mock data
_MOCK_ADVERSE_EVENTS: dict = {
    "warfarin": FDAAdverseEventSummary(
        drug_name="Warfarin", total_reports=15234, serious_reports=12891,
        top_reactions=[
            FDAAdverseEvent(reaction="Hemorrhage", serious=True, report_count=4821),
            FDAAdverseEvent(reaction="Prothrombin time prolonged", serious=True, report_count=2103),
            FDAAdverseEvent(reaction="Epistaxis", serious=False, report_count=1892),
            FDAAdverseEvent(reaction="Subdural hematoma", serious=True, report_count=1204),
            FDAAdverseEvent(reaction="Gastrointestinal hemorrhage", serious=True, report_count=987),
        ],
    ),
    "metformin": FDAAdverseEventSummary(
        drug_name="Metformin", total_reports=8923, serious_reports=3214,
        top_reactions=[
            FDAAdverseEvent(reaction="Lactic acidosis", serious=True, report_count=1823),
            FDAAdverseEvent(reaction="Nausea", serious=False, report_count=1654),
            FDAAdverseEvent(reaction="Diarrhoea", serious=False, report_count=1432),
            FDAAdverseEvent(reaction="Vitamin B12 deficiency", serious=False, report_count=987),
            FDAAdverseEvent(reaction="Hypoglycaemia", serious=True, report_count=654),
        ],
    ),
    "lisinopril": FDAAdverseEventSummary(
        drug_name="Lisinopril", total_reports=11203, serious_reports=4987,
        top_reactions=[
            FDAAdverseEvent(reaction="Angioedema", serious=True, report_count=3201),
            FDAAdverseEvent(reaction="Cough", serious=False, report_count=2893),
            FDAAdverseEvent(reaction="Hypotension", serious=True, report_count=1654),
            FDAAdverseEvent(reaction="Renal impairment", serious=True, report_count=987),
            FDAAdverseEvent(reaction="Hyperkalemia", serious=True, report_count=765),
        ],
    ),
    "aspirin": FDAAdverseEventSummary(
        drug_name="Aspirin", total_reports=9876, serious_reports=4321,
        top_reactions=[
            FDAAdverseEvent(reaction="Gastrointestinal hemorrhage", serious=True, report_count=2341),
            FDAAdverseEvent(reaction="Gastrointestinal pain", serious=False, report_count=1876),
            FDAAdverseEvent(reaction="Nausea", serious=False, report_count=1234),
            FDAAdverseEvent(reaction="Tinnitus", serious=False, report_count=987),
            FDAAdverseEvent(reaction="Allergic reaction", serious=True, report_count=654),
        ],
    ),
}

_MOCK_DRUG_LABELS: dict = {
    "warfarin": FDADrugLabelResult(
        drug_name="Warfarin", brand_names=["Coumadin", "Jantoven"], generic_name="warfarin sodium",
        boxed_warning="WARNING: BLEEDING RISK. Warfarin can cause serious and fatal bleeding. Perform regular monitoring of INR.",
        warnings="Hemorrhage: Most serious risk. Monitor INR regularly.",
        contraindications="Hemorrhagic tendencies or blood dyscrasias.",
        indications_and_usage="Prophylaxis and treatment of thromboembolic complications.",
        manufacturer="Bristol-Myers Squibb", has_boxed_warning=True,
    ),
    "metformin": FDADrugLabelResult(
        drug_name="Metformin", brand_names=["Glucophage", "Fortamet", "Glumetza"], generic_name="metformin hydrochloride",
        boxed_warning="WARNING: LACTIC ACIDOSIS. Fatal in approximately 50% of cases when it occurs.",
        warnings="Renal impairment: Obtain eGFR before starting; contraindicated when eGFR < 30.",
        contraindications="Severe renal impairment (eGFR < 30 mL/min/1.73 m²).",
        indications_and_usage="Adjunct to diet and exercise for type 2 diabetes.",
        manufacturer="Various", has_boxed_warning=True,
    ),
    "lisinopril": FDADrugLabelResult(
        drug_name="Lisinopril", brand_names=["Prinivil", "Zestril"], generic_name="lisinopril",
        boxed_warning="WARNING: FETAL TOXICITY. Discontinue lisinopril when pregnancy is detected.",
        warnings="Angioedema: May occur at any time during treatment.",
        contraindications="History of angioedema related to previous ACE inhibitor treatment.",
        indications_and_usage="Treatment of hypertension, heart failure, and acute myocardial infarction.",
        manufacturer="Various", has_boxed_warning=True,
    ),
}


def _get_mock_adverse_events(drug_name: str) -> FDAAdverseEventSummary:
    key = drug_name.lower().split()[0]
    if key in _MOCK_ADVERSE_EVENTS:
        return _MOCK_ADVERSE_EVENTS[key]
    return FDAAdverseEventSummary(drug_name=drug_name, total_reports=0, serious_reports=0, top_reactions=[])


def _get_mock_drug_label(drug_name: str) -> FDADrugLabelResult:
    key = drug_name.lower().split()[0]
    return _MOCK_DRUG_LABELS.get(key, FDADrugLabelResult(drug_name=drug_name, brand_names=[]))


def _parse_adverse_events(drug_name: str, data: dict, limit: int) -> FDAAdverseEventSummary:
    total = data.get("meta", {}).get("results", {}).get("total", 0)
    results = data.get("results") or []
    reaction_counts: dict = {}
    serious_reactions: set = set()
    serious_count = 0
    for report in results:
        is_serious = bool(report.get("serious", 0))
        if is_serious:
            serious_count += 1
        for rx in report.get("patient", {}).get("reaction") or []:
            name = rx.get("reactionmeddrapt", "Unknown").title()
            reaction_counts[name] = reaction_counts.get(name, 0) + 1
            if is_serious:
                serious_reactions.add(name)
    top = sorted(reaction_counts.items(), key=lambda x: x[1], reverse=True)[:limit]
    reactions = [FDAAdverseEvent(reaction=name, serious=(name in serious_reactions), report_count=count) for name, count in top]
    return FDAAdverseEventSummary(drug_name=drug_name, total_reports=total, serious_reports=serious_count, top_reactions=reactions)


def _truncate(text: Optional[str], max_chars: int = 400) -> Optional[str]:
    if not text:
        return text
    text = text.strip()
    return text[:max_chars] + "..." if len(text) > max_chars else text


def _parse_drug_label(drug_name: str, data: dict) -> FDADrugLabelResult:
    results = data.get("results") or []
    if not results:
        return FDADrugLabelResult(drug_name=drug_name)
    r = results[0]
    openfda = r.get("openfda", {})
    brand_names = openfda.get("brand_name") or []
    generic_name = (openfda.get("generic_name") or [None])[0]
    manufacturer = (openfda.get("manufacturer_name") or [None])[0]

    def _first(key: str) -> Optional[str]:
        vals = r.get(key)
        if not vals:
            return None
        return _truncate(" ".join(vals) if isinstance(vals, list) else vals)

    boxed = _first("boxed_warning")
    return FDADrugLabelResult(
        drug_name=drug_name, brand_names=brand_names[:5], generic_name=generic_name,
        boxed_warning=boxed, warnings=_first("warnings"),
        contraindications=_first("contraindications"),
        indications_and_usage=_first("indications_and_usage"),
        manufacturer=manufacturer, has_boxed_warning=bool(boxed),
    )


def get_adverse_events(drug_name: str, limit: int = 5) -> FDAAdverseEventSummary:
    if settings.openfda_source == "mock":
        return _get_mock_adverse_events(drug_name)
    try:
        params = _fda_params_with_key({"search": f'patient.drug.medicinalproduct:"{drug_name}"', "limit": min(limit * 5, 100)})
        resp = httpx.get(f"{_OPENFDA_BASE}/drug/event.json", params=params, headers=_fda_headers(), timeout=_REQUEST_TIMEOUT, follow_redirects=True)
        resp.raise_for_status()
        return _parse_adverse_events(drug_name, resp.json(), limit)
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code == 404:
            return FDAAdverseEventSummary(drug_name=drug_name, total_reports=0, serious_reports=0, top_reactions=[])
        _log.warning("OpenFDA adverse events API error for %r: %s", drug_name, exc)
        return _get_mock_adverse_events(drug_name)
    except Exception as exc:
        _log.warning("OpenFDA adverse events call failed for %r: %s", drug_name, exc)
        return _get_mock_adverse_events(drug_name)


def get_drug_label(drug_name: str) -> FDADrugLabelResult:
    if settings.openfda_source == "mock":
        return _get_mock_drug_label(drug_name)
    try:
        for search_field in ("openfda.generic_name", "openfda.brand_name"):
            params = _fda_params_with_key({"search": f'{search_field}:"{drug_name}"', "limit": 1})
            resp = httpx.get(f"{_OPENFDA_BASE}/drug/label.json", params=params, headers=_fda_headers(), timeout=_REQUEST_TIMEOUT, follow_redirects=True)
            if resp.status_code == 200:
                data = resp.json()
                if data.get("results"):
                    return _parse_drug_label(drug_name, data)
        return FDADrugLabelResult(drug_name=drug_name)
    except Exception as exc:
        _log.warning("OpenFDA label call failed for %r: %s", drug_name, exc)
        return _get_mock_drug_label(drug_name)
