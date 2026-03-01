"""DB-mode repository for health trajectory data."""
from typing import List, Optional, Any
from datetime import datetime

from openemr_mcp.schemas import TrajectoryPoint

LAB_CODE_ALIASES: dict = {
    "a1c": ["4548-4", "4549-2", "17856-6", "HBA1C", "A1C"],
    "ldl": ["13457-7", "18262-6", "2089-1", "LDL", "LDL-C"],
    "egfr": ["33914-3", "62238-1", "EGFR", "GFR"],
}


def _normalize_pid(patient_id_str: str) -> Optional[int]:
    s = (patient_id_str or "").strip().lower()
    if s.startswith("p"):
        s = s[1:]
    try:
        return int(s)
    except (ValueError, TypeError):
        return None


def _to_iso(dt_val: Any) -> str:
    if dt_val is None:
        return ""
    if isinstance(dt_val, datetime):
        return dt_val.isoformat()
    return str(dt_val)


def _code_to_metric(code_upper: str) -> Optional[str]:
    for metric, aliases in LAB_CODE_ALIASES.items():
        if code_upper in {a.upper() for a in aliases}:
            return metric
    return None


def _default_unit(metric: str) -> str:
    defaults = {
        "a1c": "%", "ldl": "mg/dL", "egfr": "mL/min/1.73m²",
        "weight": "kg", "bp_systolic": "mmHg", "bp_diastolic": "mmHg", "phq9": "score",
    }
    return defaults.get(metric, "")


def get_vitals_trends_db(patient_id_str: str, from_date: str, get_connection: Any) -> List[TrajectoryPoint]:
    """Query form_vitals for bp and weight since from_date."""
    pid = _normalize_pid(patient_id_str)
    if pid is None:
        return []
    sql = """
        SELECT v.date, v.bps, v.bpd, v.weight
        FROM form_vitals v
        JOIN forms f ON f.form_id = v.id
        WHERE v.pid = %s AND f.deleted != 1 AND v.date >= %s
        ORDER BY v.date ASC
    """
    points: List[TrajectoryPoint] = []
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute(sql, (pid, from_date))
        rows = cursor.fetchall()
        cursor.close()
    except Exception:
        return []
    for row in rows:
        date_val, bps, bpd, weight = row
        effective = _to_iso(date_val)
        if bps is not None:
            try:
                points.append(TrajectoryPoint(metric="bp_systolic", value=float(bps), unit="mmHg", effective_at=effective, source="form_vitals"))
            except (ValueError, TypeError):
                pass
        if bpd is not None:
            try:
                points.append(TrajectoryPoint(metric="bp_diastolic", value=float(bpd), unit="mmHg", effective_at=effective, source="form_vitals"))
            except (ValueError, TypeError):
                pass
        if weight is not None:
            try:
                points.append(TrajectoryPoint(metric="weight", value=float(weight), unit="kg", effective_at=effective, source="form_vitals"))
            except (ValueError, TypeError):
                pass
    return points


def get_lab_trends_db(patient_id_str: str, from_date: str, result_code_filters: Optional[List[str]], get_connection: Any) -> List[TrajectoryPoint]:
    """Query procedure_result for lab results since from_date."""
    pid = _normalize_pid(patient_id_str)
    if pid is None:
        return []
    sql = """
        SELECT COALESCE(NULLIF(pr.date, '0000-00-00 00:00:00'), rep.date_collected) AS effective_date,
               pr.result_code, pr.result, pr.units
        FROM procedure_result pr
        JOIN procedure_report rep ON rep.procedure_report_id = pr.procedure_report_id
        JOIN procedure_order ord ON ord.procedure_order_id = rep.procedure_order_id
        WHERE ord.patient_id = %s
          AND COALESCE(NULLIF(pr.date, '0000-00-00 00:00:00'), rep.date_collected) >= %s
        ORDER BY effective_date ASC
    """
    points: List[TrajectoryPoint] = []
    accepted: Optional[set] = None
    if result_code_filters is not None:
        accepted = {c.upper() for c in result_code_filters}
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute(sql, (pid, from_date))
        rows = cursor.fetchall()
        cursor.close()
    except Exception:
        return []
    for row in rows:
        date_val, result_code, result_val, units = row
        code_upper = (result_code or "").strip().upper()
        if accepted is not None and code_upper not in accepted:
            continue
        metric = _code_to_metric(code_upper)
        if metric is None:
            continue
        try:
            value = float(result_val)
        except (ValueError, TypeError):
            continue
        points.append(TrajectoryPoint(
            metric=metric, value=value,
            unit=str(units or "").strip() or _default_unit(metric),
            effective_at=_to_iso(date_val),
            source="procedure_result", code=result_code,
        ))
    return points


def get_questionnaire_trends_db(patient_id_str: str, from_date: str, questionnaire_name_filters: Optional[List[str]], get_connection: Any) -> List[TrajectoryPoint]:
    """Query questionnaire_response for PHQ-9 or other instruments."""
    pid = _normalize_pid(patient_id_str)
    if pid is None:
        return []
    sql = """
        SELECT create_time, questionnaire_name, form_score
        FROM questionnaire_response
        WHERE patient_id = %s AND create_time >= %s AND questionnaire_name LIKE %s
        ORDER BY create_time ASC
    """
    points: List[TrajectoryPoint] = []
    name_patterns = questionnaire_name_filters or ["%PHQ%"]
    try:
        conn = get_connection()
        cursor = conn.cursor()
        for pattern in name_patterns:
            like_pattern = f"%{pattern}%" if "%" not in pattern else pattern
            cursor.execute(sql, (pid, from_date, like_pattern))
            for row in cursor.fetchall():
                create_time, q_name, form_score = row
                try:
                    value = float(form_score)
                except (ValueError, TypeError):
                    continue
                points.append(TrajectoryPoint(metric="phq9", value=value, unit="score", effective_at=_to_iso(create_time), source="questionnaire_response"))
        cursor.close()
    except Exception:
        return []
    points.sort(key=lambda p: p.effective_at)
    return points
