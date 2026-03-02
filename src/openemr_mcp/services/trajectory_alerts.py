"""
Drift Alert Engine v1 — rule-based clinical deterioration detection.
Rules applied per MetricTrajectory. Each rule returns a DriftAlert or None.
"""

from datetime import datetime, timedelta, timezone

from openemr_mcp.schemas import DriftAlert, MetricTrajectory, TrajectoryPoint


def _phq9_band(score: float) -> str:
    if score <= 4:
        return "minimal"
    if score <= 9:
        return "mild"
    if score <= 14:
        return "moderate"
    if score <= 19:
        return "moderately_severe"
    return "severe"


def _points_in_last_n_months(points: list[TrajectoryPoint], n_months: int) -> list[TrajectoryPoint]:
    cutoff = datetime.now(timezone.utc) - timedelta(days=n_months * 30)
    cutoff_str = cutoff.strftime("%Y-%m-%d")
    return [p for p in points if p.effective_at[:10] >= cutoff_str]


def _baseline_value(points: list[TrajectoryPoint], baseline_months: int) -> float | None:
    cutoff = datetime.now(timezone.utc) - timedelta(days=baseline_months * 30)
    cutoff_str = cutoff.strftime("%Y-%m-%d")
    older = [p for p in points if p.effective_at[:10] <= cutoff_str]
    if not older:
        return None
    return sorted(older, key=lambda p: p.effective_at)[0].value


def _avg(values: list[float]) -> float | None:
    return sum(values) / len(values) if values else None


def _check_a1c(traj: MetricTrajectory) -> DriftAlert | None:
    if not traj.points:
        return None
    sorted_pts = sorted(traj.points, key=lambda p: p.effective_at)
    latest = sorted_pts[-1].value
    baseline = _baseline_value(sorted_pts, 6)
    if baseline is None:
        return None
    delta = latest - baseline
    if delta >= 0.5:
        return DriftAlert(
            metric="a1c",
            severity="high",
            title="HbA1c Worsening",
            rationale=f"HbA1c increased by {delta:.1f}% (from {baseline:.1f}% to {latest:.1f}%) over the past 6 months.",
            evidence_points=[p for p in sorted_pts if _points_in_last_n_months([p], 6)],
        )
    return None


def _check_ldl(traj: MetricTrajectory) -> DriftAlert | None:
    if not traj.points:
        return None
    sorted_pts = sorted(traj.points, key=lambda p: p.effective_at)
    latest = sorted_pts[-1].value
    baseline = _baseline_value(sorted_pts, 6)
    if baseline is None:
        return None
    delta = latest - baseline
    if delta >= 40:
        return DriftAlert(
            metric="ldl",
            severity="high",
            title="LDL Cholesterol Significantly Elevated",
            rationale=f"LDL increased by {delta:.0f} mg/dL (from {baseline:.0f} to {latest:.0f} mg/dL) over 6 months.",
            evidence_points=_points_in_last_n_months(sorted_pts, 6),
        )
    if delta >= 20:
        return DriftAlert(
            metric="ldl",
            severity="moderate",
            title="LDL Cholesterol Rising",
            rationale=f"LDL increased by {delta:.0f} mg/dL (from {baseline:.0f} to {latest:.0f} mg/dL) over 6 months.",
            evidence_points=_points_in_last_n_months(sorted_pts, 6),
        )
    return None


def _check_egfr(traj: MetricTrajectory) -> DriftAlert | None:
    if not traj.points:
        return None
    sorted_pts = sorted(traj.points, key=lambda p: p.effective_at)
    latest = sorted_pts[-1].value
    baseline = _baseline_value(sorted_pts, 6)
    decline_alert = False
    rationale_parts = []
    if baseline is not None:
        decline = baseline - latest
        if decline >= 5:
            decline_alert = True
            rationale_parts.append(
                f"eGFR declined by {decline:.1f} mL/min/1.73m² (from {baseline:.1f} to {latest:.1f}) over 6 months"
            )
    if latest < 60:
        recent = _points_in_last_n_months(sorted_pts, 6)
        if len(recent) >= 2 and recent[-1].value < recent[0].value:
            decline_alert = True
            rationale_parts.append(f"eGFR is {latest:.1f} (below CKD threshold of 60) with a downward trend")
    if decline_alert:
        return DriftAlert(
            metric="egfr",
            severity="high",
            title="eGFR Declining — Kidney Function Concern",
            rationale=". ".join(rationale_parts) + ".",
            evidence_points=_points_in_last_n_months(sorted_pts, 6),
        )
    return None


def _check_weight(traj: MetricTrajectory) -> DriftAlert | None:
    if not traj.points:
        return None
    sorted_pts = sorted(traj.points, key=lambda p: p.effective_at)
    latest = sorted_pts[-1].value
    baseline = _baseline_value(sorted_pts, 6)
    if baseline is None or baseline == 0:
        return None
    pct_change = abs((latest - baseline) / baseline) * 100
    if pct_change >= 5:
        direction = "gained" if latest > baseline else "lost"
        return DriftAlert(
            metric="weight",
            severity="moderate",
            title=f"Significant Weight Change ({direction.title()})",
            rationale=f"Patient {direction} {abs(latest - baseline):.1f} kg ({pct_change:.1f}%) over 6 months.",
            evidence_points=_points_in_last_n_months(sorted_pts, 6),
        )
    return None


