"""Immutable non-observation records (backend M3): missions, environmental events, source
artifacts, human-issued commands, non-clinical rule findings and AI explanations.

None of these is a ``HealthObservation``. Each carries explicit marker fields that make the
distinction machine-checkable:

* ``EnvironmentalEvent.applies_to_individual`` is always ``False`` — environmental radiation is
  never an astronaut's dose (D-021/P-2; no detector-to-tissue conversion exists in MEDVITAL).
* ``RuleFinding.clinical`` is always ``False`` — findings are non-clinical review flags (D-021).
* ``AIExplanation.is_observation`` is always ``False`` — AI text is never evidence (D-022).
* ``ReturnNowCommand`` requires a *human* issuer; there is no automated code path that creates one.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated, Literal, Self
from uuid import UUID, uuid5

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, StringConstraints, model_validator

from medvital.core.schema import DataOrigin, LongText, ModuleId, Provenance, ShortText, SubjectId

RECORDS_SCHEMA_VERSION = 1
_NS = UUID("8a1d2c4e-6b0f-4e3a-9c71-5d2e8f0a1b33")

MissionId = Annotated[str, StringConstraints(pattern=r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,63}$")]
PrincipalId = Annotated[str, StringConstraints(pattern=r"^[A-Za-z0-9|@._:-]{1,128}$")]
RequiredText = Annotated[str, StringConstraints(min_length=1, max_length=2000)]
Sha256 = Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{64}$")]


class _Record(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: int = RECORDS_SCHEMA_VERSION

    @model_validator(mode="after")
    def _check_version(self) -> Self:
        if self.schema_version != RECORDS_SCHEMA_VERSION:
            raise ValueError(f"unsupported record schema_version {self.schema_version}")
        return self


# --------------------------------------------------------------------------- missions


class Mission(_Record):
    """Mission context: anchors the time model (L±n / R±n) and scopes access (D-021, M5)."""

    mission_id: MissionId
    name: ShortText
    launch_at: AwareDatetime
    return_at: AwareDatetime | None = Field(default=None, description="None while the mission is ongoing.")
    crew: list[SubjectId] = Field(min_length=1, max_length=32)
    data_origin: DataOrigin = Field(description="simulated for demo missions; never invent a real mission.")
    created_at: AwareDatetime
    notes: LongText | None = None

    @model_validator(mode="after")
    def _check(self) -> Self:
        if self.return_at is not None and not self.return_at > self.launch_at:
            raise ValueError("return_at must be after launch_at")
        if len(set(self.crew)) != len(self.crew):
            raise ValueError("crew contains duplicates")
        return self


# --------------------------------------------------------------------------- source artifacts


class ProcessingStep(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    at: AwareDatetime
    step: ShortText  # e.g. "download", "checksum", "parse:donki_sep"
    tool: ShortText  # e.g. "medvital.acquire v1"
    detail: LongText | None = None


class SourceArtifact(_Record):
    """Manifest of one downloaded source file. The file itself is stored unmodified, by checksum."""

    artifact_id: UUID
    source_system: ShortText  # e.g. "NASA DONKI", "NASA OSDR", "PDS PPI (MSL RAD)"
    dataset_id: ShortText  # e.g. "DONKI/SEP", "OSD-569", "MSL-M-RAD-3-RDR-V1.0"
    dataset_version: ShortText | None = None
    source_url: ShortText = Field(description="Retrieval URL with any API key removed.")
    original_filename: ShortText
    sha256: Sha256
    size_bytes: int = Field(ge=0)
    content_type: ShortText | None = None
    retrieved_at: AwareDatetime
    import_method: ShortText
    license_note: LongText | None = Field(default=None, description="None = licence not yet verified.")
    processing_history: list[ProcessingStep] = Field(default_factory=list)

    @staticmethod
    def make_id(source_url: str, sha256: str) -> UUID:
        return uuid5(_NS, f"artifact|{source_url}|{sha256}")


# --------------------------------------------------------------------------- environment


class DetectorContext(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    instrument: ShortText  # e.g. "MSL RAD"
    detector: ShortText | None = None  # e.g. "B", "E"
    detector_material: ShortText | None = Field(default=None, description="None = not stated by the source.")
    location: ShortText = Field(description="Where the detector was, e.g. 'Mars surface (Gale crater)'.")


class EnvironmentalMeasurement(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    quantity: ShortText  # source field name, e.g. "TOT_DOSE_B"
    value: float = Field(allow_inf_nan=False)
    unit: ShortText  # as stated by the source, e.g. "uGy/h" (detector material dose rate)
    uncertainty: float | None = Field(default=None, ge=0, allow_inf_nan=False)


class EnvironmentalEvent(_Record):
    """Space-environment record (DONKI event/notice or a detector measurement such as MSL RAD).

    Never linked to a subject's dose: there is deliberately no subject field, and
    ``applies_to_individual`` is fixed to False.
    """

    event_id: UUID
    source_system: Literal["NASA DONKI", "MSL RAD", "scenario"]
    event_type: ShortText  # e.g. "SEP", "CME", "FLR", "GST", "notification:FLR", "dosimetry"
    source_event_id: ShortText  # e.g. sepID, messageID, RAD product id + observation index
    source_version: ShortText | None = None
    start_time: AwareDatetime
    end_time: AwareDatetime | None = None
    summary: LongText | None = None
    link: ShortText | None = None
    detector: DetectorContext | None = None
    measurements: list[EnvironmentalMeasurement] = Field(default_factory=list)
    linked_source_events: list[ShortText] = Field(default_factory=list)
    provenance: Provenance
    source_artifact_id: UUID | None = None
    applies_to_individual: Literal[False] = False

    @model_validator(mode="after")
    def _check(self) -> Self:
        if self.end_time is not None and self.end_time < self.start_time:
            raise ValueError("end_time must not precede start_time")
        if self.source_system == "scenario" and self.provenance.data_origin is not DataOrigin.SIMULATED:
            raise ValueError("scenario events must be simulated")
        if self.source_system != "scenario" and self.provenance.data_origin is DataOrigin.SIMULATED:
            raise ValueError("DONKI/RAD records cannot be labelled simulated")
        if self.measurements and self.detector is None:
            raise ValueError("measurements require detector context")
        return self

    @staticmethod
    def make_id(source_system: str, source_event_id: str, source_version: str | None) -> UUID:
        return uuid5(_NS, f"env|{source_system}|{source_event_id}|{source_version or ''}")


# --------------------------------------------------------------------------- commands


class HumanIssuer(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    principal_id: PrincipalId
    display_name: ShortText
    role: Literal["flight_surgeon", "ground_control", "mission_commander"]
    issuer_type: Literal["human"] = "human"


class CommandStatus(StrEnum):
    ISSUED = "issued"
    ACKNOWLEDGED = "acknowledged"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    WITHDRAWN = "withdrawn"


ALLOWED_TRANSITIONS: dict[CommandStatus, frozenset[CommandStatus]] = {
    CommandStatus.ISSUED: frozenset({CommandStatus.ACKNOWLEDGED, CommandStatus.WITHDRAWN}),
    CommandStatus.ACKNOWLEDGED: frozenset({CommandStatus.IN_PROGRESS, CommandStatus.WITHDRAWN}),
    CommandStatus.IN_PROGRESS: frozenset({CommandStatus.COMPLETED, CommandStatus.WITHDRAWN}),
    CommandStatus.COMPLETED: frozenset(),
    CommandStatus.WITHDRAWN: frozenset(),
}


class ReturnNowCommand(_Record):
    """RETURN_NOW is issued by a human only (D-021). MEDVITAL stores, syncs and displays it."""

    command_id: UUID
    command: Literal["RETURN_NOW"] = "RETURN_NOW"
    mission_id: MissionId
    subject_ids: list[SubjectId] = Field(default_factory=list, description="Empty = whole crew.")
    issuer: HumanIssuer
    issued_at: AwareDatetime
    reason: RequiredText
    mission_context: RequiredText


class CommandStatusEvent(_Record):
    """Append-only status history; the command record itself never changes."""

    event_id: UUID
    command_id: UUID
    status: CommandStatus
    actor: HumanIssuer
    at: AwareDatetime
    note: LongText | None = None


# --------------------------------------------------------------------------- rule findings


class FindingCategory(StrEnum):
    DEVICE_OFFLINE = "device_offline"
    INVALID_SENSOR_DATA = "invalid_sensor_data"
    MISSED_SCHEDULED_MEASUREMENT = "missed_scheduled_measurement"
    SYNC_FAILURE = "sync_failure"
    SPACE_WEATHER_NOTICE = "space_weather_notice"
    STATISTICAL_DEVIATION_REVIEW = "statistical_deviation_review"


class RuleFinding(_Record):
    """Non-clinical, deterministic rule output. A review flag, never a diagnosis or risk label."""

    finding_id: UUID
    rule_id: ShortText
    rule_version: ShortText
    category: FindingCategory
    mission_id: MissionId | None = None
    subject_id: SubjectId | None = None
    device_id: ShortText | None = None
    module: ModuleId | None = None
    evaluated_at: AwareDatetime
    window_start: AwareDatetime | None = None
    window_end: AwareDatetime | None = None
    summary: RequiredText
    evidence_ids: list[ShortText] = Field(default_factory=list)
    parameters: dict[str, str] = Field(default_factory=dict, description="Operational parameters used.")
    review_required: Literal[True] = True
    clinical: Literal[False] = False

    @staticmethod
    def make_id(rule_id: str, key: str) -> UUID:
        return uuid5(_NS, f"finding|{rule_id}|{key}")


# --------------------------------------------------------------------------- AI explanations


class AIExplanation(_Record):
    """Output of an explanation model (e.g. Gemini, M7). Stored separately; never an observation."""

    explanation_id: UUID
    provider: ShortText
    model: ShortText
    created_at: AwareDatetime
    requested_by: PrincipalId
    question: RequiredText
    summary: RequiredText
    evidence: list[RequiredText] = Field(min_length=1)
    missing_information: list[RequiredText] = Field(default_factory=list)
    uncertainty: list[RequiredText] = Field(default_factory=list)
    cited_observation_ids: list[UUID] = Field(default_factory=list)
    cited_finding_ids: list[UUID] = Field(default_factory=list)
    cited_report_ids: list[ShortText] = Field(default_factory=list)
    input_data_classes: list[Literal["simulated", "public_nasa"]] = Field(min_length=1)
    is_observation: Literal[False] = False

    @model_validator(mode="after")
    def _check(self) -> Self:
        if not (self.cited_observation_ids or self.cited_finding_ids or self.cited_report_ids):
            raise ValueError("an AI explanation must cite the records it describes")
        return self


# --------------------------------------------------------------------------- device ownership


class DeviceAssignment(_Record):
    """Which subject a device belongs to within a mission (append-only; the latest by
    ``assigned_at`` is current). ``subject_id=None`` unassigns the device.

    Used by write authorization (D-032): a restricted principal may submit an observation with a
    ``device_id`` only if that device is currently assigned to the observation's subject.
    """

    assignment_id: UUID
    device_id: Annotated[str, StringConstraints(pattern=r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,63}$")]
    subject_id: SubjectId | None
    mission_id: MissionId
    assigned_by: PrincipalId
    assigned_at: AwareDatetime
    note: LongText | None = None
