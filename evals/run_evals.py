#!/usr/bin/env python3
"""
openemr-mcp evaluation runner.

Executes all cases in eval_cases.json against mock mode and reports pass/fail
with per-case latency. Exits non-zero if any case fails.

Usage:
    python evals/run_evals.py                     # all cases
    python evals/run_evals.py --tag safety        # only safety-tagged cases
    python evals/run_evals.py --id vp_001         # single case
"""

import argparse
import inspect
import json
import os
import sys
import time
from pathlib import Path
from typing import Any

# Force mock mode for all evals
os.environ.setdefault("OPENEMR_DATA_SOURCE", "mock")
os.environ.setdefault("DRUG_INTERACTION_SOURCE", "mock")
os.environ.setdefault("SYMPTOM_SOURCE", "mock")
os.environ.setdefault("OPENFDA_SOURCE", "mock")

# Ensure src is on the path when running from the repo root
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

CASES_PATH = Path(__file__).parent / "eval_cases.json"


# ---------------------------------------------------------------------------
# Tool dispatch
# ---------------------------------------------------------------------------


def _prepare_eval_drug_safety_db() -> None:
    """Point drug safety SQLite to a writable eval-local file."""
    import openemr_mcp.repositories.drug_safety as ds_repo

    eval_db_dir = Path(__file__).parent / ".eval_tmp"
    eval_db_dir.mkdir(parents=True, exist_ok=True)
    ds_repo._DB_PATH = eval_db_dir / "drug_safety_flags.db"
    ds_repo._conn = None


def _dispatch(tool: str, inp: dict) -> Any:
    if tool == "patient_search":
        from openemr_mcp.tools.patient import run_patient_search

        return run_patient_search(**inp)
    if tool == "patient_by_id":
        from openemr_mcp.tools.patient import run_get_patient_by_id

        return run_get_patient_by_id(**inp)
    if tool == "appointment_list":
        from openemr_mcp.tools.appointments import run_appointment_list

        return run_appointment_list(**inp)
    if tool == "medication_list":
        from openemr_mcp.tools.medications import run_medication_list

        return run_medication_list(**inp)
    if tool == "drug_interaction_check":
        from openemr_mcp.tools.drug_interactions import run_drug_interaction_check

        return run_drug_interaction_check(**inp)
    if tool == "provider_search":
        from openemr_mcp.tools.providers import run_provider_search

        return run_provider_search(**inp)
    if tool == "fda_adverse_events":
        from openemr_mcp.tools.fda import run_fda_adverse_events

        return run_fda_adverse_events(**inp)
    if tool == "fda_drug_label":
        from openemr_mcp.tools.fda import run_fda_drug_label

        return run_fda_drug_label(**inp)
    if tool == "symptom_lookup":
        from openemr_mcp.tools.symptoms import run_symptom_lookup

        return run_symptom_lookup(**inp)
    if tool == "lab_trends":
        from openemr_mcp.tools.lab_trends import run_lab_trends

        return run_lab_trends(**inp)
    if tool == "vital_trends":
        from openemr_mcp.tools.vital_trends import run_vital_trends

        return run_vital_trends(**inp)
    if tool == "questionnaire_trends":
        from openemr_mcp.tools.questionnaire import run_questionnaire_trends

        return run_questionnaire_trends(**inp)
    if tool == "health_trajectory":
        from openemr_mcp.tools.trajectory import run_health_trajectory

        return run_health_trajectory(**inp)
    if tool == "visit_prep":
        from openemr_mcp.tools.visit_prep import run_visit_prep

        return run_visit_prep(**inp)
    if tool == "drug_safety_flag_create":
        _prepare_eval_drug_safety_db()
        from openemr_mcp.tools.drug_safety import run_create_drug_safety_flag

        return run_create_drug_safety_flag(**inp)
    if tool == "drug_safety_flag_list":
        _prepare_eval_drug_safety_db()
        from openemr_mcp.tools.drug_safety import run_get_drug_safety_flags

        return run_get_drug_safety_flags(**inp)
    if tool == "auth_interface":
        return None  # checked in assertions
    if tool == "data_source_contract":
        return None  # checked in assertions
    if tool == "config_env_contract":
        return None  # checked in assertions
    if tool == "no_fabrication_contract":
        return None  # checked in assertions
    raise ValueError(f"Unknown tool: {tool!r}")


