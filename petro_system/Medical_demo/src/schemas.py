from __future__ import annotations

import json
from typing import Any, Literal

from pydantic import BaseModel, Field


class PatientBasic(BaseModel):
    name: str = ""
    gender: str = ""
    age: int | None = None
    city: str = "上海"
    insurance_context: str = ""


class VitalSigns(BaseModel):
    temperature: float | None = None
    blood_pressure: str = ""
    heart_rate: int | None = None


class ExamResult(BaseModel):
    date: str = ""
    type: str = "other"
    item: str = ""
    result: str = ""
    unit: str = ""
    reference_range: str = ""
    abnormal: bool = False
    source_page: int | None = None
    source_file: str = ""


class PatientNeed(BaseModel):
    preferred_city: str = "上海"
    preferred_area: str = ""
    hospital_level: str = "三级优先"
    k: int = 6
    special_constraints: list[str] = Field(default_factory=list)
    require_doctor_evidence: bool = False


class DepartmentCandidate(BaseModel):
    department: str
    reason: str = ""
    confidence: float = 0.5


class PatientProfile(BaseModel):
    patient_basic: PatientBasic = Field(default_factory=PatientBasic)
    chief_complaint: str = ""
    present_illness: str = ""
    past_history: list[str] = Field(default_factory=list)
    allergy_history: list[str] = Field(default_factory=list)
    surgery_history: list[str] = Field(default_factory=list)
    current_symptoms: list[str] = Field(default_factory=list)
    vital_signs: VitalSigns = Field(default_factory=VitalSigns)
    exam_results: list[ExamResult] = Field(default_factory=list)
    suspected_diagnoses: list[str] = Field(default_factory=list)
    department_candidates: list[DepartmentCandidate] = Field(default_factory=list)
    urgency_level: Literal["routine", "soon", "urgent"] = "routine"
    patient_need: PatientNeed = Field(default_factory=PatientNeed)
    missing_information: list[str] = Field(default_factory=list)
    risk_flags: list[str] = Field(default_factory=list)
    source_files: list[str] = Field(default_factory=list)
    raw_document_text: str = ""
    raw_page_texts: list[dict[str, Any]] = Field(default_factory=list)

    def to_json_text(self) -> str:
        return json.dumps(self.model_dump(), ensure_ascii=False, indent=2)


class HospitalCandidate(BaseModel):
    name: str
    address: str = ""
    city: str = "上海"
    district: str = ""
    level: str = ""
    phone: str = ""
    location: str = ""
    strengths: list[str] = Field(default_factory=list)
    source: str = "fallback"
    evidence_url: str = ""
    map_url: str = ""


class DoctorEvidence(BaseModel):
    name: str = ""
    title: str = ""
    department: str = ""
    hospital: str = ""
    expertise: str = ""
    source_url: str = ""


class Recommendation(BaseModel):
    rank: int
    hospital: str
    department: str
    doctor: str = "待人工确认"
    title: str = ""
    score: float = 0.0
    address: str = ""
    reasons: list[str] = Field(default_factory=list)
    evidence_urls: list[str] = Field(default_factory=list)
    official_source_urls: list[str] = Field(default_factory=list)
    map_url: str = ""
    caveats: list[str] = Field(default_factory=list)


def parse_profile_json(text: str | dict[str, Any] | PatientProfile) -> PatientProfile:
    if isinstance(text, PatientProfile):
        return text
    if isinstance(text, dict):
        return PatientProfile.model_validate(text)

    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`")
        if cleaned.startswith("json"):
            cleaned = cleaned[4:].strip()
    return PatientProfile.model_validate(json.loads(cleaned))


def compact_dict(data: BaseModel | dict[str, Any]) -> dict[str, Any]:
    if isinstance(data, BaseModel):
        return data.model_dump()
    return data
