from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Configuration lue depuis les variables d'environnement (ou le fichier .env)."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "Chess Opening Coach API"
    app_env: str = "development"
    api_v1_prefix: str = "/api/v1"
    backend_port: int = 8000


settings = Settings()