# ---------------------------------------------------------------------------
# Assertion engine
# ---------------------------------------------------------------------------


def _get_attr(obj: Any, field: str) -> Any:
    """Return obj.field or obj[field], whichever exists."""
    try:
        return getattr(obj, field)
    except AttributeError:
        pass
    try:
        return obj[field]
    except (KeyError, TypeError):
        pass
    return None


def _check(result: Any, expect: dict, tool: str) -> list[str]:
    """Return list of failure messages (empty = all passed)."""
    failures = []

    # ---------- special contract checks ----------
    if tool == "auth_interface":
        from openemr_mcp.auth import OAuth2TokenManager

        m = expect.get("method_exists")
        if m and not callable(getattr(OAuth2TokenManager, m, None)):
            failures.append(f"OAuth2TokenManager missing method: {m}")
        absent = expect.get("method_absent")
        if absent and hasattr(OAuth2TokenManager, absent):
            failures.append(f"OAuth2TokenManager must not expose: {absent}")
        return failures

    if tool == "data_source_contract":
        from openemr_mcp import data_source

        src = inspect.getsource(data_source)
        contains = expect.get("source_contains")
        if contains and contains not in src:
            failures.append(f"data_source source missing: {contains!r}")
        not_contains = expect.get("source_not_contains")
        if not_contains and not_contains in src:
            failures.append(f"data_source source must not contain: {not_contains!r}")
        return failures

    if tool == "config_env_contract":
        from openemr_mcp import config

        src = inspect.getsource(config)
        env_var = expect.get("env_var_read")
        if env_var and env_var not in src:
            failures.append(f"config.py does not read env var: {env_var!r}")
        return failures

    if tool == "no_fabrication_contract":
        from openemr_mcp.services import openfda_client
        from openemr_mcp.tools import drug_interactions, symptoms

        checks = [
            ("drug_interactions.py", inspect.getsource(drug_interactions)),
            ("symptoms.py", inspect.getsource(symptoms)),
            ("openfda_client.py", inspect.getsource(openfda_client)),
        ]
        target_modules = set(expect.get("target_modules") or [])
        if target_modules:
            checks = [(label, src) for (label, src) in checks if label in target_modules]

        required = expect.get("source_contains") or []
        forbidden = expect.get("source_not_contains") or []

        for label, src in checks:
            for token in required:
                if token not in src:
                    failures.append(f"{label} source missing: {token!r}")
            for token in forbidden:
                if token in src:
                    failures.append(f"{label} source must not contain: {token!r}")
        return failures

    # ---------- standard result checks ----------
    if expect.get("is_none") and result is not None:
        failures.append(f"Expected None, got {type(result).__name__}")
        return failures

    if expect.get("not_none") and result is None:
        failures.append("Expected non-None result, got None")
        return failures

    if expect.get("result_type") == "list" and not isinstance(result, list):
        failures.append(f"Expected list, got {type(result).__name__}")

    if "result_count" in expect:
        count = len(result) if isinstance(result, list) else -1
        if count != expect["result_count"]:
            failures.append(f"Expected {expect['result_count']} results, got {count}")

    if "min_results" in expect:
        count = len(result) if isinstance(result, list) else -1
        if count < expect["min_results"]:
            failures.append(f"Expected >= {expect['min_results']} results, got {count}")

    if "fields" in expect:
        if isinstance(result, list):
            item = result[0] if result else None
        else:
            item = result
        if item is not None:
            for f in expect["fields"]:
                if _get_attr(item, f) is None:
                    failures.append(f"Missing field: {f!r}")

    if "first_medication_fields" in expect:
        meds = _get_attr(result, "medications") or []
        med = meds[0] if meds else None
        if med is None:
            failures.append("No medications to check fields on")
        else:
            for f in expect["first_medication_fields"]:
                if _get_attr(med, f) is None:
                    failures.append(f"Medication missing field: {f!r}")

    if "brief_fields" in expect:
        brief = _get_attr(result, "brief")
        if brief is not None:
            for f in expect["brief_fields"]:
                if _get_attr(brief, f) is None:
                    failures.append(f"brief missing field: {f!r}")

    if "metadata_fields" in expect:
        meta = _get_attr(result, "metadata")
        if meta is not None:
            for f in expect["metadata_fields"]:
                if _get_attr(meta, f) is None:
                    failures.append(f"metadata missing field: {f!r}")

    if "has_critical" in expect:
        val = _get_attr(result, "has_critical")
        if val is None:
            failures.append("Missing has_critical field")
        elif val != expect["has_critical"]:
            failures.append(f"has_critical: expected {expect['has_critical']}, got {val}")

    if "min_interactions" in expect:
        interactions = _get_attr(result, "interactions") or []
        if len(interactions) < expect["min_interactions"]:
            failures.append(f"Expected >= {expect['min_interactions']} interactions, got {len(interactions)}")

    if "interaction_count" in expect:
        interactions = _get_attr(result, "interactions") or []
        if len(interactions) != expect["interaction_count"]:
            failures.append(f"Expected {expect['interaction_count']} interactions, got {len(interactions)}")

    if "urgency_level" in expect:
        ul = _get_attr(result, "urgency_level")
        if ul != expect["urgency_level"]:
            failures.append(f"urgency_level: expected {expect['urgency_level']!r}, got {ul!r}")

    if "urgency_in" in expect:
        ul = _get_attr(result, "urgency_level")
        if ul not in expect["urgency_in"]:
            failures.append(f"urgency_level {ul!r} not in {expect['urgency_in']}")

    if "has_disclaimer" in expect:
        disc = _get_attr(result, "disclaimer")
        if not disc:
            failures.append("Missing or empty disclaimer")

    if "min_conditions" in expect:
        conds = _get_attr(result, "possible_conditions") or []
        if len(conds) < expect["min_conditions"]:
            failures.append(f"Expected >= {expect['min_conditions']} conditions, got {len(conds)}")

    if "each_has_points" in expect and isinstance(result, list):
        for i, traj in enumerate(result):
            pts = _get_attr(traj, "points")
            if not pts:
                failures.append(f"Trajectory[{i}] has no points")

    if "metric_names_include" in expect and isinstance(result, list):
        metric_names = [_get_attr(t, "metric") for t in result]
        for m in expect["metric_names_include"]:
            if m not in metric_names:
                failures.append(f"Metric {m!r} not in result metrics {metric_names}")

    if "all_metric" in expect and isinstance(result, list):
        for traj in result:
            if _get_attr(traj, "metric") != expect["all_metric"]:
                failures.append(f"Expected all metrics to be {expect['all_metric']!r}")

    if "trajectories_is_list" in expect:
        trajs = _get_attr(result, "trajectories")
        if not isinstance(trajs, list):
            failures.append("trajectories field is not a list")

    if "patient_id" in expect:
        pid = _get_attr(result, "patient_id") or _get_attr(_get_attr(result, "metadata"), "patient_id")
        if pid != expect["patient_id"]:
            failures.append(f"patient_id: expected {expect['patient_id']!r}, got {pid!r}")

    if "severity" in expect:
        sev = _get_attr(result, "severity")
        if sev != expect["severity"]:
            failures.append(f"severity: expected {expect['severity']!r}, got {sev!r}")

    if "specialty_queried" in expect:
        sq = _get_attr(result, "specialty_queried")
        if sq != expect["specialty_queried"]:
            failures.append(f"specialty_queried: expected {expect['specialty_queried']!r}, got {sq!r}")

    if "min_providers" in expect:
        provs = _get_attr(result, "providers") or []
        if len(provs) < expect["min_providers"]:
            failures.append(f"Expected >= {expect['min_providers']} providers, got {len(provs)}")

    if "min_total_reports" in expect:
        tr = _get_attr(result, "total_reports")
        if tr is None or tr < expect["min_total_reports"]:
            failures.append(f"total_reports: expected >= {expect['min_total_reports']}, got {tr}")

    if "min_medications" in expect:
        meds = _get_attr(result, "medications") or []
        if len(meds) < expect["min_medications"]:
            failures.append(f"Expected >= {expect['min_medications']} medications, got {len(meds)}")

    if "medication_count" in expect:
        meds = _get_attr(result, "medications") or []
        if len(meds) != expect["medication_count"]:
            failures.append(f"Expected {expect['medication_count']} medications, got {len(meds)}")

    return failures


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------


