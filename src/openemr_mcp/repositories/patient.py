"""OpenEMR patient_data access via MySQL. Raises ToolError on connection failure."""

from collections.abc import Callable
from typing import Any

from openemr_mcp.repositories._errors import ToolError
from openemr_mcp.schemas import PatientMatch

DB_CONNECTION_ERROR_MSG = "OpenEMR database connection failed"


def get_openemr_connection():
    """Return a MySQL connection from settings. Raises ToolError on failure."""
    from openemr_mcp.config import settings

    try:
        import pymysql

        return pymysql.connect(
            host=settings.openemr_db_host,
            port=settings.openemr_db_port,
            user=settings.openemr_db_user,
            password=settings.openemr_db_password,
            database=settings.openemr_db_name,
        )
    except Exception:
        raise ToolError(DB_CONNECTION_ERROR_MSG)


def search_patients(query: str, get_connection: Callable[[], Any]) -> list[PatientMatch]:
    """Search patient_data by name with parameterized LIKE."""
    q = (query or "").strip()
    if not q:
        return []
    try:
        conn = get_connection()
    except Exception:
        raise ToolError(DB_CONNECTION_ERROR_MSG)
    try:
        cursor = conn.cursor()
        pattern = "%" + q + "%"
        sql = """
            SELECT pid, fname, lname, DOB, sex, city
            FROM patient_data
            WHERE fname LIKE %s OR lname LIKE %s OR CONCAT(COALESCE(fname,''), ' ', COALESCE(lname,'')) LIKE %s
            ORDER BY lname, fname
            LIMIT 50
        """
        cursor.execute(sql, (pattern, pattern, pattern))
        rows = cursor.fetchall()
        cursor.close()
        out = []
        for row in rows:
            pid_val = row[0]
            fname_val = row[1] or ""
            lname_val = row[2] or ""
            dob_val = str(row[3]) if row[3] is not None else None
            if dob_val and dob_val.startswith("0000-00-00"):
                dob_val = None
            sex_val = (row[4] or "").strip() or None
            city_val = (row[5] or "").strip() or None
            full_name = " ".join([fname_val, lname_val]).strip() or "Unknown"
            out.append(
                PatientMatch(
                    patient_id="p" + str(pid_val),
                    full_name=full_name,
                    dob=dob_val,
                    sex=sex_val,
                    city=city_val,
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


def get_patient_by_id(pid: int, get_connection: Callable[[], Any]) -> PatientMatch | None:
    """Fetch a single patient by OpenEMR integer pid. Returns None if not found."""
    try:
        conn = get_connection()
    except Exception:
        raise ToolError(DB_CONNECTION_ERROR_MSG)
    try:
        cursor = conn.cursor()
        sql = "SELECT pid, fname, lname, DOB, sex, city FROM patient_data WHERE pid = %s LIMIT 1"
        cursor.execute(sql, (pid,))
        row = cursor.fetchone()
        cursor.close()
        if not row:
            return None
        pid_val, fname_val, lname_val, dob_val, sex_val, city_val = row
        dob_str = str(dob_val) if dob_val else None
        if dob_str and dob_str.startswith("0000-00-00"):
            dob_str = None
        full_name = " ".join([fname_val or "", lname_val or ""]).strip() or "Unknown"
        return PatientMatch(
            patient_id="p" + str(pid_val),
            full_name=full_name,
            dob=dob_str,
            sex=(sex_val or "").strip() or None,
            city=(city_val or "").strip() or None,
        )
    except ToolError:
        raise
    except Exception:
        raise ToolError(DB_CONNECTION_ERROR_MSG)
    finally:
        try:
            conn.close()
        except Exception:
            pass
