"""Settings from the environment / .env. Missing keys fail where they are used."""

from pathlib import Path

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_ignore_empty=True, extra="ignore")

    exa_api_key: SecretStr | None = None
    typesafe_api_key: SecretStr | None = None
    deepgram_api_key: SecretStr | None = None
    vapi_api_key: SecretStr | None = None
    vapi_server_secret: SecretStr | None = None
    vapi_assistant_id: str | None = None
    vapi_llm_provider: str = "openai"
    vapi_llm_model: str = "gpt-4.1"
    vapi_voice_id: str = "asteria"
    jev_model: str = "jev-1.13.0"
    deepgram_stt_model: str = "nova-3"
    deepgram_tts_model: str = "aura-2-thalia-en"
    bling_region: str = "San Francisco Bay Area, CA"
    bling_data_dir: Path = Path("data")
    public_base_url: str | None = None
    exa_timeout_s: float = 5.0
    jev_timeout_s: float = 2.5
    plan_deadline_s: float = 8.0


def require(value: SecretStr | None, name: str) -> str:
    if value is None:
        raise RuntimeError(f"{name} is not set")
    return value.get_secret_value()
