"""OpenEMR prescriptions access via MySQL."""
from typing import List, Callable, Any, Optional

from openemr_mcp.schemas import Medication
from openemr_mcp.repositories._errors import ToolError

DB_CONNECTION_ERROR_MSG = "OpenEMR database connection failed"


def _normalize_patient_id(patient_id_str: str) -> Optional[int]:
    s = (patient_id_str or "").strip().lower()
    if s.startswith("p"):
        s = s[1:]
    if not s:
        return None
    try:
        return int(s)
    except ValueError:
        return None


def get_medications(patient_id_str: str, get_connection: Callable[[], Any]) -> List[Medication]:
    """Fetch prescriptions for patient. Returns [] for bad/empty patient_id."""
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
            SELECT drug, dosage, unit, active
            FROM prescriptions
            WHERE patient_id = %s
            ORDER BY id
            LIMIT 100
        """
        cursor.execute(sql, (pid,))
        rows = cursor.fetchall()
        cursor.close()
        out = []
        for row in rows:
            drug_val, dosage_val, unit_val, active_val = row
            drug = (drug_val.strip() if drug_val else None) or "Unknown"
            dosage = dosage_val.strip() if dosage_val else None
            status = "active" if active_val == 1 else "inactive"
            out.append(Medication(drug=drug, dosage=dosage, status=status))
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
