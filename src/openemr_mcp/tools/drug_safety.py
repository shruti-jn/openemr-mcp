"""Drug Safety Flag tools — CRUD operations for patient-specific drug safety notes."""
import logging
import unicodedata
from typing import Optional

from openemr_mcp.repositories.drug_safety import (
    create_flag, get_flags, get_flag_by_id, update_flag, delete_flag,
)
from openemr_mcp.schemas import (
    DrugSafetyFlag, DrugSafetyFlagCreate, DrugSafetyFlagUpdate, DrugSafetyFlagListResponse,
)
from openemr_mcp.services.safety import sanitize_drug_name
from openemr_mcp.repositories._errors import ToolError

_log = logging.getLogger("openemr_mcp")
_MAX_DESCRIPTION_LEN = 1000


def _sanitize_description(text: str) -> str:
    if not text:
        return text
    cleaned = "".join(c for c in text.strip() if unicodedata.category(c)[0] != "C" or c in (" ", "\t"))
    return cleaned[:_MAX_DESCRIPTION_LEN]


def run_create_drug_safety_flag(
    patient_id: str, drug_name: str, description: str,
    flag_type: str = "adverse_event", severity: str = "MODERATE",
    source: str = "AGENT", created_by: str = "agent",
) -> DrugSafetyFlag:
    try:
        safe_drug_name = sanitize_drug_name(drug_name)
    except ValueError as exc:
        _log.warning("create_drug_safety_flag rejected drug_name %r: %s", drug_name, exc)
        raise ToolError(f"Invalid drug name: {exc}") from exc
    safe_description = _sanitize_description(description)
    payload = DrugSafetyFlagCreate(
        patient_id=patient_id, drug_name=safe_drug_name, description=safe_description,
        flag_type=flag_type, severity=severity, source=source, created_by=created_by,
    )
    return create_flag(payload)


def run_get_drug_safety_flags(patient_id: str, status_filter: Optional[str] = None) -> DrugSafetyFlagListResponse:
    return get_flags(patient_id, status_filter=status_filter)


def run_update_drug_safety_flag(
    flag_id: str, severity: Optional[str] = None,
    description: Optional[str] = None, status: Optional[str] = None,
) -> Optional[DrugSafetyFlag]:
    safe_description = _sanitize_description(description) if description is not None else None
    payload = DrugSafetyFlagUpdate(severity=severity, description=safe_description, status=status)
    return update_flag(flag_id, payload)


def run_delete_drug_safety_flag(flag_id: str) -> bool:
    return delete_flag(flag_id)
