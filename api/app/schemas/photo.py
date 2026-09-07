from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

#: Spec §9 restricts uploads to these.
PhotoContentType = Literal["image/jpeg", "image/png", "image/heic"]


class PresignRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    content_type: PhotoContentType


class PresignResponse(BaseModel):
    upload_url: str
    s3_key: str


class PhotoConfirm(BaseModel):
    """Called after the direct upload succeeds (spec §6)."""

    model_config = ConfigDict(extra="forbid")

    s3_key: str = Field(min_length=1, max_length=512)
    taken_on: date


class PhotoOut(BaseModel):
    id: int
    taken_on: date
    view_url: str
    thumb_url: str | None
