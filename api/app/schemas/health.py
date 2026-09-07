import uuid

from pydantic import BaseModel


class Health(BaseModel):
    status: str


class AuthHealth(BaseModel):
    status: str
    user_id: uuid.UUID
    unit: str
