from typing import Literal

from pydantic import BaseModel, ConfigDict

from app.core.config import Environment


class LivenessData(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: Literal["alive"] = "alive"
    service: str


class ReadinessComponents(BaseModel):
    model_config = ConfigDict(extra="forbid")
    database: Literal["ready", "unavailable"]
    storage: Literal["ready", "unavailable"]
    migrations: Literal["ready", "missing", "behind", "multiple_heads", "error"]
    knowledge_base: Literal["empty"] = "empty"
    ai_configuration: Literal["configured", "unconfigured"]


class ReadinessData(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: Literal["ready", "degraded"]
    components: ReadinessComponents


class SystemVersionData(BaseModel):
    model_config = ConfigDict(extra="forbid")
    application: str
    api_version: Literal["v1"] = "v1"
    backend_version: str
    environment: Environment
    build: str
