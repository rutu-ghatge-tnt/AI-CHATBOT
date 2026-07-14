"""Pydantic models for HLHP bus payloads and API bodies."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class HlhpGoalSetupPayload(BaseModel):
    name: str = ""
    goal_name: str = Field(default="", alias="goalName")
    days: int = 90
    city: str = ""
    skin: str = ""
    concern: str = ""
    goal_focus: str = Field(default="", alias="goalFocus")
    brief: str = ""
    goal_type: str = Field(default="wedding", alias="goalType")
    age: str = ""
    gender: str = ""
    home_city: str = Field(default="", alias="homeCity")
    assigned_doctor_id: str = Field(default="", alias="assignedDoctorId")
    assigned_doctor_name: str = Field(default="", alias="assignedDoctorName")
    ts: int = 0

    model_config = {"populate_by_name": True}

    def to_bus_payload(self) -> dict[str, Any]:
        return self.model_dump(by_alias=True, exclude_none=True)


class HlhpProfileUpdateRequest(BaseModel):
    user_id: str | None = None
    name: str | None = None
    city: str | None = None
    skin: str | None = None
    concern: str | None = None
    age: str | None = None
    gender: str | None = None


class HlhpGoalCreateRequest(BaseModel):
    user_id: str | None = None
    goal_name: str = Field(..., alias="goalName")
    days: int = Field(default=90, ge=1, le=365)
    city: str = ""
    skin: str = ""
    concern: str = ""
    goal_focus: str = Field(default="", alias="goalFocus")
    brief: str = ""
    goal_type: str = Field(default="wedding", alias="goalType")
    name: str = ""
    age: str = ""
    gender: str = ""
    assigned_doctor_id: str = Field(default="", alias="assignedDoctorId")

    model_config = {"populate_by_name": True}


class HlhpChatMessageRequest(BaseModel):
    user_id: str | None = None
    doctor_id: str | None = None
    txt: str = ""
    photo: bool = False


class HlhpTypingRequest(BaseModel):
    user_id: str | None = None
    doctor_id: str | None = None
    on: bool = True


class HlhpPaymentCheckoutRequest(BaseModel):
    user_id: str | None = None
    doctor_id: str = Field(..., alias="doctorId")
    tnc_accepted: bool = Field(..., alias="tncAccepted")
    name: str = ""
    winback: bool = False

    model_config = {"populate_by_name": True}


class HlhpDoctorSubscriptionUpdate(BaseModel):
    fee: int = Field(..., ge=99, le=99999)


class HlhpDoctorMessageRequest(BaseModel):
    txt: str = Field(..., min_length=1)


class HlhpDoctorOnboardComplete(BaseModel):
    name: str = ""
    quals: str = ""
    about: str = Field(default="", max_length=400)
    city: str = ""
    clinics: int = 1
    clinic_list: list[dict[str, Any]] = Field(default_factory=list, alias="clinicList")
    service_names: list[str] = Field(default_factory=list, alias="serviceNames")
    fee: int = 1499

    model_config = {"populate_by_name": True}


ChatWho = Literal["seeker", "doctor"]
