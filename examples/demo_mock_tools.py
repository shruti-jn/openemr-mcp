#!/usr/bin/env python3
"""
Demo script showing how to call openemr-mcp tools directly in mock mode.

No external services required — all data comes from built-in mock fixtures.

Usage:
    pip install -e .
    python examples/demo_mock_tools.py
"""

import json
import os
import sys
from pathlib import Path

# Force mock mode
os.environ["OPENEMR_DATA_SOURCE"] = "mock"
os.environ["DRUG_INTERACTION_SOURCE"] = "mock"
os.environ["SYMPTOM_SOURCE"] = "mock"
os.environ["OPENFDA_SOURCE"] = "mock"

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))


def pp(label: str, obj):
    """Pretty-print a result."""
    print(f"\n{'=' * 60}")
    print(f"  {label}")
    print(f"{'=' * 60}")
    if hasattr(obj, "model_dump"):
        print(json.dumps(obj.model_dump(), indent=2, default=str))
    elif isinstance(obj, list):
        for item in obj:
            if hasattr(item, "model_dump"):
                print(json.dumps(item.model_dump(), indent=2, default=str))
            else:
                print(json.dumps(item, indent=2, default=str))
    else:
        print(obj)


def main():
    # --- Patient search ---
    from openemr_mcp.tools.patient import run_patient_search

    patients = run_patient_search("John")
    pp("Patient search for 'John'", patients)

    if not patients:
        print("No patients found. Exiting.")
        return

    pid = patients[0].patient_id

    # --- Appointments ---
    from openemr_mcp.tools.appointments import run_appointment_list

    appts = run_appointment_list(pid)
    pp(f"Appointments for {pid}", appts)

    # --- Medications ---
    from openemr_mcp.tools.medications import run_medication_list

    meds = run_medication_list(pid)
    pp(f"Medications for {pid}", meds)

    # --- Drug interactions ---
    from openemr_mcp.tools.drug_interactions import run_drug_interaction_check

    interactions = run_drug_interaction_check(["lisinopril", "metformin"])
    pp("Drug interactions: lisinopril + metformin", interactions)

    # --- Symptom lookup ---
    from openemr_mcp.tools.symptoms import run_symptom_lookup

    symptoms = run_symptom_lookup(["headache", "fatigue"])
    pp("Symptom lookup: headache + fatigue", symptoms)

    # --- FDA adverse events ---
    from openemr_mcp.tools.fda import run_fda_adverse_events

    fda = run_fda_adverse_events("lisinopril", limit=3)
    pp("FDA adverse events: lisinopril", fda)

    # --- Health trajectory ---
    from openemr_mcp.tools.trajectory import run_health_trajectory

    trajectory = run_health_trajectory(pid, window_months=6)
    pp(f"Health trajectory for {pid}", trajectory)

    # --- Visit prep ---
    from openemr_mcp.tools.visit_prep import run_visit_prep

    prep = run_visit_prep(pid)
    pp(f"Visit prep for {pid}", prep)

    print(f"\n{'=' * 60}")
    print("  Demo complete.")
    print(f"{'=' * 60}\n")


if __name__ == "__main__":
    main()
