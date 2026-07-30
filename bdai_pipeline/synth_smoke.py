"""절대 원칙(CLAUDE.md)에 따라 실제 연기를 피우지 않고, person/helmet/vest 탐지 모델이
연기로 인한 저시야·부분 가림에도 견디는지 테스트하기 위한 디지털 합성 연기 augmentation.

실제 화재 CCTV 사진(AI Hub 176) 관찰 결과를 반영한 설계:
  - 연기는 균일한 안개가 아니라 뭉게뭉게 피어오르는 불규칙한 덩어리(난류) 형태
  - 중심부는 짙고(검정/회색), 가장자리로 갈수록 옅어지며 배경이 비쳐 보이는 반투명 그라디언트
  - 색상은 우리 라벨 정의(검정/회색/흰색 연기)의 3종 분포를 그대로 사용
  - 짙은 연기가 덮인 영역은 자연스럽게 부분 가림(occlusion) 효과를 겸함 — 별도 랜덤 박스 가림 불필요

사람 위치 자체는 바뀌지 않으므로 원본 바운딩박스 라벨을 그대로 재사용할 수 있다(재라벨링 불필요).
"""

from __future__ import annotations

import numpy as np
import cv2


def _fbm_noise(h: int, w: int, octaves: int, rng: np.random.Generator, base_cells: int = 4) -> np.ndarray:
    """저해상도 랜덤 노이즈를 여러 스케일로 겹쳐 블러 업샘플링하는 저비용 fBm(fractal noise) 근사.
    게임/그래픽스에서 흔히 쓰는 "blurred white noise" 트릭 — Perlin 라이브러리 없이 구현.
    base_cells: 가장 굵은 옥타브의 격자 칸 수 (작을수록 큰 덩어리)."""
    noise = np.zeros((h, w), dtype=np.float32)
    amplitude, total = 1.0, 0.0
    aspect = w / h
    for i in range(octaves):
        cells = base_cells * (2**i)
        sh = max(2, cells)
        sw = max(2, round(cells * aspect))
        layer = rng.random((sh, sw)).astype(np.float32)
        layer = cv2.resize(layer, (w, h), interpolation=cv2.INTER_CUBIC)
        noise += layer * amplitude
        total += amplitude
        amplitude *= 0.5
    noise /= total
    noise -= noise.min()
    noise /= max(noise.max(), 1e-6)
    return noise


def _soft_blobs(
    h: int,
    w: int,
    rng: np.random.Generator,
    boxes: list[tuple[float, float, float, float]] | None,
) -> np.ndarray:
    """연기 "뭉치"의 큰 구조를 만드는 부드러운 원형 블롭들(가우시안 감쇠, 최댓값 합성).

    boxes(원본 라벨의 [x,y,w,h] 목록)가 주어지면 **박스마다 하나씩** 블롭을 배치한다 —
    화면의 빈 공간에 임의로 연기가 생기는 걸 막고, 반드시 사람/객체 위치 주변에서만
    연기가 생기게 하기 위함이다. boxes가 없을 때만(앵커로 삼을 대상이 없을 때) 예외적으로
    화면 전체 랜덤 위치를 쓴다."""
    field = np.zeros((h, w), dtype=np.float32)
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)

    if boxes:
        for bx, by, bw, bh in boxes:
            # 박스 중심 근처에서 살짝 흔들어(가림이 항상 정중앙은 아니게) 다양성을 준다
            cx = bx + bw / 2 + rng.uniform(-0.25, 0.25) * bw
            cy = by + bh / 2 + rng.uniform(-0.25, 0.25) * bh
            # CCTV처럼 사람이 화면 대비 작게 찍힌 경우, 연기 크기는 "사람 크기"가 아니라
            # 그 사람을 확실히 감쌀 만한 정도로 키운다 (사람 크기의 1.2~2.2배 반경).
            rx = max(bw, bh) * rng.uniform(1.2, 2.2)
            ry = rx
            d2 = ((xx - cx) / max(rx, 1.0)) ** 2 + ((yy - cy) / max(ry, 1.0)) ** 2
            field = np.maximum(field, np.exp(-d2 * 1.4))
        return field

    # 앵커로 삼을 박스가 없는 경우에만 화면 전체 랜덤 위치로 대체
    n_blobs = int(rng.integers(1, 4))
    for _ in range(n_blobs):
        cx = rng.uniform(0.1, 0.9) * w
        cy = rng.uniform(0.1, 0.9) * h
        rx = rng.uniform(0.22, 0.45) * w
        ry = rng.uniform(0.22, 0.45) * h
        d2 = ((xx - cx) / max(rx, 1.0)) ** 2 + ((yy - cy) / max(ry, 1.0)) ** 2
        field = np.maximum(field, np.exp(-d2 * 1.4))
    return field


