"""
Drug interaction check tool.
DRUG_INTERACTION_SOURCE: mock (default) | rxnorm | openfda
"""
import logging
from typing import List, Optional

import httpx

from openemr_mcp.config import settings
from openemr_mcp.repositories._errors import ToolError
from openemr_mcp.schemas import DrugInteraction, DrugInteractionResponse

_log = logging.getLogger("openemr_mcp")

_INTERACTION_DB: List[DrugInteraction] = [
    DrugInteraction(drug_a="Warfarin",       drug_b="Aspirin",         severity="HIGH",     description="Concurrent use of Warfarin and Aspirin significantly increases the risk of serious bleeding events including gastrointestinal and intracranial hemorrhage."),
    DrugInteraction(drug_a="Warfarin",       drug_b="Ibuprofen",       severity="HIGH",     description="NSAIDs like Ibuprofen can potentiate the anticoagulant effect of Warfarin and cause gastrointestinal bleeding."),
    DrugInteraction(drug_a="Atorvastatin",   drug_b="Clarithromycin",  severity="HIGH",     description="Clarithromycin inhibits CYP3A4, dramatically increasing Atorvastatin plasma levels and risk of myopathy or rhabdomyolysis."),
    DrugInteraction(drug_a="Lisinopril",     drug_b="Potassium Chloride", severity="MODERATE", description="ACE inhibitors like Lisinopril reduce potassium excretion. Adding potassium supplements risks hyperkalemia."),
    DrugInteraction(drug_a="Metformin",      drug_b="Alcohol",         severity="MODERATE", description="Alcohol potentiates Metformin's effect on lactate metabolism, increasing the risk of lactic acidosis."),
    DrugInteraction(drug_a="Sertraline",     drug_b="Lorazepam",       severity="MODERATE", description="CNS depressants like Lorazepam may enhance the sedative effects of Sertraline."),
    DrugInteraction(drug_a="Digoxin",        drug_b="Furosemide",      severity="MODERATE", description="Furosemide-induced hypokalemia can potentiate Digoxin toxicity. Monitor potassium levels closely."),
    DrugInteraction(drug_a="Methotrexate",   drug_b="Ibuprofen",       severity="HIGH",     description="NSAIDs reduce renal clearance of Methotrexate, potentially causing toxic accumulation."),
    DrugInteraction(drug_a="Prednisone",     drug_b="Ibuprofen",       severity="MODERATE", description="Combining corticosteroids with NSAIDs substantially increases the risk of peptic ulcer disease."),
    DrugInteraction(drug_a="Albuterol Inhaler", drug_b="Metoprolol Succinate", severity="MODERATE", description="Non-selective beta-blockers can antagonize the bronchodilator effect of Albuterol."),
]

_PAIR_INDEX: dict = {}
for _item in _INTERACTION_DB:
    _key = frozenset({_item.drug_a.lower(), _item.drug_b.lower()})
    _PAIR_INDEX[_key] = _item

_RXNORM_BASE = "https://rxnav.nlm.nih.gov/REST"
_OPENFDA_BASE = "https://api.fda.gov"
_OPENFDA_TIMEOUT = 8.0


def _run_mock_check(medications: List[str]) -> DrugInteractionResponse:
    meds = [m.strip() for m in medications if m and m.strip()]
    interactions: List[DrugInteraction] = []
    for i in range(len(meds)):
        for j in range(i + 1, len(meds)):
            key = frozenset({meds[i].lower(), meds[j].lower()})
            hit = _PAIR_INDEX.get(key)
            if hit:
                interactions.append(hit)
    has_critical = any(ix.severity == "HIGH" for ix in interactions)
    return DrugInteractionResponse(medications_checked=meds, interactions=interactions, has_critical=has_critical)


def _run_openfda_check(medications: List[str]) -> Optional[DrugInteractionResponse]:
    meds = [m.strip() for m in medications if m and m.strip()]
    if len(meds) < 2:
        return DrugInteractionResponse(medications_checked=meds, interactions=[], has_critical=False)
    interactions: List[DrugInteraction] = []
    has_critical = False
    # Pairwise queries to OpenFDA FAERS to see co-reported reactions
    for i in range(len(meds)):
        for j in range(i + 1, len(meds)):
            a = meds[i]
            b = meds[j]
            try:
                params = {
                    "search": f'patient.drug.medicinalproduct:"{a}" AND patient.drug.medicinalproduct:"{b}"',
                    "count": "patient.reaction.reactionmeddrapt.exact",
                    "limit": 5,
                }
                r = httpx.get(f"{_OPENFDA_BASE}/drug/event.json", params=params, timeout=_OPENFDA_TIMEOUT)
                r.raise_for_status()
                data = r.json()
            except Exception as exc:
                _log.warning("OpenFDA interaction lookup failed for %r + %r: %s", a, b, exc)
                return None
            counts = data.get("results") or []
            if not isinstance(counts, list):
                continue
            # Flag critical if any reaction is commonly co-reported
            total = sum(c.get("count", 0) for c in counts if isinstance(c, dict))
            severity = "HIGH" if total >= 50 else "MODERATE" if total >= 5 else "LOW"
            has_critical = has_critical or severity == "HIGH"
            top_reaction = counts[0].get("term", "Unknown") if counts else "Adverse event reported together"
            
            # Skip if no meaningful signal
            if total == 0:
                continue
                
            interactions.append(
                DrugInteraction(
                    drug_a=a,
                    drug_b=b,
                    severity=severity,
                    description=(
                        f"OpenFDA FAERS co-reporting for {a} + {b}: {total} reports. "
                        f"Top reaction: {top_reaction}. Note: Co-reporting indicates correlation, "
                        f"not definitive causation. Verify with clinical guidelines."
                    ),
                )
            )
    return DrugInteractionResponse(medications_checked=meds, interactions=interactions, has_critical=has_critical)