def run_cases(cases: list[dict], verbose: bool = False) -> tuple[int, int, list[dict]]:
    passed = 0
    failed = 0
    results = []

    for case in cases:
        cid = case["id"]
        tool = case["tool"]
        inp = case.get("input", {})
        expect = case.get("expect", {})
        desc = case.get("description", "")

        t0 = time.perf_counter()
        error: str | None = None
        result = None
        try:
            result = _dispatch(tool, inp)
        except Exception as exc:
            error = f"{type(exc).__name__}: {exc}"
        elapsed_ms = (time.perf_counter() - t0) * 1000

        if error:
            failures = [f"Tool raised exception: {error}"]
        else:
            failures = _check(result, expect, tool)

        ok = len(failures) == 0
        status = "PASS" if ok else "FAIL"
        if ok:
            passed += 1
        else:
            failed += 1

        row = {
            "id": cid,
            "tool": tool,
            "status": status,
            "latency_ms": round(elapsed_ms, 2),
            "failures": failures,
            "description": desc,
        }
        results.append(row)

        icon = "✓" if ok else "✗"
        msg = f"  {icon} [{cid}] {desc} ({elapsed_ms:.1f}ms)"
        if not ok:
            for f in failures:
                msg += f"\n      → {f}"
        print(msg)

    return passed, failed, results


