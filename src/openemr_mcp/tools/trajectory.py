"""Health Trajectory tool: orchestrates lab, vital, and questionnaire trends + drift alerts."""

from datetime import datetime, timezone

from openemr_mcp.schemas import HealthTrajectoryResponse, MetricTrajectory
from openemr_mcp.services.trajectory_alerts import compute_drift_alerts
from openemr_mcp.tools.lab_trends import run_lab_trends
from openemr_mcp.tools.questionnaire import run_questionnaire_trends
from openemr_mcp.tools.vital_trends import run_vital_trends

ALL_METRICS = ["a1c", "ldl", "egfr", "weight", "bp_systolic", "bp_diastolic", "phq9"]
LAB_METRICS = ["a1c", "ldl", "egfr"]
VITAL_METRICS = ["weight", "bp_systolic", "bp_diastolic"]
QUESTIONNAIRE_METRICS = ["phq9"]


def run_health_trajectory(
    patient_id: str,
    window_months: int = 24,
    metrics: list[str] | None = None,
) -> HealthTrajectoryResponse:
    """Aggregate all metric trajectories and compute drift alerts."""
    target = set(metrics or ALL_METRICS)
    all_trajectories: list[MetricTrajectory] = []
    data_gaps: list[str] = []

    lab_targets = [m for m in LAB_METRICS if m in target]
    if lab_targets:
        try:
            lab_trajs = run_lab_trends(patient_id, metrics=lab_targets, window_months=window_months)
            for traj in lab_trajs:
                if not traj.points:
                    data_gaps.append(traj.metric)
                else:
                    all_trajectories.append(traj)
        except Exception:
            data_gaps.extend(lab_targets)

    vital_targets = [m for m in VITAL_METRICS if m in target]
    if vital_targets:
        try:
            vital_trajs = run_vital_trends(patient_id, metrics=vital_targets, window_months=window_months)
            for traj in vital_trajs:
                if not traj.points:
                    data_gaps.append(traj.metric)
                else:
                    all_trajectories.append(traj)
        except Exception:
            data_gaps.extend(vital_targets)

    if "phq9" in target:
        try:
            q_trajs = run_questionnaire_trends(patient_id, instrument="PHQ-9", window_months=window_months)
            for traj in q_trajs:
                if not traj.points:
                    data_gaps.append("phq9")
                else:
                    all_trajectories.append(traj)
        except Exception:
            data_gaps.append("phq9")

    alerts = compute_drift_alerts(all_trajectories)

    return HealthTrajectoryResponse(
        patient_id=patient_id,
        generated_at=datetime.now(timezone.utc).isoformat(),
        window_months=window_months,
        trajectories=all_trajectories,
        alerts=alerts,
        data_gaps=list(dict.fromkeys(data_gaps)),
    )
