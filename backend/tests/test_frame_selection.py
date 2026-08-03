import cv2
import numpy as np

from app.briefing.frame_selection import select_reference_frame
from app.inference.detector import Detection
from app.models.schemas import ObjectClass


def _det(bbox, confidence=0.9) -> Detection:
    return Detection(object_class=ObjectClass.PERSON, confidence=confidence, bbox_xyxy=bbox)


def _save(path, image) -> str:
    cv2.imwrite(str(path), image)
    return str(path)


def _sharp_image(size=200) -> np.ndarray:
    rng = np.random.default_rng(0)
    return rng.integers(0, 255, (size, size, 3), dtype=np.uint8)


def _flat_image(size=200) -> np.ndarray:
    return np.full((size, size, 3), 128, dtype=np.uint8)


def test_prefers_sharper_frame(tmp_path):
    sharp_path = _save(tmp_path / "sharp.jpg", _sharp_image())
    flat_path = _save(tmp_path / "flat.jpg", _flat_image())

    bbox = (0, 0, 200, 200)  # 정사각형이라 두 후보 다 occlusion 점수는 동일
    result = select_reference_frame([(sharp_path, _det(bbox)), (flat_path, _det(bbox))])
    assert result == (sharp_path, bbox)


def test_prefers_typical_aspect_ratio_when_sharpness_equal(tmp_path):
    # 두 후보 모두 같은 이미지 내용(=선명도 동일)이지만 파일을 따로 저장해 결과로 구분 가능하게 함
    typical_path = _save(tmp_path / "typical.jpg", _flat_image())
    odd_path = _save(tmp_path / "odd.jpg", _flat_image())

    typical_bbox = (0, 0, 100, 220)  # 세로/가로 ≈ 2.2 (전형적인 전신 비율)
    odd_bbox = (0, 0, 100, 800)  # 매우 길쭉함 → 가려짐/이상 포즈로 추정

    result = select_reference_frame(
        [(typical_path, _det(typical_bbox)), (odd_path, _det(odd_bbox))]
    )
    assert result == (typical_path, typical_bbox)


def test_prefers_larger_box_when_others_equal(tmp_path):
    small_path = _save(tmp_path / "small.jpg", _flat_image())
    large_path = _save(tmp_path / "large.jpg", _flat_image())

    small_bbox = (0, 0, 50, 110)  # 비율 2.2 유지
    large_bbox = (0, 0, 100, 220)  # 같은 비율, 더 큼

    result = select_reference_frame(
        [(small_path, _det(small_bbox)), (large_path, _det(large_bbox))]
    )
    assert result == (large_path, large_bbox)


def test_empty_candidates_returns_none():
    assert select_reference_frame([]) is None


def test_missing_file_does_not_crash_and_loses_to_real_file(tmp_path):
    real_path = _save(tmp_path / "real.jpg", _sharp_image())
    bbox = (0, 0, 200, 200)

    result = select_reference_frame(
        [("/no/such/file.jpg", _det(bbox)), (real_path, _det(bbox))]
    )
    assert result == (real_path, bbox)