def main():
    parser = argparse.ArgumentParser(description="openemr-mcp eval runner")
    parser.add_argument("--tag", help="Only run cases with this tag")
    parser.add_argument("--id", help="Only run the case with this ID")
    parser.add_argument("--json", action="store_true", help="Output results as JSON")
    args = parser.parse_args()

    with open(CASES_PATH) as f:
        all_cases = json.load(f)

    cases = all_cases
    if args.tag:
        cases = [c for c in cases if args.tag in c.get("tags", [])]
    if args.id:
        cases = [c for c in cases if c["id"] == args.id]

    if not cases:
        print("No cases matched filters.")
        sys.exit(0)

    print(f"\nopenemr-mcp eval runner — {len(cases)} cases\n")
    passed, failed, results = run_cases(cases)

    total = passed + failed
    latencies = [r["latency_ms"] for r in results if r["status"] == "PASS"]
    avg_ms = sum(latencies) / len(latencies) if latencies else 0
    p99_ms = sorted(latencies)[int(len(latencies) * 0.99) - 1] if latencies else 0

    print(f"\n{'─' * 60}")
    print(f"  Results : {passed}/{total} passed  ({failed} failed)")
    print(f"  Avg latency (passing): {avg_ms:.1f}ms")
    print(f"  P99 latency (passing): {p99_ms:.1f}ms")
    print(f"{'─' * 60}\n")

    if args.json:
        print(json.dumps(results, indent=2))

    sys.exit(0 if failed == 0 else 1)


if __name__ == "__main__":
    main()
