from typing import Literal

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", hide_input_in_errors=True)

    app_env: Literal["local", "test", "eval"] = "local"
    database_url: str = "sqlite+aiosqlite:///./data/charge_ops.db"
    mqtt_host: str = "127.0.0.1"
    mqtt_port: int = Field(default=1883, ge=1, le=65535)
    mqtt_enabled: bool = True
    mqtt_topic_prefix: str = "charge/v1"
    simulator_mode: Literal["legacy", "operations"] = "legacy"
    simulator_state_dir: str = "./data/simulator"
    session_report_expiry_seconds: float = Field(default=86400, gt=0)
    session_report_retry_seconds: tuple[float, float, float, float] = (1, 2, 4, 30)
    telemetry_interval_seconds: float = Field(default=2, gt=0)
    fresh_sample_max_age_seconds: float = Field(default=10, gt=0)
    offline_timeout_seconds: float = Field(default=15, gt=0)
    overheat_threshold_c: float = 60
    control_ack_timeout_seconds: float = Field(default=5, gt=0)
    control_verification_timeout_seconds: float = Field(default=4, gt=0)
    scenario_ack_timeout_seconds: float = Field(default=5, gt=0)
    db_busy_timeout_ms: int = Field(default=1000, gt=0)
    agent_model_timeout_seconds: float = Field(default=20, gt=0)
    agent_tool_timeout_seconds: float = Field(default=3, gt=0)
    agent_total_timeout_seconds: float = Field(default=90, gt=0)
    agent_cleanup_timeout_seconds: float = Field(default=5, gt=0)
    agent_max_model_requests: int = Field(default=6, ge=1)
    agent_max_tool_calls: int = Field(default=8, ge=1)
    llm_mode: Literal["fixture", "real"] = "fixture"
    llm_base_url: str = ""
    llm_model: str = ""
    llm_api_key: SecretStr = SecretStr("")

    @model_validator(mode="after")
    def validate_mode(self) -> "Settings":
        if not self.mqtt_enabled and self.app_env not in {"test", "eval"}:
            raise ValueError("MQTT may only be disabled in test/eval")
        if self.llm_mode == "real" and not all(
            (
                self.llm_base_url.strip(),
                self.llm_model.strip(),
                self.llm_api_key.get_secret_value().strip(),
            )
        ):
            raise ValueError("LLM_CONFIGURATION_ERROR: real mode requires endpoint/model/key")
        if not self.mqtt_topic_prefix or any(c in self.mqtt_topic_prefix for c in "+#"):
            raise ValueError("Invalid MQTT topic prefix")
        return self
