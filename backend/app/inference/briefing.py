"""상황 타임라인의 "요약 브리핑" 버튼 — 이 순간까지 시스템이 실제로 기록한 데이터를 근거로
Gemini에게 짧은 한국어 브리핑 문장을 쓰게 한다.

ZERO는 자유 문장을 만들어주는 모델이 아니라서(situation_probe.py 참고) 요약 문장 생성에는
쓸 수 없다. 대신 BDAI 테넌트에 이미 연결돼 있는 Gemini 게이트웨이(OpenAI SDK 호환,
플랫폼 → 모델 → gemini 화면에서 확인함)를 쓴다 — 기존 superb_ai_api_key/tenant를 그대로
재사용하므로 새 키 발급이 필요 없다.

이 요약은 CLAUDE.md 2번(절대 원칙)을 위반할 위험이 가장 큰 기능이다 — "전원 안전", "대피
완료", "몇 명 남았다" 같은 확정적 문장을 AI가 만들어낼 수 있기 때문에, 시스템 프롬프트에
금지 표현을 명시적으로 박아둔다. 호출 실패는 다른 추론 모듈과 같은 원칙으로 예외를 던지지
않고 None을 반환한다(있으면 좋은 보조 기능이지 안전 판정의 필수 경로가 아님).
"""

from __future__ import annotations

import base64
import json
import logging
import re
from datetime import datetime
from functools import lru_cache
from pathlib import Path

from openai import OpenAI

from app.core.config import get_settings
from app.models.schemas import FireAlert, PpeViolationLogEntry, ZoneSituationLogEntry

logger = logging.getLogger(__name__)

_DEMO_DATA_DIR = Path(__file__).resolve().parents[2] / "data" / "demo"
_MODEL = "gemini-3.5-flash"

# 2026-08-04: 처음엔 2~4문장짜리 줄글 문단을 그대로 돌려줬는데, 관리자가 급하게 훑어보기엔
# 가독성이 떨어진다는 피드백을 받았다(실측) — 한 줄 headline + 짧은 사실 문장 여러 개(points)로
# 구조를 나눠서 프론트엔드가 카드/불릿 형태로 그릴 수 있게 JSON으로만 답하게 한다.
_SYSTEM_PROMPT = """너는 산업안전 CCTV 관제 대시보드의 브리핑 보조 AI다. 관리자가 지금까지의
상황을 한눈에 파악하도록 아래 JSON 형식으로만 답한다 (다른 설명·마크다운 코드블록 없이 순수
JSON 객체 하나만 출력):

{"headline": "지금 상황을 한 줄로 요약 (20자 내외)", "points": ["핵심 사실 1개씩 담은 짧은 문장 (25자 내외)", "..."]}

points는 3~5개, 각 항목은 하나의 사실만 담은 짧은 문장으로 쓴다(예: "B구역 4명 관측 중",
"쓰러진 인원 2명 확인 필요").

절대 지켜야 할 규칙(위반 시 시스템 안전 원칙에 어긋남):
- 아래에 주어진 데이터와 이미지에서 실제로 관측된 사실만 말한다. 추측이나 없는 정보를 지어내지 않는다.
- "전원 안전", "전원 대피 완료", "모두 무사함" 같은 확정적 안전 선언을 절대 하지 않는다 — 이 시스템은 CCTV 관측 범위 안의 정보만 다루는 보조 시스템이다.
- 공장 전체 재실 인원이나 잔류 인원을 확정하지 않는다. "관측된 인원" 수준으로만 말한다.
- 관측이 끊긴 사람을 안전하다거나 위험하다고 단정하지 않는다.
- 사람의 신원, 성별, 나이, 인종, 체형을 추정하지 않는다. 복장 색상만으로 동일인이라고 단정하지 않는다.
- 과장하지 말고, 확인이 필요한 부분은 "확인 필요"로 표현한다.
- disclaimer(추정 정보라는 문구)는 화면에서 별도로 이미 표시하므로 points에 넣지 않는다."""


@lru_cache
def _get_client() -> OpenAI:
    settings = get_settings()
    return OpenAI(
        base_url=f"https://llm.bdai.superb-ai.com/tenants/{settings.superb_ai_tenant}/llm",
        api_key=settings.superb_ai_api_key,
    )


def _encode_image(frame_path_rel: str | None) -> str | None:
    if not frame_path_rel:
        return None
    rel = frame_path_rel.removeprefix("/demo-frames/")
    path = _DEMO_DATA_DIR / rel
    if not path.exists():
        return None
    b64 = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:image/jpeg;base64,{b64}"


