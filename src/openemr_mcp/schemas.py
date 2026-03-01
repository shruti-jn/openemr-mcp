"""All Pydantic schemas for openemr-mcp tools."""
from typing import List, Literal, Optional
from pydantic import BaseModel, Field, field_validator


# ---------------------------------------------------------------------------
# Patients
# ---------------------------------------------------------------------------

class PatientMatch(BaseModel):
    patient_id: str
    full_name: str
    dob: Optional[str] = None
    sex: Optional[str] = None
    city: Optional[str] = None


# ---------------------------------------------------------------------------
# Appointments
# ---------------------------------------------------------------------------

class Appointment(BaseModel):
    appointment_id: str
    patient_id: str
    start_time: str
    reason: Optional[str] = None
    provider_id: Optional[str] = None
    provider_name: Optional[str] = None


# ---------------------------------------------------------------------------
# Medications & Drug Interactions
# ---------------------------------------------------------------------------

class Medication(BaseModel):
    drug: str
    dosage: Optional[str] = None
    status: str  # "active" | "inactive"


class MedicationListResponse(BaseModel):
    patient_id: str
    medications: List[Medication]


class DrugInteraction(BaseModel):
    drug_a: str
    drug_b: str
    severity: Literal["HIGH", "MODERATE", "LOW"]
    description: str


class DrugInteractionResponse(BaseModel):
    medications_checked: List[str]
    interactions: List[DrugInteraction]
    has_critical: bool


# ---------------------------------------------------------------------------
# Providers
# ---------------------------------------------------------------------------

class Provider(BaseModel):
    provider_id: str
    full_name: str
    specialty: str
    location: str
    accepting_new_patients: bool


class ProviderSearchResponse(BaseModel):
    providers: List[Provider]
    specialty_queried: str = ""
    location_queried: str = ""


# ---------------------------------------------------------------------------
# Symptoms
# ---------------------------------------------------------------------------

class PossibleCondition(BaseModel):
    name: str
    likelihood: Literal["HIGH", "MODERATE", "LOW"]
    urgency: Literal["URGENT", "SEE_DOCTOR", "MONITOR"]


class SymptomLookupResponse(BaseModel):
    symptoms_checked: List[str]
    possible_conditions: List[PossibleCondition]
    urgency_level: Literal["URGENT", "SEE_DOCTOR", "MONITOR"]
    disclaimer: str


# ---------------------------------------------------------------------------
# Drug Safety Flags
# ---------------------------------------------------------------------------

class DrugSafetyFlag(BaseModel):
    id: str
    patient_id: str
    drug_name: str
    flag_type: Literal["adverse_event", "recall", "warning", "contraindication", "custom"]
    severity: Literal["HIGH", "MODERATE", "LOW"]
    source: Literal["FDA_FAERS", "FDA_LABEL", "FDA_RECALL", "CLINICIAN", "AGENT"]
    description: str
    status: Literal["active", "resolved", "under_review"] = "active"
    created_at: str
    updated_at: str
    created_by: str = "agent"


class DrugSafetyFlagCreate(BaseModel):
    patient_id: str = Field(..., min_length=1, max_length=50)
    drug_name: str = Field(..., min_length=1, max_length=200)
    flag_type: Literal["adverse_event", "recall", "warning", "contraindication", "custom"] = "adverse_event"
    severity: Literal["HIGH", "MODERATE", "LOW"] = "MODERATE"
    source: Literal["FDA_FAERS", "FDA_LABEL", "FDA_RECALL", "CLINICIAN", "AGENT"] = "AGENT"
    description: str = Field(..., min_length=1, max_length=1000)
    created_by: str = "agent"


class DrugSafetyFlagUpdate(BaseModel):
    severity: Optional[Literal["HIGH", "MODERATE", "LOW"]] = None
    description: Optional[str] = None
    status: Optional[Literal["active", "resolved", "under_review"]] = None


class DrugSafetyFlagListResponse(BaseModel):
    patient_id: str
    flags: List[DrugSafetyFlag]
    active_count: int
    high_severity_count: int


