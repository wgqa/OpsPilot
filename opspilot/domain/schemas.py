from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, StrictStr


class ServiceInfoRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    service_id: StrictStr = Field(min_length=1, max_length=64)


class ServiceInfoResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    service_id: str
    route: str
    tenant_id: str
    integration_id: str
    credential_ref: str
    config_version: int
    principal_id: str
    principal_status: str
    principal_version: int
    accepted_credential_ref: str
    policy_version: int


class IntegrationInfoResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    integration_id: str
    principal_id: str
    credential_ref: str
    config_version: int
    principal_status: str
    principal_version: int