def _build_context_text(
    now: datetime,
    fire_alert: FireAlert | None,
    zone_person_counts: dict[str, int],
    situation_checks: list[ZoneSituationLogEntry],
    ppe_events: list[PpeViolationLogEntry],
) -> str:
    lines = [f"지금 시각: {now.isoformat()}"]

    if fire_alert is None:
        lines.append("화재경보: 발생하지 않음 (평상시 모드)")
    else:
        triggered_at = datetime.fromisoformat(fire_alert.triggered_at)
        elapsed = max(0, int((now - triggered_at).total_seconds()))
        lines.append(f"화재경보: {fire_alert.triggered_at}에 발생, 지금까지 약 {elapsed}초 경과")

    if zone_person_counts:
        counts_text = ", ".join(f"{zone} {count}명" for zone, count in zone_person_counts.items())
        lines.append(f"현재 구역별 관측 인원: {counts_text}")
    else:
        lines.append("현재 구역별 관측 인원: 관측된 사람 없음")

    if situation_checks:
        # 지금까지 확인된 카테고리별 최고 인원 수(타임라인 이정표와 같은 집계 방식) — 매초
        # 쌓이는 전체 기록 대신, 상황이 실제로 악화된 최대치만 전달한다.
        running_max: dict[str, int] = {}
        for entry in situation_checks:
            for zone in entry.zones:
                for category, count in zone.breakdown.items():
                    if category == "체류중" or count <= 0:
                        continue
                    running_max[category] = max(running_max.get(category, 0), count)
        if running_max:
            worst_text = ", ".join(f"{cat} 최대 {n}명" for cat, n in running_max.items())
            lines.append(f"화재 이후 2차 확인에서 감지된 우려 상황(누적 최고치): {worst_text}")
        latest = situation_checks[-1]
        latest_text = " / ".join(
            f"{z.zone_id} 총 {z.total}명(" + ", ".join(f"{c} {n}명" for c, n in z.breakdown.items() if n > 0) + ")" for z in latest.zones
        )
        lines.append(f"가장 최근 2차 확인({latest.at}): {latest_text}")

    if ppe_events:
        lines.append(f"오늘 PPE(안전모/안전조끼) 미착용 적발: 총 {len(ppe_events)}건")
        recent = ppe_events[-3:]
        for e in recent:
            still = e.reviewed_helmet or e.helmet_state, e.reviewed_vest or e.vest_state
            lines.append(f"  - {e.at} {e.zone or '구역 미상'}: 헬멧={still[0]}, 조끼={still[1]}")

    return "\n".join(lines)


_JSON_BLOCK_RE = re.compile(r"\{.*\}", re.DOTALL)


def _parse_summary(raw: str) -> tuple[str, list[str]] | None:
    """Gemini 응답에서 headline/points를 뽑는다. 가끔 ```json 코드블록으로 감싸거나
    앞뒤에 군더더기 텍스트를 붙이는 경우가 있어(실측), 가장 바깥 {...} 블록만 잘라내
    파싱한다. 그래도 실패하면 통째로 하나의 point로 만들어 최소한 뭐라도 보여준다."""
    match = _JSON_BLOCK_RE.search(raw)
    if match:
        try:
            data = json.loads(match.group(0))
            headline = str(data.get("headline", "")).strip()
            points = [str(p).strip() for p in data.get("points", []) if str(p).strip()]
            if headline and points:
                return headline, points
        except (json.JSONDecodeError, AttributeError):
            pass
    stripped = raw.strip()
    if not stripped:
        return None
    return "상황 요약", [stripped]


def generate_situation_summary(
    *,
    now: datetime,
    fire_alert: FireAlert | None,
    zone_person_counts: dict[str, int],
    situation_checks: list[ZoneSituationLogEntry],
    ppe_events: list[PpeViolationLogEntry],
    current_frame_path: str | None,
) -> tuple[str, list[str]] | None:
    context_text = _build_context_text(now, fire_alert, zone_person_counts, situation_checks, ppe_events)

    image_paths = [current_frame_path]
    if situation_checks:
        image_paths.append(situation_checks[0].frame_path)  # 화재 발생 직후 첫 확인 프레임
    image_urls = [u for p in image_paths for u in [_encode_image(p)] if u]

    content: list[dict] = [{"type": "text", "text": context_text}]
    for url in image_urls[:2]:
        content.append({"type": "image_url", "image_url": {"url": url}})

    try:
        client = _get_client()
        response = client.chat.completions.create(
            model=_MODEL,
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": content},
            ],
            # Gemini 3.x는 응답 전에 내부적으로 "생각" 토큰을 먼저 쓰고(실측: 짧은 질문에도
            # 400 토큰 예산이 사고 과정만으로 다 소진돼 답변이 통째로 잘림, finish_reason="length"),
            # 그 사고 토큰도 이 한도 안에서 같이 계산된다 — 실제 답변 몇 문장을 확보하려면
            # 넉넉하게 잡아야 한다(게이트웨이 한도인 8,192 이내).
            max_tokens=2048,
        )
        raw = response.choices[0].message.content
        if not raw:
            return None
        return _parse_summary(raw)
    except Exception:
        logger.warning("briefing: Gemini 요약 생성 실패", exc_info=True)
        return None
