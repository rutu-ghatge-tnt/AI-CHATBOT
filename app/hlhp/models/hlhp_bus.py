"""Pydantic models for HLHP bus payloads and API bodies."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator


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
    assigned_doctor_name: str = Field(default="", alias="assignedDoctorName")

    model_config = {"populate_by_name": True}


class HlhpChatDoc(BaseModel):
    name: str = Field(..., min_length=1, max_length=256)
    size: str = ""


class HlhpChatMessageRequest(BaseModel):
    user_id: str | None = None
    doctor_id: str | None = Field(default=None, alias="doctorId")
    txt: str = ""
    photo: bool = False
    img: str | None = None
    doc: HlhpChatDoc | None = None

    model_config = {"populate_by_name": True}

    @model_validator(mode="after")
    def require_content(self) -> "HlhpChatMessageRequest":
        has_text = bool((self.txt or "").strip())
        has_img = bool((self.img or "").strip()) or self.photo
        has_doc = self.doc is not None and bool(self.doc.name.strip())
        if not (has_text or has_img or has_doc):
            raise ValueError("message requires txt, img/photo, or doc")
        return self


class HlhpTypingRequest(BaseModel):
    user_id: str | None = None
    doctor_id: str | None = Field(default=None, alias="doctorId")
    on: bool = True

    model_config = {"populate_by_name": True}


class HlhpPaymentCheckoutRequest(BaseModel):
    user_id: str | None = None
    doctor_id: str = Field(..., alias="doctorId")
    tnc_accepted: bool = Field(..., alias="tncAccepted")
    name: str = ""

    model_config = {"populate_by_name": True}


class HlhpPaymentVerifyRequest(BaseModel):
    user_id: str | None = None
    razorpay_payment_id: str = Field(..., alias="razorpayPaymentId", min_length=1)
    razorpay_subscription_id: str = Field(
        ..., alias="razorpaySubscriptionId", min_length=1
    )
    razorpay_signature: str = Field(..., alias="razorpaySignature", min_length=1)

    model_config = {"populate_by_name": True}


class HlhpPaymentDoctorScopedRequest(BaseModel):
    """Cancel / resume body — scoped to a seeker↔doctor lane."""

    user_id: str | None = None
    doctor_id: str = Field(..., alias="doctorId")

    model_config = {"populate_by_name": True}


class HlhpPaymentRenewRequest(BaseModel):
    user_id: str | None = None
    doctor_id: str = Field(..., alias="doctorId")
    tnc_accepted: bool = Field(..., alias="tncAccepted")
    name: str = ""

    model_config = {"populate_by_name": True}


class HlhpDoctorSubscriptionUpdate(BaseModel):
    fee: int = Field(..., ge=99, le=99999)


class HlhpDoctorMessageRequest(BaseModel):
    txt: str = ""
    photo: bool = False
    img: str | None = None
    doc: HlhpChatDoc | None = None

    @model_validator(mode="after")
    def require_content(self) -> "HlhpDoctorMessageRequest":
        has_text = bool((self.txt or "").strip())
        has_img = bool((self.img or "").strip()) or self.photo
        has_doc = self.doc is not None and bool(self.doc.name.strip())
        if not (has_text or has_img or has_doc):
            raise ValueError("message requires txt, img/photo, or doc")
        return self


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

    @field_validator("fee")
    @classmethod
    def fee_bounds(cls, value: int) -> int:
        if value < 99 or value > 99999:
            raise ValueError("fee must be between 99 and 99999")
        return value


ChatWho = Literal["seeker", "doctor"]
