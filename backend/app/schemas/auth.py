from datetime import UTC, datetime

from pydantic import BaseModel, ConfigDict, Field, field_serializer, field_validator


class LoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=128, repr=False)
    remember_me: bool = False

    @field_validator("password")
    @classmethod
    def no_control(cls, v: str) -> str:
        if any(ord(c) < 32 or ord(c) == 127 for c in v):
            raise ValueError("Password tidak valid.")
        return v


class AdminPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True, extra="forbid")
    id: int
    username: str
    display_name: str
    role: str


class AdminSessionPublic(BaseModel):
    model_config = ConfigDict(extra="forbid")
    remember_me: bool
    idle_expires_at: datetime
    expires_at: datetime

    @field_serializer("idle_expires_at", "expires_at")
    def ser(self, v: datetime) -> str:
        return v.astimezone(UTC).isoformat().replace("+00:00", "Z")


class LoginData(BaseModel):
    admin: AdminPublic
    session: AdminSessionPublic
    csrf_token: str


class CurrentAdminData(BaseModel):
    admin: AdminPublic
    session: AdminSessionPublic


class CsrfData(BaseModel):
    csrf_token: str
    session_expires_at: datetime

    @field_serializer("session_expires_at")
    def ser(self, v: datetime) -> str:
        return v.astimezone(UTC).isoformat().replace("+00:00", "Z")


class LogoutData(BaseModel):
    logged_out: bool = True