def _check_bp(systolic_traj: MetricTrajectory | None, diastolic_traj: MetricTrajectory | None) -> list[DriftAlert]:
    alerts: list[DriftAlert] = []

    def _last_n_values(traj, n):
        if not traj or not traj.points:
            return []
        return [p.value for p in sorted(traj.points, key=lambda p: p.effective_at)[-n:]]

    def _last_n_pts(traj, n):
        if not traj or not traj.points:
            return []
        return sorted(traj.points, key=lambda p: p.effective_at)[-n:]

    sys_vals = _last_n_values(systolic_traj, 3)
    dia_vals = _last_n_values(diastolic_traj, 3)
    avg_sys = _avg(sys_vals)
    avg_dia = _avg(dia_vals)
    evidence = _last_n_pts(systolic_traj, 3) + _last_n_pts(diastolic_traj, 3)

    if avg_sys is not None and avg_sys >= 160:
        alerts.append(
            DriftAlert(
                metric="bp_systolic",
                severity="high",
                title="Severely Elevated Systolic Blood Pressure",
                rationale=f"Average systolic BP over last 3 readings is {avg_sys:.0f} mmHg (≥160 mmHg).",
                evidence_points=evidence,
            )
        )
    elif avg_sys is not None and avg_sys >= 140:
        alerts.append(
            DriftAlert(
                metric="bp_systolic",
                severity="moderate",
                title="Elevated Systolic Blood Pressure",
                rationale=f"Average systolic BP over last 3 readings is {avg_sys:.0f} mmHg (≥140 mmHg).",
                evidence_points=evidence,
            )
        )
    if avg_dia is not None and avg_dia >= 100:
        alerts.append(
            DriftAlert(
                metric="bp_diastolic",
                severity="high",
                title="Severely Elevated Diastolic Blood Pressure",
                rationale=f"Average diastolic BP over last 3 readings is {avg_dia:.0f} mmHg (≥100 mmHg).",
                evidence_points=evidence,
            )
        )
    elif avg_dia is not None and avg_dia >= 90:
        alerts.append(
            DriftAlert(
                metric="bp_diastolic",
                severity="moderate",
                title="Elevated Diastolic Blood Pressure",
                rationale=f"Average diastolic BP over last 3 readings is {avg_dia:.0f} mmHg (≥90 mmHg).",
                evidence_points=evidence,
            )
        )
    return alerts


def _check_phq9(traj: MetricTrajectory) -> DriftAlert | None:
    if not traj.points:
        return None
    sorted_pts = sorted(traj.points, key=lambda p: p.effective_at)
    latest = sorted_pts[-1].value
    baseline = _baseline_value(sorted_pts, 6)
    if baseline is None:
        return None
    delta = latest - baseline
    latest_band = _phq9_band(latest)
    baseline_band = _phq9_band(baseline)
    if latest_band == "severe" and baseline_band != "severe":
        return DriftAlert(
            metric="phq9",
            severity="high",
            title="PHQ-9 Score Entered Severe Range",
            rationale=f"PHQ-9 score increased from {baseline:.0f} ({baseline_band}) to {latest:.0f} ({latest_band}). Immediate clinical review recommended.",
            evidence_points=_points_in_last_n_months(sorted_pts, 6),
        )
    if delta >= 5:
        return DriftAlert(
            metric="phq9",
            severity="moderate",
            title="PHQ-9 Score Worsening",
            rationale=f"PHQ-9 score increased by {delta:.0f} points (from {baseline:.0f} to {latest:.0f}) over 6 months.",
            evidence_points=_points_in_last_n_months(sorted_pts, 6),
        )
    return None


def compute_drift_alerts(trajectories: list[MetricTrajectory]) -> list[DriftAlert]:
    """Apply all drift rules to a list of MetricTrajectory objects. Returns alerts sorted by severity."""
    alerts: list[DriftAlert] = []
    traj_by_metric: dict = {t.metric: t for t in trajectories}
    for metric, check_fn in [
        ("a1c", _check_a1c),
        ("ldl", _check_ldl),
        ("egfr", _check_egfr),
        ("weight", _check_weight),
    ]:
        if metric in traj_by_metric:
            alert = check_fn(traj_by_metric[metric])
            if alert:
                alerts.append(alert)
    alerts.extend(_check_bp(traj_by_metric.get("bp_systolic"), traj_by_metric.get("bp_diastolic")))
    if "phq9" in traj_by_metric:
        alert = _check_phq9(traj_by_metric["phq9"])
        if alert:
            alerts.append(alert)
    _severity_order = {"high": 0, "moderate": 1, "info": 2}
    alerts.sort(key=lambda a: _severity_order.get(a.severity, 99))
    return alerts
