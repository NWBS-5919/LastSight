"""탐지 모델 추론 래퍼.

BDAI 플랫폼에서 학습했든(모델 레지스트리 배포 엔드포인트 호출) 로컬/Colab에서 학습했든(가중치 파일 로드)
이 모듈 뒤로 숨기고, 나머지 코드(app/tracking, app/rules)는 아래 인터페이스만 바라보게 한다.

CLAUDE.md 4-1 클래스 정의(person/helmet/vest)를 그대로 따를 것.
"""

from dataclasses import dataclass

from app.models.schemas import ObjectClass


@dataclass
class Detection:
    object_class: ObjectClass
    confidence: float
    bbox_xyxy: tuple[float, float, float, float]


def detect(frame) -> list[Detection]:  # noqa: ANN001 - frame 타입은 사용할 영상 처리 라이브러리 확정 후 지정
    """단일 프레임에서 person/helmet/vest를 탐지해 Detection 리스트로 반환.

    TODO: BDAI 배포 엔드포인트(REST) 호출 또는 로컬 가중치(.pt/.onnx) 추론으로 구현.
    """
    raise NotImplementedError