def _resolve_rxcui(drug_name: str) -> Optional[str]:
    try:
        r = httpx.get(f"{_RXNORM_BASE}/rxcui.json", params={"name": drug_name}, timeout=5.0)
        r.raise_for_status()
        rxnorm_ids = r.json().get("idGroup", {}).get("rxnormId") or []
        return rxnorm_ids[0] if rxnorm_ids else None
    except Exception as exc:
        _log.warning("RxNorm rxcui lookup failed for %r: %s", drug_name, exc)
        return None


def _fetch_rxnorm_interactions(rxcuis: list[str]) -> Optional[dict]:
    if not rxcuis:
        return None
    # RxNorm docs/examples use '+'-delimited rxcuis; some gateways reject space-delimited values.
    candidates = ["+".join(rxcuis), ",".join(rxcuis)]
    for rxcuis_param in candidates:
        try:
            r = httpx.get(f"{_RXNORM_BASE}/interaction/list.json", params={"rxcuis": rxcuis_param}, timeout=10.0)
            r.raise_for_status()
            return r.json()
        except Exception as exc:
            _log.warning("RxNorm interaction list call failed for rxcuis=%r: %s", rxcuis_param, exc)
    return None


def _run_rxnorm_check(medications: List[str]) -> Optional[DrugInteractionResponse]:
    meds = [m.strip() for m in medications if m and m.strip()]
    if len(meds) < 2:
        return DrugInteractionResponse(medications_checked=meds, interactions=[], has_critical=False)
    rxcui_map: dict = {}
    for drug in meds:
        cui = _resolve_rxcui(drug)
        if cui:
            rxcui_map[drug] = cui
    if len(rxcui_map) < 2:
        return None
    data = _fetch_rxnorm_interactions(list(rxcui_map.values()))
    if data is None:
        return None
    interactions: List[DrugInteraction] = []
    seen_pairs: set = set()
    for group in data.get("fullInteractionTypeGroup") or []:
        source_name: str = group.get("sourceName", "")
        is_onc_high = "onc" in source_name.lower() or "high" in source_name.lower()
        for itype in group.get("fullInteractionType") or []:
            for pair in itype.get("interactionPair") or []:
                concepts = pair.get("interactionConcept") or []
                if len(concepts) < 2:
                    continue
                drug_a = concepts[0].get("minConceptItem", {}).get("name", "Unknown")
                drug_b = concepts[1].get("minConceptItem", {}).get("name", "Unknown")
                description: str = pair.get("description", "Drug interaction found.")
                pair_key = frozenset({drug_a.lower(), drug_b.lower()})
                if pair_key in seen_pairs:
                    continue
                seen_pairs.add(pair_key)
                desc_lower = description.lower()
                if is_onc_high or any(kw in desc_lower for kw in ("serious", "severe", "significant", "contraindicated")):
                    severity = "HIGH"
                else:
                    severity = "MODERATE"
                interactions.append(DrugInteraction(drug_a=drug_a.title(), drug_b=drug_b.title(), severity=severity, description=description))
    has_critical = any(ix.severity == "HIGH" for ix in interactions)
    return DrugInteractionResponse(medications_checked=meds, interactions=interactions, has_critical=has_critical)


def run_drug_interaction_check(medications: List[str]) -> DrugInteractionResponse:
    """Check all pairs for known interactions."""
    if settings.drug_interaction_source == "rxnorm":
        result = _run_rxnorm_check(medications)
        if result is not None:
            return result
        raise ToolError("Drug interaction source 'rxnorm' unavailable; no fallback data used.")
    if settings.drug_interaction_source == "openfda":
        result = _run_openfda_check(medications)
        if result is not None:
            return result
        raise ToolError("Drug interaction source 'openfda' unavailable; no fallback data used.")
    return _run_mock_check(medications)
