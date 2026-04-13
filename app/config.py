from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    # Telegram
    telegram_bot_token: str = ""

    # VK OAuth App
    vk_app_id: int = 0
    vk_app_secret: str = ""
    vk_token_encryption_key: str = ""  # Fernet key for encrypting stored tokens

    # Database
    database_url: str = "postgresql+asyncpg://poll_user:poll_pass@db:5432/poll_aggregator"

    # App
    webhook_base_url: str = "http://localhost:8000"
    admin_api_key: str = "changeme"


settings = Settings()
