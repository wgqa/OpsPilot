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
