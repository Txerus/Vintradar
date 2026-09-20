from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    database_url: str = "sqlite+aiosqlite:///./vintradar.db"
    vintradar_api_token: str = "dev-token"
    vinted_domain: str = "https://www.vinted.fr"
    scan_global_rpm: int = 4
    scan_daily_budget: int = 1440
    targeted_search_daily_budget: int = 24
    ntfy_url: str = "http://localhost:8080"
    ntfy_base_url: str = "http://localhost:8080"
    ntfy_upstream_base_url: str = "https://ntfy.sh"
    ntfy_topic: str = "vintradar"
    ntfy_token: str | None = None
    ollama_enabled: bool = False
    ollama_url: str = "http://localhost:11434"
    ollama_model: str = "qwen3:4b"
    bricklink_consumer_key: str | None = None
    bricklink_consumer_secret: str | None = None
    bricklink_token_value: str | None = None
    bricklink_token_secret: str | None = None
    brickset_api_key: str | None = None
    rebrickable_api_key: str | None = None
    pricecharting_token: str | None = None
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
settings=Settings()
