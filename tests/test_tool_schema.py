from __future__ import annotations

import pytest
from pydantic import ValidationError

from opspilot.domain.schemas import ServiceInfoRequest
from opspilot.tools.model_tools import get_demo_service_info


def test_model_tool_arguments_require_one_strict_service_id() -> None:
    assert ServiceInfoRequest.model_validate({"service_id": "orders-demo"}).service_id == "orders-demo"
    with pytest.raises(ValidationError):
        ServiceInfoRequest.model_validate({"service_id": 7})
    with pytest.raises(ValidationError):
        ServiceInfoRequest.model_validate({"service_id": "orders-demo", "tenant_id": "tenant-b"})
    with pytest.raises(ValidationError):
        get_demo_service_info.invoke({"service_id": 7})
