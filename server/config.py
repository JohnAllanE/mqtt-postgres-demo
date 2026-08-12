from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_env: str = "dev"
    log_level: str = "INFO"

    mqtt_broker_host: str = "localhost"
    mqtt_broker_port: int = 1883
    mqtt_client_id_server: str = "srv-001"
    mqtt_client_id_gateway: str = "gw-001"
    mqtt_topic_prefix: str = "demo"

    postgres_host: str = "localhost"
    postgres_port: int = 5432
    postgres_db: str = "mqtt_demo"
    postgres_user: str = "postgres"
    postgres_password: str = "postgres"

    server_host: str = "0.0.0.0"
    server_port: int = 8000

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    @property
    def postgres_dsn(self) -> str:
        return (
            f"postgresql://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @property
    def gateway_telemetry_global_topic(self) -> str:
        return (
            f"{self.mqtt_topic_prefix}/gateway/"
            f"{self.mqtt_client_id_gateway}/telemetry/global"
        )

    @property
    def gateway_telemetry_monitor_topic(self) -> str:
        return (
            f"{self.mqtt_topic_prefix}/gateway/"
            f"{self.mqtt_client_id_gateway}/telemetry/monitor"
        )

    @property
    def gateway_status_topic(self) -> str:
        return f"{self.mqtt_topic_prefix}/gateway/{self.mqtt_client_id_gateway}/status"

    @property
    def gateway_cmd_topic(self) -> str:
        return f"{self.mqtt_topic_prefix}/gateway/{self.mqtt_client_id_gateway}/cmd"

    @property
    def gateway_cmd_ack_topic(self) -> str:
        return f"{self.mqtt_topic_prefix}/gateway/{self.mqtt_client_id_gateway}/cmd_ack"


settings = Settings()
