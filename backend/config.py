from typing import Annotated

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )

    # --- External API keys ---
    APOLLO_API_KEY: str = ""
    ANTHROPIC_API_KEY: str = ""
    HUNTER_API_KEY: str = ""
    SLACK_WEBHOOK_URL: str = ""

    # --- Database ---
    DATABASE_URL: str = "sqlite:////data/crm.db"

    # --- Application ---
    SECRET_KEY: str = "change-me-in-production"

    # --- ICP (Ideal Customer Profile) filters ---
    # Provide as comma-separated strings in the environment, e.g.:
    #   ICP_TITLES=VP of Engineering,Head of Engineering,CTO
    ICP_TITLES: list[str] = []
    ICP_LOCATIONS: list[str] = []
    ICP_INDUSTRIES: list[str] = []
    ICP_EMPLOYEE_MIN: int = 50
    ICP_EMPLOYEE_MAX: int = 500

    # --- Anthropic model selection ---
    ANTHROPIC_MODEL_SCORING: str = "claude-haiku-4-5-20251001"
    ANTHROPIC_MODEL_WRITING: str = "claude-sonnet-4-6"

    # --- Prompt files ---
    PROMPT_PATH: str = "/app/prompts/icp_v1.md"

    @field_validator("ICP_TITLES", "ICP_LOCATIONS", "ICP_INDUSTRIES", mode="before")
    @classmethod
    def _parse_comma_separated(cls, v: str | list) -> list[str]:
        if isinstance(v, list):
            return [str(item).strip() for item in v if str(item).strip()]
        if isinstance(v, str):
            return [item.strip() for item in v.split(",") if item.strip()]
        return []


settings = Settings()
