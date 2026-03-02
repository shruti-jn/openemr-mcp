"""OpenEMR appointment access via MySQL."""

import datetime as dt
from collections.abc import Callable
from typing import Any

from openemr_mcp.repositories._errors import ToolError
from openemr_mcp.schemas import Appointment

DB_CONNECTION_ERROR_MSG = "OpenEMR database connection failed"


def _normalize_patient_id(patient_id_str: str) -> int | None:
    s = (patient_id_str or "").strip().lower()
    if s.startswith("p"):
        s = s[1:]
    if not s:
        return None
    try:
        return int(s)
    except ValueError:
        return None


def get_appointments(patient_id_str: str, get_connection: Callable[[], Any]) -> list[Appointment]:
    """Fetch appointments from openemr_postcalendar_events. Returns [] for bad patient_id."""
    pid = _normalize_patient_id(patient_id_str)
    if pid is None:
        return []
    try:
        conn = get_connection()
    except Exception:
        raise ToolError(DB_CONNECTION_ERROR_MSG)
    try:
        cursor = conn.cursor()
        sql = """
            SELECT e.pc_eid, e.pc_pid, e.pc_eventDate, e.pc_startTime,
                   e.pc_title, e.pc_aid, u.fname, u.lname
            FROM openemr_postcalendar_events e
            LEFT JOIN users u ON u.id = e.pc_aid
            WHERE e.pc_pid = %s
            ORDER BY e.pc_eventDate, e.pc_startTime
            LIMIT 100
        """
        cursor.execute(sql, (pid,))
        rows = cursor.fetchall()
        cursor.close()
        out = []
        for row in rows:
            pc_eid, pc_pid, pc_event_date, pc_start_time, pc_title, pc_aid, fname, lname = row
            appointment_id = "a" + str(pc_eid)
            patient_id = "p" + str(pc_pid)
            start_time: str | None = None
            if pc_event_date:
                date_str = str(pc_event_date)[:10]
                if pc_start_time is not None:
                    if isinstance(pc_start_time, dt.timedelta):
                        total_seconds = int(pc_start_time.total_seconds())
                        hours, remainder = divmod(total_seconds, 3600)
                        minutes, seconds = divmod(remainder, 60)
                        time_str = f"{hours:02d}:{minutes:02d}:{seconds:02d}"
                    else:
                        time_str = str(pc_start_time)
                    start_time = f"{date_str}T{time_str}"
                else:
                    start_time = f"{date_str}T00:00:00"
            reason = (pc_title or "").strip() or None
            provider_id: str | None = None
            provider_name: str | None = None
            if pc_aid:
                provider_id = "prov" + str(pc_aid)
                name_parts = [n for n in [(fname or "").strip(), (lname or "").strip()] if n]
                if name_parts:
                    provider_name = "Dr. " + " ".join(name_parts)
            out.append(
                Appointment(
                    appointment_id=appointment_id,
                    patient_id=patient_id,
                    start_time=start_time or "",
                    reason=reason,
                    provider_id=provider_id,
                    provider_name=provider_name,
                )
            )
        return out
    except ToolError:
        raise
    except Exception:
        raise ToolError(DB_CONNECTION_ERROR_MSG)
    finally:
        try:
            conn.close()
        except Exception:
            pass
