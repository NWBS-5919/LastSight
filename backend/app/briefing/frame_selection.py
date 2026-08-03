"""참조 프레임 선택.

track_id의 프레임 후보들 중 선명도·가림 정도(추정)·박스 크기·탐지 신뢰도를 조합한 점수로
구조카드에 쓸 가장 알아보기 쉬운 프레임을 고른다.

각 지표는 이 후보군 안에서의 상대 순위(min-max 정규화)로 비교한다 — 절대 임계값을 쓰면
영상 해상도·조명에 따라 기준이 달라져 신뢰할 수 없기 때문.
"""

import cv2
import numpy as np

from app.inference.detector import Detection

BBox = tuple[float, float, float, float]

# 서 있는 성인 전신 박스의 대략적인 세로/가로 비율. 이 값에서 크게 벗어날수록
# 가려짐·측면 포즈 등으로 온전한 모습이 아닐 가능성이 높다고 "추정"한다 (근사치, 정밀 측정 아님).
_EXPECTED_ASPECT_RATIO = 2.2

_WEIGHT_SHARPNESS = 0.4
_WEIGHT_OCCLUSION = 0.3
_WEIGHT_SIZE = 0.2
_WEIGHT_CONFIDENCE = 0.1


def _crop(image: np.ndarray, bbox: BBox) -> np.ndarray | None:
    h, w = image.shape[:2]
    x1, y1, x2, y2 = bbox
    x1, y1 = max(0, int(x1)), max(0, int(y1))
    x2, y2 = min(w, int(x2)), min(h, int(y2))
    if x2 <= x1 or y2 <= y1:
        return None
    return image[y1:y2, x1:x2]


def _sharpness(frame_path: str, bbox: BBox) -> float:
    """박스 영역의 라플라시안 분산. 값이 클수록 선명(흐릿하지 않음)."""
    image = cv2.imread(frame_path)
    if image is None:
        return 0.0
    crop = _crop(image, bbox)
    if crop is None or crop.size == 0:
        return 0.0
    gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
    return float(cv2.Laplacian(gray, cv2.CV_64F).var())


def _occlusion_score(bbox: BBox) -> float:
    """전형적인 전신 박스 비율에 가까울수록 1에 가까운 점수(=덜 가려졌을 것으로 추정)."""
    x1, y1, x2, y2 = bbox
    width, height = max(x2 - x1, 1e-6), max(y2 - y1, 1e-6)
    aspect = height / width
    diff = abs(aspect - _EXPECTED_ASPECT_RATIO) / _EXPECTED_ASPECT_RATIO
    return max(0.0, 1.0 - diff)


def _normalize(values: list[float]) -> list[float]:
    lo, hi = min(values), max(values)
    if hi - lo < 1e-9:
        return [1.0 for _ in values]
    return [(v - lo) / (hi - lo) for v in values]


def select_reference_frame(candidates: list[tuple[str, Detection]]) -> tuple[str, BBox] | None:
    """(frame_path, Detection) 후보 리스트 중 가장 적합한 (frame_path, bbox_xyxy)를 반환.

    bbox_xyxy를 같이 반환하는 이유: 참조 프레임엔 다른 사람이 같이 찍혀 있을 수 있어서,
    프레임 경로만으로는 "이 카드가 누구를 가리키는지" 알 수 없다 — 호출부가 이 bbox로
    빨간 박스를 그려 명확히 표시한다. 후보 없으면 None."""
    if not candidates:
        return None

    sharpness_vals = [_sharpness(path, det.bbox_xyxy) for path, det in candidates]
    size_vals = [
        max(det.bbox_xyxy[2] - det.bbox_xyxy[0], 0) * max(det.bbox_xyxy[3] - det.bbox_xyxy[1], 0)
        for _path, det in candidates
    ]
    occlusion_vals = [_occlusion_score(det.bbox_xyxy) for _path, det in candidates]

    sharp_n = _normalize(sharpness_vals)
    size_n = _normalize(size_vals)

    best_index = 0
    best_score = -1.0
    for i, (_path, det) in enumerate(candidates):
        score = (
            _WEIGHT_SHARPNESS * sharp_n[i]
            + _WEIGHT_OCCLUSION * occlusion_vals[i]
            + _WEIGHT_SIZE * size_n[i]
            + _WEIGHT_CONFIDENCE * det.confidence
        )
        if score > best_score:
            best_score = score
            best_index = i

    best_path, best_det = candidates[best_index]
    return best_path, best_det.bbox_xyxy
