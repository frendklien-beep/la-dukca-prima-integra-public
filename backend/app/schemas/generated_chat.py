from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class GeneratedClaim(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str = Field(min_length=1, max_length=1200)
    status: Literal["supported", "inferred", "unsupported"]
    source_keys: list[str] = Field(max_length=5)
    confidence: float = Field(ge=0.0, le=1.0)


class GeneratedIntentAnswer(BaseModel):
    model_config = ConfigDict(extra="forbid")

    intent_id: str
    status: Literal["success", "insufficient_knowledge"]
    answer: str = Field(min_length=1, max_length=6000)
    used_source_keys: list[str] = Field(max_length=5)
    needs_human_confirmation: bool
    claims: list[GeneratedClaim] = Field(default_factory=list, max_length=30)
    unsupported_claims_detected: bool = False
    grounding_status: Literal["passed", "warning", "failed"] = "passed"


class GeneratedConversationAnswer(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["success", "partial", "insufficient_knowledge"]
    intent_answers: list[GeneratedIntentAnswer] = Field(min_length=1, max_length=5)


_CLAIM_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["text", "status", "source_keys", "confidence"],
    "properties": {
        "text": {"type": "string"},
        "status": {
            "type": "string",
            "enum": ["supported", "inferred", "unsupported"],
        },
        "source_keys": {
            "type": "array",
            "maxItems": 5,
            "items": {"type": "string"},
        },
        "confidence": {"type": "number", "minimum": 0.0, "maximum": 1.0},
    },
}


GENERATED_CONVERSATION_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["status", "intent_answers"],
    "properties": {
        "status": {
            "type": "string",
            "enum": ["success", "partial", "insufficient_knowledge"],
        },
        "intent_answers": {
            "type": "array",
            "minItems": 1,
            "maxItems": 5,
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": [
                    "intent_id",
                    "status",
                    "answer",
                    "used_source_keys",
                    "needs_human_confirmation",
                    "claims",
                    "unsupported_claims_detected",
                    "grounding_status",
                ],
                "properties": {
                    "intent_id": {"type": "string"},
                    "status": {
                        "type": "string",
                        "enum": ["success", "insufficient_knowledge"],
                    },
                    "answer": {"type": "string"},
                    "used_source_keys": {
                        "type": "array",
                        "maxItems": 5,
                        "items": {"type": "string"},
                    },
                    "needs_human_confirmation": {"type": "boolean"},
                    "claims": {
                        "type": "array",
                        "maxItems": 30,
                        "items": _CLAIM_SCHEMA,
                    },
                    "unsupported_claims_detected": {"type": "boolean"},
                    "grounding_status": {
                        "type": "string",
                        "enum": ["passed", "warning", "failed"],
                    },
                },
            },
        },
    },
}
