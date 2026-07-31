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

development_log.md 25번: 처음엔 person/helmet/vest 박스를 각각 독립적으로 무작위 블러
처리해서, 한 사람 안에서 부위마다 다른 방향·세기로 흐려지는 비현실적인 결과가 나올 수 있었다
(헬멧/조끼를 구분하는 미세한 단서가 부위마다 제각각 뭉개져 판별력을 해칠 위험). 그래서 이제는
**person 박스 하나당 블러 파라미터(각도·세기)를 한 번만 정하고, 그 person과 겹치는
helmet/vest 등 다른 박스는 같은 파라미터를 그대로 물려받는다** — 실제로 한 사람이 움직이면
신체 부위 전체가 같은 방향·세기로 함께 흐려지는 것과 동일하다.
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


def _overlap_ratio(a: tuple[float, float, float, float], b: tuple[float, float, float, float]) -> float:
    """겹치는 영역 / 더 작은 박스 면적 — helmet/vest가 person 안에 포함되는지 보는 "포함 비율"
    (IoU는 크기 차이가 크면 낮게 나와 person처럼 훨씬 큰 박스와의 관계를 보기엔 부적절)."""
    ax, ay, aw, ah = a
    bx, by, bw, bh = b
    ix1, iy1 = max(ax, bx), max(ay, by)
    ix2, iy2 = min(ax + aw, bx + bw), min(ay + ah, by + bh)
    inter = max(0.0, ix2 - ix1) * max(0.0, iy2 - iy1)
    smaller = min(aw * ah, bw * bh)
    return inter / smaller if smaller > 0 else 0.0


def _blur_region(out: np.ndarray, box: tuple[float, float, float, float], kernel: np.ndarray, kernel_len: int) -> None:
    x, y, w, h = box
    h_img, w_img = out.shape[:2]
    pad = kernel_len
    x0, y0 = max(0, int(x) - pad), max(0, int(y) - pad)
    x1, y1 = min(w_img, int(x + w) + pad), min(h_img, int(y + h) + pad)
    if x1 <= x0 or y1 <= y0:
        return

    region = out[y0:y1, x0:x1]
    blurred = cv2.filter2D(region, -1, kernel, borderType=cv2.BORDER_REPLICATE)

    mask = np.zeros(region.shape[:2], dtype=np.float32)
    bx0, by0 = int(x) - x0, int(y) - y0
    bx1, by1 = bx0 + int(w), by0 + int(h)
    mask[max(0, by0) : max(0, by1), max(0, bx0) : max(0, bx1)] = 1.0
    feather = max(3, kernel_len // 2) | 1
    mask = cv2.GaussianBlur(mask, (feather, feather), 0)
    mask3 = mask[:, :, None]

    out[y0:y1, x0:x1] = region * (1 - mask3) + blurred * mask3


def add_synthetic_motion_blur(
    image: np.ndarray,
    rng: np.random.Generator,
    annotations: list[tuple[str, tuple[float, float, float, float]]] | None,
    *,
    strength: str = "random",
) -> np.ndarray:
    """(class_name, bbox) 목록을 받아 person 단위로 일관된 방향성 모션 블러를 합성해 반환.

    person 박스마다 블러 파라미터(각도·세기)를 한 번만 뽑고, 그 person과 많이 겹치는
    (포함 비율 50% 이상) helmet/vest 등 다른 박스에는 같은 파라미터를 그대로 적용한다.
    person이 아닌 박스만 있는 경우(예: 이 데이터셋에 person 라벨이 없음)엔 그 박스들을
    각자 독립적인 person처럼 취급해 블러를 적용한다.

    strength: "light"|"medium"|"heavy"|"random" — 블러 길이(박스 대비 비율) 조절.
    annotations가 없으면 원본을 그대로 반환한다(적용할 위치가 없으므로).
    """
    if not annotations:
        return image.copy()

    out = image.astype(np.float32)

    strength_ranges = {
        "light": (0.08, 0.15),
        "medium": (0.15, 0.25),
        "heavy": (0.25, 0.35),
    }

    person_boxes = [box for name, box in annotations if name == "person"]
    other = [(name, box) for name, box in annotations if name != "person"]
    if not person_boxes:
        # person 라벨이 없는 소스(예: 뛰는 자세 데이터는 class_name="person"으로 이미 매핑돼 있어
        # 보통 여기 안 걸리지만, 방어적으로) — 남은 박스를 각자 기준으로 처리.
        person_boxes = [box for _, box in other]
        other = []

    for px, py, pw, ph in person_boxes:
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
        kernel_len = max(3, int(round(pw * blur_ratio)))
        kernel = _motion_kernel(kernel_len, angle)

        _blur_region(out, (px, py, pw, ph), kernel, kernel_len)
        for _name, box in other:
            if _overlap_ratio(box, (px, py, pw, ph)) >= 0.5:
                _blur_region(out, box, kernel, kernel_len)

    return np.clip(out, 0, 255).astype(np.uint8)
