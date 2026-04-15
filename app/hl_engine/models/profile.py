from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class SkinType(str, Enum):
    OILY = "oily"
    DRY = "dry"
    COMBINATION = "combination"
    NORMAL = "normal"
    SENSITIVE = "sensitive"


class SkinConcern(str, Enum):
    ACNE = "acne"
    PIGMENTATION = "pigmentation"
    TAN = "tan"
    AGING = "aging"
    DULLNESS = "dullness"
    SENSITIVITY = "sensitivity"
    DARK_CIRCLES = "dark_circles"
    PORES = "pores"
    TEXTURE = "texture"
    DEHYDRATION = "dehydration"
    REDNESS = "redness"
    MELASMA = "melasma"


class Gender(str, Enum):
    MALE = "male"
    FEMALE = "female"
    OTHER = "other"
    PREFER_NOT_TO_SAY = "prefer_not_to_say"


class AgeBracket(str, Enum):
    AGE_18_24 = "18-24"
    AGE_25_30 = "25-30"
    AGE_31_40 = "31-40"
    AGE_41_50 = "41-50"
    AGE_50_PLUS = "50+"


class HairType(str, Enum):
    STRAIGHT = "straight"
    WAVY = "wavy"
    CURLY = "curly"
    COILY = "coily"
    THINNING = "thinning"


class HairConcern(str, Enum):
    FRIZZ = "frizz"
    DANDRUFF = "dandruff"
    THINNING = "thinning"
    OILINESS = "oiliness"
    DRYNESS = "dryness"
    COLOR_TREATED = "color_treated"
    BREAKAGE = "breakage"
    SCALP_SENSITIVITY = "scalp_sensitivity"


class UserProfile(BaseModel):
    user_id: str
    skin_type: SkinType
    skin_concerns: list[SkinConcern] = Field(..., min_length=1, max_length=3)
    gender: Gender
    age_bracket: AgeBracket
    hair_type: Optional[HairType] = None
    hair_concerns: list[HairConcern] = Field(default_factory=list, max_length=3)

    @property
    def fitzpatrick_type(self) -> int:
        return _SKIN_TYPE_TO_FITZPATRICK.get(self.skin_type, 4)

    @property
    def primary_concern(self) -> SkinConcern:
        return self.skin_concerns[0]

    @property
    def has_hair_profile(self) -> bool:
        return self.hair_type is not None


_SKIN_TYPE_TO_FITZPATRICK = {
    SkinType.SENSITIVE: 3,
    SkinType.DRY: 4,
    SkinType.NORMAL: 4,
    SkinType.COMBINATION: 4,
    SkinType.OILY: 4,
}
