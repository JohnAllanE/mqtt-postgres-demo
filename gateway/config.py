from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_env: str = "dev"
    log_level: str = "INFO"

    mqtt_broker_host: str = "localhost"
    mqtt_broker_port: int = 1883
    mqtt_client_id_gateway: str = "gw-001"
    mqtt_topic_prefix: str = "demo"

    global_default_freq_hz: float = 1.0
    monitor_default_freq_hz: float = 10.0
    global_default_batch_ms: int = 1000
    monitor_default_batch_ms: int = 500

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    @property
    def status_topic(self) -> str:
        return f"{self.mqtt_topic_prefix}/gateway/{self.mqtt_client_id_gateway}/status"

    @property
    def telemetry_global_topic(self) -> str:
        return (
            f"{self.mqtt_topic_prefix}/gateway/"
            f"{self.mqtt_client_id_gateway}/telemetry/global"
        )

    @property
    def telemetry_monitor_topic(self) -> str:
        return (
            f"{self.mqtt_topic_prefix}/gateway/"
            f"{self.mqtt_client_id_gateway}/telemetry/monitor"
        )

    @property
    def command_topic(self) -> str:
        return f"{self.mqtt_topic_prefix}/gateway/{self.mqtt_client_id_gateway}/cmd"

    @property
    def command_ack_topic(self) -> str:
        return f"{self.mqtt_topic_prefix}/gateway/{self.mqtt_client_id_gateway}/cmd_ack"


settings = Settings()