# coverage 단계별 국소 블롭의 최대 불투명도 범위. "light"는 실제로는 원본과 거의
# 구분이 안 될 만큼 약해서 의미가 없었으므로 빼고 medium/heavy만 쓴다.
_COVERAGE_PRESETS = {
    "medium": {"alpha_range": (0.48, 0.68)},
    "heavy": {"alpha_range": (0.68, 0.92)},
}


def _adaptive_smoke_color(image: np.ndarray, mask: np.ndarray, rng: np.random.Generator) -> np.ndarray:
    """연기가 덮일 자리의 실제 배경 밝기를 측정해서, 항상 대비가 나도록 연기 색(회색조)을
    자동으로 정한다. 고정된 색상값(예: 회색=110)을 쓰면 특정 샘플 배경에서는 잘 보여도
    다른 배경(더 밝거나 어두운 장면)에서는 묻혀버리는 문제가 있어 — 데이터셋 전체 수천 장에
    걸쳐 일반적으로 통하려면 이미지마다 배경에 맞춰 조정돼야 한다."""
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY).astype(np.float32)
    m = mask > 0.15
    local_bg = float(gray[m].mean()) if m.any() else float(gray.mean())

    offset = rng.uniform(55, 95)
    if local_bg >= 130:
        target = np.clip(local_bg - offset, 15, 70)  # 밝은 배경 → 어두운 연기
    elif local_bg <= 100:
        target = np.clip(local_bg + offset, 160, 235)  # 어두운 배경 → 밝은 연기
    else:
        target = np.clip(local_bg - offset, 15, 70) if rng.random() < 0.5 else np.clip(local_bg + offset, 160, 235)

    jitter = rng.uniform(-5, 5, size=3)  # 완전한 무채색은 부자연스러우니 아주 약한 색 편차
    return np.clip(target + jitter, 0, 255).astype(np.float32)


def add_synthetic_smoke(
    image: np.ndarray,
    rng: np.random.Generator,
    *,
    coverage: str = "random",
    boxes: list[tuple[float, float, float, float]] | None = None,
) -> np.ndarray:
    """image(BGR, uint8)에 합성 연기를 얹어 반환. coverage: "medium"|"heavy"|"random".
    boxes: [x,y,w,h] 픽셀 좌표 목록(원본 라벨) — 주어지면 연기가 사람 위치에 편향되어 얹힌다."""
    h, w = image.shape[:2]

    # 박스마다 하나씩 블롭이 생기므로(위 _soft_blobs 참고), 화면의 빈 공간에는
    # 연기가 생기지 않는다 — 사람/객체 주변에서만 연기가 생긴다.
    base = _soft_blobs(h, w, rng, boxes=boxes)
    texture = _fbm_noise(h, w, octaves=3, rng=rng, base_cells=6)
    density = base * (0.45 + 0.55 * texture)

    # 연기가 위로 갈수록(천장 쪽) 더 짙게 퍼지는 경향을 약하게 반영.
    # (주의) 여기서 "이미지 전체 최댓값 기준" 정규화를 하면 안 된다 — 박스가 여러 개일 때
    # 우연히 가장 강하게 나온 박스 하나가 기준(1.0)이 되면서 나머지 박스들이 상대적으로
    # 밀려 사라지는 버그가 있었다(사람 한 명만 진하게 나오고 나머지는 안 보이던 원인).
    # base와 texture가 이미 각각 0~1 범위라 곱해도 0~1을 벗어나지 않으므로 정규화 불필요.
    y_grad = np.linspace(0.85, 1.15, h, dtype=np.float32).reshape(-1, 1)
    density = np.clip(density * y_grad, 0, 1)
    density = np.clip((density - 0.2) / 0.8, 0, 1) ** 1.3

    if coverage == "random":
        coverage = rng.choice(["medium", "heavy"], p=[0.5, 0.5])
    preset = _COVERAGE_PRESETS[coverage]
    max_alpha = rng.uniform(*preset["alpha_range"])

    color = _adaptive_smoke_color(image, density, rng)

    alpha = (density * max_alpha)[:, :, None]
    out = image.astype(np.float32) * (1 - alpha) + color[None, None, :] * alpha

    # 짙은 연기가 낀 장면은 전체적으로 시야가 흐려지고 대비가 낮아지는 경향 반영
    avg_density = float(density.mean() * max_alpha)
    if avg_density > 0.03:
        k = max(1, int(avg_density * 14)) | 1  # 홀수 커널
        blurred = cv2.GaussianBlur(out, (k, k), 0)
        out = out * (1 - avg_density * 0.6) + blurred * (avg_density * 0.6)
        out = (out - 127.5) * (1 - avg_density * 0.25) + 127.5  # 대비 살짝 낮춤

    return np.clip(out, 0, 255).astype(np.uint8)
