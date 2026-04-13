from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    # Telegram
    telegram_bot_token: str = ""

    # VK
    vk_group_token: str = ""
    vk_group_id: int = 0
    vk_confirmation_string: str = ""

    # Database
    database_url: str = "postgresql+asyncpg://poll_user:poll_pass@db:5432/poll_aggregator"

    # App
    webhook_base_url: str = "http://localhost:8000"
    admin_api_key: str = "changeme"


settings = Settings()
