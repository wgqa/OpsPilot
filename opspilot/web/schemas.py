from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class LoginRequest(StrictModel):
    actor_id: str = Field(min_length=1, max_length=100)
    password: str = Field(min_length=1, max_length=512)


class CreateSessionRequest(StrictModel):
    pass


class CreateTaskRequest(StrictModel):
    initial_message: str = Field(min_length=1, max_length=20_000)


class MessageRequest(StrictModel):
    body: str = Field(min_length=1, max_length=20_000)
    input_kind: Literal["CHAT_READONLY", "CORRECT_TASK_INPUT"] = "CHAT_READONLY"
    task_id: str | None = Field(default=None, max_length=100)


class AbortTaskRequest(StrictModel):
    reason: str = Field(min_length=1, max_length=500)


class PlanApprovalRequest(StrictModel):
    decision: Literal["APPROVED", "REJECTED"]


class S2HandoffSubmitRequest(StrictModel):
    operation_id: str = Field(min_length=1, max_length=200)
    draft_id: str = Field(min_length=1, max_length=200)
    draft_digest: str = Field(min_length=64, max_length=64)
    expected_control_revision: int = Field(ge=0)
    handoff_kind: Literal["SCOPE_REVIEW"]


class MemoryCommandRequest(StrictModel):
    """Memory lifecycle writes accept no caller-authored source or content fields."""
    pass


class SemanticMemoryCandidateRequest(StrictModel):
    memory_kind: Literal["ALIAS", "INTERFACE_CONVENTION", "WORK_CONSTRAINT"]
    memory_key: str = Field(min_length=1, max_length=120)
    content: str = Field(min_length=1, max_length=800)
    source_message_id: str = Field(min_length=1, max_length=120)
    ttl_days: int = Field(default=90, ge=1, le=365)
    supersedes_memory_id: str | None = Field(default=None, max_length=120)
    expected_version: int | None = Field(default=None, ge=1)
