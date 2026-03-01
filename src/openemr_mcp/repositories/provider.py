"""OpenEMR provider (user) access via MySQL."""
from typing import List, Callable, Any, Optional

from openemr_mcp.schemas import Provider
from openemr_mcp.repositories._errors import ToolError

DB_CONNECTION_ERROR_MSG = "OpenEMR database connection failed"


def search_providers(
    specialty: Optional[str],
    location: Optional[str],
    get_connection: Callable[[], Any],
) -> List[Provider]:
    """Search active, authorized providers by specialty and/or location."""
    spec = (specialty or "").strip() or None
    loc = (location or "").strip() or None
    spec_pattern = "%" + spec + "%" if spec else None
    loc_pattern = "%" + loc + "%" if loc else None
    try:
        conn = get_connection()
    except Exception:
        raise ToolError(DB_CONNECTION_ERROR_MSG)
    try:
        cursor = conn.cursor()
        sql = """
            SELECT id, fname, lname, specialty, facility
            FROM users
            WHERE active = 1 AND authorized = 1
              AND (%s IS NULL OR specialty LIKE %s)
              AND (%s IS NULL OR facility LIKE %s)
            ORDER BY lname, fname
            LIMIT 100
        """
        cursor.execute(sql, (spec_pattern, spec_pattern, loc_pattern, loc_pattern))
        rows = cursor.fetchall()
        cursor.close()
        out = []
        for row in rows:
            user_id, fname, lname, specialty_val, facility_val = row
            fname_s = (fname or "").strip()
            lname_s = (lname or "").strip()
            name_parts = [n for n in [fname_s, lname_s] if n]
            full_name = ("Dr. " + " ".join(name_parts)).strip() if name_parts else "Unknown"
            out.append(Provider(
                provider_id="prov" + str(user_id),
                full_name=full_name,
                specialty=(specialty_val or "").strip() or "General",
                location=(facility_val or "").strip(),
                accepting_new_patients=True,
            ))
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
