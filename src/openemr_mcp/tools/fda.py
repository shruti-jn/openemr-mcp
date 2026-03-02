"""FDA drug safety tools — adverse events and drug labels."""

import logging

from openemr_mcp.repositories._errors import ToolError
from openemr_mcp.schemas import FDAAdverseEventSummary, FDADrugLabelResult
from openemr_mcp.services.openfda_client import get_adverse_events, get_drug_label
from openemr_mcp.services.safety import sanitize_drug_name

_log = logging.getLogger("openemr_mcp")


def run_fda_adverse_events(drug_name: str, limit: int = 5) -> FDAAdverseEventSummary:
    """Query FDA FAERS for adverse event reports on a drug."""
    if not drug_name or not drug_name.strip():
        return FDAAdverseEventSummary(drug_name="", total_reports=0, serious_reports=0, top_reactions=[])
    try:
        safe_name = sanitize_drug_name(drug_name)
    except ValueError as exc:
        _log.warning("fda_adverse_events rejected drug_name %r: %s", drug_name, exc)
        raise ToolError(f"Invalid drug name: {exc}") from exc
    return get_adverse_events(safe_name, limit=limit)


def run_fda_drug_label(drug_name: str) -> FDADrugLabelResult:
    """Query FDA drug label database for official prescribing information."""
    if not drug_name or not drug_name.strip():
        return FDADrugLabelResult(drug_name="")
    try:
        safe_name = sanitize_drug_name(drug_name)
    except ValueError as exc:
        _log.warning("fda_drug_label rejected drug_name %r: %s", drug_name, exc)
        raise ToolError(f"Invalid drug name: {exc}") from exc
    return get_drug_label(safe_name)
