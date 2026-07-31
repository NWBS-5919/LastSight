"""helmet/vest 라벨 박스에만 국소적으로 색상(hue)을 무작위로 바꿔치는 augmentation.

development_log.md: 실측 결과 helmet/vest 신호의 ~93~95%를 차지하는 SFCHD가 색상 자체도
편향돼 있었다 (vest 66.8%가 파랑 한 가지). "vest=파랑"처럼 색만 보고 클래스를 맞히는 얕은
상관관계를 모델이 학습할 위험이 있어, 같은 사람·같은 형태의 helmet/vest를 색만 무작위로
바꾼 복사본을 추가해 색과 클래스 사이의 상관관계를 깨뜨린다.

모션 블러(synth_motion_blur.py)와 달리 색상은 사람 단위로 묶을 이유가 없다 — 실제로도 한
사람이 쓴 헬멧과 조끼 색이 서로 무관할 수 있으므로 박스마다 독립적으로 무작위 색을 적용한다.
"""

from __future__ import annotations

import cv2
import numpy as np


def _jitter_region(
    out: np.ndarray,
    box: tuple[float, float, float, float],
    hue_shift: float,
    sat_scale: float,
    val_scale: float,
) -> None:
    x, y, w, h = box
    h_img, w_img = out.shape[:2]
    x0, y0 = max(0, int(x)), max(0, int(y))
    x1, y1 = min(w_img, int(x + w)), min(h_img, int(y + h))
    if x1 <= x0 or y1 <= y0:
        return

    region = out[y0:y1, x0:x1].astype(np.uint8)
    hsv = cv2.cvtColor(region, cv2.COLOR_BGR2HSV).astype(np.float32)
    hsv[..., 0] = (hsv[..., 0] + hue_shift) % 180
    hsv[..., 1] = np.clip(hsv[..., 1] * sat_scale, 0, 255)
    hsv[..., 2] = np.clip(hsv[..., 2] * val_scale, 0, 255)
    jittered = cv2.cvtColor(hsv.astype(np.uint8), cv2.COLOR_HSV2BGR).astype(np.float32)

    # 박스 경계에서 색이 뚝 끊기지 않도록 가장자리를 페더링
    mask = np.ones(region.shape[:2], dtype=np.float32)
    feather = max(3, min(region.shape[0], region.shape[1]) // 6) | 1
    mask = cv2.GaussianBlur(mask, (feather, feather), 0)
    mask3 = mask[:, :, None]

    out[y0:y1, x0:x1] = region.astype(np.float32) * (1 - mask3) + jittered * mask3


def add_synthetic_color_jitter(
    image: np.ndarray,
    rng: np.random.Generator,
    annotations: list[tuple[str, tuple[float, float, float, float]]] | None,
    *,
    target_classes: tuple[str, ...] = ("helmet", "vest"),
) -> np.ndarray:
    """(class_name, bbox) 목록을 받아 target_classes에 해당하는 박스마다 독립적으로
    무작위 색상 변형을 적용해 반환. 대상 박스가 없으면 원본을 그대로 반환한다."""
    targets = [box for name, box in (annotations or []) if name in target_classes]
    if not targets:
        return image.copy()

    out = image.astype(np.float32)
    for box in targets:
        hue_shift = float(rng.uniform(0, 180))  # 전체 색상환에서 무작위 회전
        sat_scale = float(rng.uniform(0.6, 1.4))
        val_scale = float(rng.uniform(0.8, 1.2))
        _jitter_region(out, box, hue_shift, sat_scale, val_scale)

    return np.clip(out, 0, 255).astype(np.uint8)
