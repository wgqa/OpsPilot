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


class IntegrationConfigRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    integration_id: StrictStr = Field(min_length=1, max_length=64)


class PrincipalStatusRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    principal_id: StrictStr = Field(min_length=1, max_length=64)


class AuthPolicyRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    service_id: StrictStr = Field(min_length=1, max_length=64)


class EndpointProbeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    service_id: StrictStr = Field(min_length=1, max_length=64)
    integration_id: StrictStr = Field(min_length=1, max_length=64)


class D2ToolFact(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    tenant_id: StrictStr
    task_id: StrictStr
    fact_type: StrictStr
    resource_id: StrictStr
    principal_id: StrictStr
    data_source: StrictStr
    observed_at: StrictStr
    observed_versions: dict[str, object]
    facts: dict[str, object]
    original_result_ref: StrictStr
    trust_class: StrictStr
