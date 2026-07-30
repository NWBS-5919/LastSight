"""BDAI(Superb AI) SDK 클라이언트 초기화 공용 모듈.

bdai_pipeline/ 아래 모든 스크립트는 여기서 만든 client를 사용한다.
환경변수 SUPERB_AI_TENANT / SUPERB_AI_API_KEY 를 .env에 설정해두면 Client()만 호출해도 인증된다.
"""

from dotenv import load_dotenv
from superb_ai import Client

load_dotenv()


def get_client() -> Client:
    """superb_ai.Client 인스턴스를 반환.

    .env에 SUPERB_AI_TENANT / SUPERB_AI_API_KEY가 없으면 Client() 생성 시점에
    AuthenticationError 등으로 실패한다 (SDK가 환경변수를 직접 읽음).
    """
    return Client()
