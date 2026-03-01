"""
Drug interaction check tool.
DRUG_INTERACTION_SOURCE: mock (default) | rxnorm
"""
import logging
from typing import List, Optional

import httpx

from openemr_mcp.config import settings
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


def _resolve_rxcui(drug_name: str) -> Optional[str]:
    try:
        r = httpx.get(f"{_RXNORM_BASE}/rxcui.json", params={"name": drug_name, "allsrc": "0", "search": "1"}, timeout=5.0)
        r.raise_for_status()
        rxnorm_ids = r.json().get("idGroup", {}).get("rxnormId") or []
        return rxnorm_ids[0] if rxnorm_ids else None
    except Exception as exc:
        _log.warning("RxNorm rxcui lookup failed for %r: %s", drug_name, exc)
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
    rxcuis_param = " ".join(rxcui_map.values())
    try:
        r = httpx.get(f"{_RXNORM_BASE}/interaction/list.json", params={"rxcuis": rxcuis_param}, timeout=10.0)
        r.raise_for_status()
        data = r.json()
    except Exception as exc:
        _log.warning("RxNorm interaction list call failed: %s", exc)
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
        _log.warning("RxNorm check failed — falling back to mock")
    return _run_mock_check(medications)
