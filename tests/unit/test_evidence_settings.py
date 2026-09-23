import pytest

from backend.app.config import Settings
from scripts.evidence import default_contract_settings


def test_evaluation_refuses_changed_business_budget_without_reading_secrets():
    settings = Settings(_env_file=None, app_env="eval", mqtt_enabled=False)
    values = default_contract_settings(settings)
    assert values["agent_tool_timeout_seconds"] == 3
    assert not any("key" in name or "llm" in name for name in values)
    with pytest.raises(ValueError, match="agent_tool_timeout_seconds"):
        default_contract_settings(settings.model_copy(update={"agent_tool_timeout_seconds": 4}))
