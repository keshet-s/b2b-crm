import json
from typing import Any, Type, Union, get_args, get_origin

from pydantic.fields import FieldInfo
from pydantic_settings import BaseSettings, DotEnvSettingsSource, EnvSettingsSource, SettingsConfigDict


def _is_list_annotation(annotation: Any) -> bool:
    """Return True if the annotation is list[...] or Optional[list[...]]."""
    if annotation is None:
        return False
    origin = get_origin(annotation)
    if origin is list:
        return True
    # Optional[list[X]] == Union[list[X], None]
    if origin is Union:
        return any(get_origin(a) is list for a in get_args(annotation))
    return False


class _CsvMixin:
    """Allow comma-separated strings as well as JSON arrays for list[str] settings.

    pydantic-settings calls prepare_field_value() *before* any pydantic
    validator can run.  In older releases (≤2.3) it gates on value_is_complex;
    in newer releases (≥2.6) that flag is always False and the method calls
    decode_complex_value unconditionally.  Checking the field annotation
    directly is version-agnostic.
    """

    def prepare_field_value(
        self, field_name: str, field: FieldInfo, value: Any, value_is_complex: bool = False
    ) -> Any:
        if isinstance(value, str) and _is_list_annotation(getattr(field, "annotation", None)):
            v = value.strip()
            if not v:
                return None  # triggers the field's default ([])
            try:
                return json.loads(v)
            except (json.JSONDecodeError, ValueError):
                # Accept comma-separated strings: "VP of Engineering,CTO"
                return [item.strip() for item in v.split(",") if item.strip()]
        return super().prepare_field_value(field_name, field, value, value_is_complex)  # type: ignore[safe-super]


class _CsvEnvSource(_CsvMixin, EnvSettingsSource):
    """OS environment variables with CSV-list support."""


class _CsvDotEnvSource(_CsvMixin, DotEnvSettingsSource):
    """Dotenv file with CSV-list support (used when running outside Docker)."""


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

    # --- Data provider selection ---
    # Switch to "apollo" in .env when upgrading to Apollo Basic plan
    ACTIVE_LEAD_PROVIDER: str = "pdl"  # Valid values: "pdl", "apollo"

    # --- PeopleDataLabs ---
    PDL_API_KEY: str = ""

    # --- Credit budgeting (safety caps per sourcing run) ---
    PDL_MAX_CREDITS_PER_RUN: int = 50       # max PDL credits one sourcing run may consume
    HUNTER_MAX_SEARCHES_PER_DAY: int = 20   # leave 5/mo buffer on free tier

    # --- Database ---
    DATABASE_URL: str = "sqlite:////data/crm.db"

    # --- Application ---
    SECRET_KEY: str = "change-me-in-production"

    # --- ICP (Ideal Customer Profile) filters ---
    # Accepts either a JSON array or a comma-separated string, e.g.:
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

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: Type["Settings"],
        init_settings,
        env_settings,
        dotenv_settings,
        **kwargs,  # 'secrets_dir' (<2.3) or 'file_secret_settings' (≥2.3)
    ) -> tuple:
        secrets = next(iter(kwargs.values()), None)
        sources: list = [init_settings, _CsvEnvSource(settings_cls), _CsvDotEnvSource(settings_cls)]
        if secrets is not None:
            sources.append(secrets)
        return tuple(sources)


settings = Settings()
