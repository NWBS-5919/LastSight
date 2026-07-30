"""백엔드에서 BDAI SDK를 쓸 때 공용으로 사용하는 클라이언트.

bdai_pipeline/client.py와 별개인 이유: bdai_pipeline은 project root에서 `python -m`으로
실행되고, backend는 backend/ 아래에서 uvicorn으로 실행돼 sys.path 루트가 다르다.
둘 다 같은 .env(app/core/config.py의 Settings)를 본다.
"""

from functools import lru_cache

from superb_ai import Client

from app.core.config import get_settings


@lru_cache
def get_bdai_client() -> Client:
    settings = get_settings()
    return Client(tenant=settings.superb_ai_tenant, api_key=settings.superb_ai_api_key)
