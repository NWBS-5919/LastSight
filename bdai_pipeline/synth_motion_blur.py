"""사람이 빠르게 움직일 때(달리기 등) 생기는 모션 블러를 디지털로 합성하는 augmentation.

development_log.md 22번 참고: 자체 촬영 CCTV 테스트에서 뛰는 사람이 거의 탐지되지 않는
문제를 발견했다. 원인은 두 가지가 겹친 것으로 확인됐다 — (1) 뛰는 자세 자체를 학습한 적이
없음(→ Roboflow runningperson 데이터로 보강), (2) 그 자세가 실제로는 흐릿하게 찍힘(→ 이 파일).
새 자세 데이터는 대부분 맑은 날 정지 사진에 가까워 흐림을 못 가르쳐주므로, 이 augmentation을
그 위에 얹어 "흐릿하게 뛰는 사람"이라는, 지금까지 어디에도 없던 조합을 만든다.

카메라는 고정, 사람만 움직인다고 가정 — 배경은 선명하게 두고 사람 영역에만 방향성 블러를
국소적으로 적용한다(실제 셔터 노출 중 피사체만 이동해 번지는 물리적 현상과 동일).
연기 합성(synth_smoke.py)과 마찬가지로 사람 위치 자체는 바뀌지 않으므로 원본 바운딩박스
라벨을 그대로 재사용할 수 있다(재라벨링 불필요).
"""

from __future__ import annotations

import cv2
import numpy as np


def _motion_kernel(length: int, angle_deg: float) -> np.ndarray:
    """길이 length, 각도 angle_deg인 직선 방향 블러 커널(정규화된 선형 커널)."""
    size = max(length, 3) | 1  # 홀수로 맞춤
    kernel = np.zeros((size, size), dtype=np.float32)
    kernel[size // 2, :] = 1.0
    center = (size / 2 - 0.5, size / 2 - 0.5)
    rot = cv2.getRotationMatrix2D(center, angle_deg, 1.0)
    kernel = cv2.warpAffine(kernel, rot, (size, size))
    total = kernel.sum()
    if total > 0:
        kernel /= total
    return kernel


def add_synthetic_motion_blur(
    image: np.ndarray,
    rng: np.random.Generator,
    boxes: list[tuple[float, float, float, float]] | None,
    *,
    strength: str = "random",
) -> np.ndarray:
    """사람 바운딩박스(x, y, w, h) 영역에만 방향성 모션 블러를 합성해 반환.

    strength: "light"|"medium"|"heavy"|"random" — 블러 길이(박스 대비 비율) 조절.
    boxes가 없으면 원본을 그대로 반환한다(적용할 위치가 없으므로).
    """
    if not boxes:
        return image.copy()

    out = image.astype(np.float32)
    h_img, w_img = image.shape[:2]

    strength_ranges = {
        "light": (0.08, 0.15),
        "medium": (0.15, 0.25),
        "heavy": (0.25, 0.35),
    }

    for x, y, w, h in boxes:
        if strength == "random":
            # CCTV 박스는 대부분 작아서(중앙값 ~57px) 강한 블러 비중이 높으면 사람 형태가
            # 통째로 뭉개진다 — light/medium 위주로 치우치게 샘플링.
            level = rng.choice(["light", "medium", "heavy"], p=[0.45, 0.4, 0.15])
        else:
            level = strength
        lo, hi = strength_ranges[level]
        blur_ratio = rng.uniform(lo, hi)

        # 사람은 보통 카메라를 기준으로 좌우(또는 약간 대각선)로 이동하므로 각도를 그 쪽으로 치우치게 샘플링
        angle = float(rng.normal(loc=0.0, scale=20.0))
        kernel_len = max(3, int(round(w * blur_ratio)))
        kernel = _motion_kernel(kernel_len, angle)

        pad = kernel_len
        x0, y0 = max(0, int(x) - pad), max(0, int(y) - pad)
        x1, y1 = min(w_img, int(x + w) + pad), min(h_img, int(y + h) + pad)
        if x1 <= x0 or y1 <= y0:
            continue

        region = out[y0:y1, x0:x1]
        blurred = cv2.filter2D(region, -1, kernel, borderType=cv2.BORDER_REPLICATE)

        # 박스 경계에서 딱 잘리지 않도록 가우시안으로 부드럽게 풀어준 마스크로 블렌딩
        mask = np.zeros(region.shape[:2], dtype=np.float32)
        bx0, by0 = int(x) - x0, int(y) - y0
        bx1, by1 = bx0 + int(w), by0 + int(h)
        mask[max(0, by0) : max(0, by1), max(0, bx0) : max(0, bx1)] = 1.0
        feather = max(3, kernel_len // 2) | 1
        mask = cv2.GaussianBlur(mask, (feather, feather), 0)
        mask3 = mask[:, :, None]

        out[y0:y1, x0:x1] = region * (1 - mask3) + blurred * mask3

    return np.clip(out, 0, 255).astype(np.uint8)