# ---------------------------------------------------------------------------
# FDA Drug Safety
# ---------------------------------------------------------------------------

class FDAAdverseEvent(BaseModel):
    reaction: str
    outcome: Optional[str] = None
    serious: bool = False
    report_count: int = 1


class FDAAdverseEventSummary(BaseModel):
    drug_name: str
    total_reports: int
    serious_reports: int
    top_reactions: List[FDAAdverseEvent]
    data_source: str = "FDA FAERS (OpenFDA)"
    disclaimer: str = (
        "This data is from FDA's Adverse Event Reporting System (FAERS). "
        "Reports are voluntary and may not reflect actual incidence rates. "
        "For clinical decisions, consult a licensed pharmacist or physician."
    )


class FDADrugLabelResult(BaseModel):
    drug_name: str
    brand_names: List[str] = []
    generic_name: Optional[str] = None
    boxed_warning: Optional[str] = None
    warnings: Optional[str] = None
    contraindications: Optional[str] = None
    indications_and_usage: Optional[str] = None
    manufacturer: Optional[str] = None
    data_source: str = "FDA Drug Label (OpenFDA)"
    has_boxed_warning: bool = False


# ---------------------------------------------------------------------------
# Trajectory / Health Trends
# ---------------------------------------------------------------------------

class TrajectoryPoint(BaseModel):
    metric: str
    value: float
    unit: str
    effective_at: str
    source: Literal[
        "fhir_observation",
        "form_vitals",
        "procedure_result",
        "questionnaire_response",
        "mock",
    ]
    code: Optional[str] = None


class MetricTrajectory(BaseModel):
    metric: str
    display_name: str
    unit: str
    window_months: int
    points: List[TrajectoryPoint]
    latest_value: Optional[float] = None
    previous_value: Optional[float] = None
    delta_abs: Optional[float] = None
    delta_pct: Optional[float] = None


class DriftAlert(BaseModel):
    metric: str
    severity: Literal["info", "moderate", "high"]
    title: str
    rationale: str
    evidence_points: List[TrajectoryPoint] = Field(default_factory=list)


class HealthTrajectoryResponse(BaseModel):
    patient_id: str
    generated_at: str
    window_months: int
    trajectories: List[MetricTrajectory]
    alerts: List[DriftAlert]
    data_gaps: List[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Visit Prep
# ---------------------------------------------------------------------------

class EvidenceItem(BaseModel):
    evidence_id: str = Field(..., min_length=1)
    source: str = Field(..., min_length=1)
    summary: str = Field(default="")


class EvidenceStore(BaseModel):
    items: List[EvidenceItem] = Field(default_factory=list)


class Claim(BaseModel):
    text: str = Field(..., min_length=1)
    evidence_ids: List[str] = Field(..., min_length=1)

    @field_validator("evidence_ids")
    @classmethod
    def evidence_ids_non_empty_elements(cls, v: List[str]) -> List[str]:
        if not v:
            raise ValueError("evidence_ids must be non-empty")
        for eid in v:
            if not (eid and eid.strip()):
                raise ValueError("evidence_ids must not contain empty strings")
        return v


class Abstention(BaseModel):
    reason_code: str = Field(..., min_length=1)
    message: str = Field(..., min_length=1)
    missing_evidence_keys: List[str] = Field(...)


class VisitPrepSection(BaseModel):
    claims: List[Claim] = Field(default_factory=list)
    abstentions: List[Abstention] = Field(default_factory=list)


class VisitPrepBrief(BaseModel):
    top_risks: VisitPrepSection
    changes_since_last_visit: VisitPrepSection
    medication_safety: VisitPrepSection
    care_gaps: VisitPrepSection
    agenda: VisitPrepSection
    abstentions: VisitPrepSection


class VisitPrepMetadata(BaseModel):
    patient_id: str = Field(..., min_length=1)
    window_months: int = Field(..., ge=1, le=36)
    generated_at: str = Field(..., min_length=1)


class VisitPrepResponse(BaseModel):
    brief: VisitPrepBrief
    metadata: VisitPrepMetadata
    evidence_store: EvidenceStore = Field(default_factory=EvidenceStore)
