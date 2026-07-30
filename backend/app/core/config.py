from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

_PROJECT_ROOT_ENV = Path(__file__).resolve().parents[3] / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=_PROJECT_ROOT_ENV, env_file_encoding="utf-8", extra="ignore")

    superb_ai_tenant: str = ""
    superb_ai_api_key: str = ""
    ppe_deployment_id: str = ""  # BDAI에 배포한 person/helmet/vest 모델의 deployment ID
    backend_host: str = "0.0.0.0"
    backend_port: int = 8000


@lru_cache
def get_settings() -> Settings:
    return Settings()
