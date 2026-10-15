"""수동 비전 모델 결과 및 사용자 프로필 요청 스키마."""
from typing import Literal
from pydantic import BaseModel, Field

class Symptoms(BaseModel):
    micro_keratin: int = Field(default=0, ge=0, le=3)
    excess_sebum: int = Field(default=0, ge=0, le=3)
    follicular_erythema: int = Field(default=0, ge=0, le=3)
    follicular_pustule: int = Field(default=0, ge=0, le=3)
    dandruff: int = Field(default=0, ge=0, le=3)
    hair_loss: int = Field(default=0, ge=0, le=3)


class Profile(BaseModel):
    age_group: str | None = None
    wash_frequency: str | None = None
    max_price: int | None = Field(default=None, ge=1)


Category = Literal["shampoo", "scaler", "treatment", "tonic"]

class RecommendRequest(BaseModel):
    symptoms: Symptoms
    user_info: Profile = Field(default_factory=Profile)
    # None keeps compatibility with the prior /recommend contract; the demo UI always
    # submits an explicit nonempty list. Selected categories are strict retrieval filters.
    categories: list[Category] | None = Field(default=None, min_length=1)



