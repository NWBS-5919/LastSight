"""영상 옆 "구조 브리핑" 챗봇 — 이 순간까지 시스템이 실제로 기록한 데이터(+필요하면 특정
시점 사진)를 근거로 Gemini가 관리자의 자유 질문에 답하게 한다.

ZERO는 자유 문장을 만들어주는 모델이 아니라서(situation_probe.py 참고) 대화형 답변 생성에는
쓸 수 없다. 대신 BDAI 테넌트에 이미 연결돼 있는 Gemini 게이트웨이(OpenAI SDK 호환,
플랫폼 → 모델 → gemini 화면에서 확인함)를 쓴다 — 기존 superb_ai_api_key/tenant를 그대로
재사용하므로 새 키 발급이 필요 없다.

이 챗봇은 CLAUDE.md 2번(절대 원칙)을 위반할 위험이 가장 큰 기능이다 — "전원 안전", "대피
완료", "몇 명 남았다" 같은 확정적 문장을 AI가 만들어낼 수 있고, 특히 관리자가 "그래서 다
안전한 거 맞지?" 같은 유도신문을 해도 원칙을 지켜야 한다. 시스템 프롬프트에 금지 표현을
명시적으로 박아두고, 매 턴 최신 데이터로 다시 grounding한다. 호출 실패는 다른 추론 모듈과
같은 원칙으로 예외를 던지지 않고 None을 반환한다(있으면 좋은 보조 기능이지 안전 판정의
필수 경로가 아니다).

2026-08-05: 원래 있던 "요약 브리핑" 버튼(한 번 누르면 headline+points를 한 번만 반환하는
단발성 호출, generate_situation_summary)을 이 모듈로 완전히 대체했다 — 챗봇의 첫 메시지가
그 역할을 그대로 하고, 후속 질문까지 받을 수 있어 상위 호환이다. 시간 힌트(특정 시점을
묻는 질문)를 인식해 그 시점에 저장된 사진을 찾아 답변에 곁들이는 기능이 핵심 차별점 —
"그때 실제로 뭐가 보였는지"를 관리자·심사위원이 직접 캐물어볼 수 있게 한다."""

from __future__ import annotations

import base64
import json
import logging
import re
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from functools import lru_cache
from pathlib import Path
from zoneinfo import ZoneInfo

from openai import OpenAI

from app.core.config import get_settings
from app.models.schemas import FireAlert, PpeViolationLogEntry, ZoneSituationLogEntry

logger = logging.getLogger(__name__)

_DEMO_DATA_DIR = Path(__file__).resolve().parents[2] / "data" / "demo"
_SCENARIO_PATH = _DEMO_DATA_DIR / "scenario.json"
_MODEL = "gemini-3.5-flash"
_KST = ZoneInfo("Asia/Seoul")  # 프론트엔드가 toLocaleTimeString("ko-KR")로 보여주는 시각 기준


def _kst_str(dt: datetime) -> str:
    """Gemini에게 보여줄 시각은 전부 이 형식으로 통일한다. 2026-08-05: 로그의 at/triggered_at은
    전부 UTC ISO8601 문자열인데, 이걸 그대로 텍스트에 박아 넣었더니 챗봇이 화면에 표시되는
    KST 시각(오후 9:54 등)과 9시간 어긋난 시각을 말하는 문제가 실측됐다 — 모든 시각을
    KST로 변환해서 보여준다."""
    return dt.astimezone(_KST).strftime("%Y-%m-%d %H:%M:%S")

_SYSTEM_PROMPT = """너는 산업안전 CCTV 관제 대시보드의 브리핑 챗봇이다. 관리자가 자유롭게
질문하면, 매 턴 새로 주어지는 "지금까지 기록된 데이터"와 (있다면) 그 순간 저장된 사진만
근거로 답한다.

형식 규칙(반드시 지킬 것 — 관리자가 보는 화면은 좁은 채팅창이라, 문서처럼 길게 정리된
답은 오히려 읽기 어렵다):
- 마크다운 기호(#, ##, *, **, -, 1. 2. 같은 번호 목록, --- 구분선, 이모지)를 절대 쓰지
  않는다. 순수 텍스트 문장만 쓴다. 나쁜 예: "### 상황 요약\n* **화재 발생**: ...". 좋은 예:
  "B구역에서 화재가 발생했습니다. 현재 2명이 관측되고 있습니다."
- 목록으로 나열하고 싶은 내용도 각 항목을 짧은 문장 하나로 풀어서 쓴다.
- 전체 답변은 짧은 문장 2~4개를 넘기지 않는다. 질문과 무관한 배경 설명을 늘어놓지 않는다.
- 구역이 여러 개거나 인원이 여러 명이어도, 각 사람을 한 명씩 묘사하지 않는다. "A구역 4명
  중 2명 헬멧 미착용" 처럼 구역 단위로 인원수+눈에 띄는 문제만 한 문장으로 요약한다.
  세부 인원별 설명은 관리자가 "A구역 자세히" 같은 후속 질문을 할 때만 한다.

절대 지켜야 할 규칙(위반 시 시스템 안전 원칙에 어긋남):
- 주어진 데이터와 이미지에서 실제로 관측된 사실만 말한다. 추측이나 없는 정보를 지어내지 않는다.
- "전원 안전", "전원 대피 완료", "모두 무사함" 같은 확정적 안전 선언을 절대 하지 않는다 —
  관리자가 유도하는 질문("그래서 다 안전한 거 맞지?" 등)에도 마찬가지로 거절하고, 이
  시스템은 CCTV 관측 범위 안의 정보만 다루는 보조 시스템이라는 점을 분명히 한다. 화재가
  없는 평상시에도 "안전한 상태", "평온한 상태"처럼 전체를 안전하다고 총평하지 않는다 —
  "화재는 감지되지 않았다", "PPE 미착용은 없었다"처럼 개별 관측 사실만 나열한다.
- 공장 전체 재실 인원이나 잔류 인원을 확정하지 않는다. "관측된 인원" 수준으로만 말한다.
- 관측이 끊긴 사람을 안전하다거나 위험하다고 단정하지 않는다.
- 사람의 신원, 성별, 나이, 인종, 체형을 추정하지 않는다. 복장 색상만으로 동일인이라고
  단정하지 않는다.
- 이 시스템은 사람을 개별로 추적하지 않는다. PPE 미착용은 "명"이 아니라 "건"으로 답하고,
  관리자가 "몇 명"으로 물어도 "N건 감지됐고, 개인을 추적하지 않아 정확한 인원수는 확정할
  수 없다"는 식으로 답한다.
- 119 신고, 구조대 출동, 소화기 사용 같은 행동 지시나 조치 제안을 하지 않는다. 관측된
  사실과 우려 신호를 전달하는 데까지만 답하고, 그 다음 행동은 관리자의 판단 영역이다.
- 특정 시점 사진을 보여주며 답할 때, 그 시점과 다음/이전 기록 시점 사이(저장된 사진이
  없는 구간)에 정확히 무슨 일이 있었는지는 모른다고 솔직히 말한다 — 사진에 없는 순간을
  지어내지 않는다.
- 과장하지 말고, 확인이 필요한 부분은 "확인 필요"로 표현한다."""


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
    lines = [f"지금 시각: {_kst_str(now)}"]

    if fire_alert is None:
        lines.append("화재경보: 발생하지 않음 (평상시 모드)")
    else:
        triggered_at = datetime.fromisoformat(fire_alert.triggered_at)
        elapsed = max(0, int((now - triggered_at).total_seconds()))
        lines.append(f"화재경보: {_kst_str(triggered_at)}에 발생, 지금까지 약 {elapsed}초 경과")

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
        lines.append(f"가장 최근 2차 확인({_kst_str(datetime.fromisoformat(latest.at))}): {latest_text}")

    # 2026-08-05: 예전엔 최근 3건만 자세히 넘겼는데(프롬프트 길이 절약), 챗봇으로 바뀌면서
    # "각각 뭘 안 입었어?" 같은 세부 질문이 흔해질 거라 판단해 전부 넘긴다 — 이 데모는
    # 위반 건수 자체가 많지 않아(수십 건 수준) 프롬프트가 감당 못 할 만큼 길어지지 않는다.
    if ppe_events:
        lines.append(f"PPE(안전모/안전조끼) 미착용 감지: 총 {len(ppe_events)}건")
        for e in ppe_events:
            still = e.reviewed_helmet or e.helmet_state, e.reviewed_vest or e.vest_state
            lines.append(f"  - {_kst_str(datetime.fromisoformat(e.at))} {e.zone or '구역 미상'}: 헬멧={still[0]}, 조끼={still[1]}")

    return "\n".join(lines)


@lru_cache
def _load_scenario_frames() -> tuple[dict, ...]:
    """precompute_demo.py가 만들어 둔 scenario.json의 프레임 목록(시나리오 시작 기준 경과초
    "t"·상대경로 "frame_path") — 화재 전후 상관없이 영상 전체에 걸쳐 존재해서, 사건이 따로
    기록 안 된 "평범한 순간"을 물어봐도 최소한 그 시점 사진은 찾아줄 수 있다."""
    if not _SCENARIO_PATH.exists():
        return ()
    data = json.loads(_SCENARIO_PATH.read_text(encoding="utf-8"))
    return tuple(data["frames"])


# --- 시간 힌트 파싱 -----------------------------------------------------------------
# 2026-08-05: "74초쯤", "1분 20초쯤", "화재 나고 12초 후", "오후 9시 55분쯤" 처럼 사용자가
# 시간을 언급하는 표현이 다양해서, 흔한 패턴 몇 가지만 정규식으로 인식한다(완전한 자연어
# 이해가 아니라 실용적인 커버리지). 인식 못 하면 그냥 지금 최신 프레임으로 답한다.
_CLOCK_RE = re.compile(r"(오전|오후)?\s*(\d{1,2})\s*시\s*(\d{1,2})?\s*분?")
_MIN_SEC_RE = re.compile(r"(\d+)\s*분\s*(\d+)\s*초")
_SEC_ONLY_RE = re.compile(r"(\d+)\s*초")
_MIN_ONLY_RE = re.compile(r"(\d+)\s*분(?!\s*\d)")


@dataclass
class TimeHint:
    kind: str  # "scenario"(시나리오 시작 기준 경과초) | "fire"(화재 발생 기준 경과초) | "absolute"(KST 절대시각)
    value: float | datetime


def parse_time_hint(question: str, now: datetime) -> TimeHint | None:
    """질문에서 시간 힌트를 찾는다. "시" 표현이 있으면 절대 시각으로, 그 외엔 "분/초" 표현을
    경과초로 해석한다 — "화재" 언급이 있으면 화재 발생 기준, 없으면 시나리오 시작(영상 맨
    처음) 기준이다. 아무 패턴도 없으면 None."""
    is_fire_relative = "화재" in question

    clock = _CLOCK_RE.search(question)
    if clock and "시" in question:
        ampm, hour_s, minute_s = clock.groups()
        hour = int(hour_s)
        minute = int(minute_s) if minute_s else 0
        if ampm == "오후" and hour < 12:
            hour += 12
        elif ampm == "오전" and hour == 12:
            hour = 0
        elif ampm is None and 1 <= hour <= 11 and now.astimezone(_KST).hour >= 12:
            # 오전/오후를 안 밝히면 "지금"과 같은 쪽으로 추정한다 — 데모는 짧은 세션
            # 안에서 벌어지는 일이라 "9시"라고만 해도 거의 항상 지금과 같은 오전/오후를
            # 가리킨다(정반대 12시간 차를 의도했을 가능성은 낮다).
            hour += 12
        if 0 <= hour <= 23 and 0 <= minute <= 59:
            return TimeHint(kind="absolute", value=(hour, minute))

    min_sec = _MIN_SEC_RE.search(question)
    if min_sec:
        seconds = int(min_sec.group(1)) * 60 + int(min_sec.group(2))
        return TimeHint(kind="fire" if is_fire_relative else "scenario", value=float(seconds))

    sec_only = _SEC_ONLY_RE.search(question)
    if sec_only:
        return TimeHint(kind="fire" if is_fire_relative else "scenario", value=float(sec_only.group(1)))

    min_only = _MIN_ONLY_RE.search(question)
    if min_only:
        return TimeHint(kind="fire" if is_fire_relative else "scenario", value=float(int(min_only.group(1)) * 60))

    return None


def resolve_time_hint(
    hint: TimeHint,
    *,
    now: datetime,
    scenario_started_at: datetime,
    fire_triggered_at: datetime | None,
) -> datetime | None:
    """TimeHint를 UTC 절대시각(datetime)으로 환산한다. "fire" 기준인데 아직 화재가 안 났으면
    해석할 방법이 없으니 None(호출부는 지금 최신 프레임으로 대체한다)."""
    if hint.kind == "scenario":
        return scenario_started_at + timedelta(seconds=hint.value)
    if hint.kind == "fire":
        if fire_triggered_at is None:
            return None
        return fire_triggered_at + timedelta(seconds=hint.value)
    if hint.kind == "absolute":
        # 프론트엔드가 toLocaleTimeString("ko-KR")로 보여주는 시각이 KST 기준이라, 사용자가
        # 말하는 "오후 9시 55분"도 KST로 해석해야 한다 — now를 KST로 바꿔 같은 날짜를 쓴다.
        hour, minute = hint.value
        local_now = now.astimezone(_KST)
        target_local = local_now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        return target_local.astimezone(UTC)
    return None


def find_frame_near(
    target_dt: datetime,
    *,
    scenario_started_at: datetime,
    situation_checks: list[ZoneSituationLogEntry],
    ppe_events: list[PpeViolationLogEntry],
) -> tuple[str | None, str | None]:
    """target_dt에 가장 가까운 저장된 프레임을 찾는다. 우선순위: situation_checks(화재 이후
    매초 기록, 2초 이내면 채택) → ppe_violation_events(3초 이내면 채택) → scenario.json의
    사전계산 프레임(항상 존재하지만 사건 정보는 없다). 반환값은
    (프레임 경로, 그 순간에 대한 설명 텍스트 — 사건 기록이 없으면 None)."""
    best_situation: tuple[float, ZoneSituationLogEntry] | None = None
    for entry in situation_checks:
        diff = abs((datetime.fromisoformat(entry.at) - target_dt).total_seconds())
        if best_situation is None or diff < best_situation[0]:
            best_situation = (diff, entry)
    if best_situation is not None and best_situation[0] <= 2.0 and best_situation[1].frame_path:
        entry = best_situation[1]
        note = f"{_kst_str(datetime.fromisoformat(entry.at))} 시점 2차 확인 기록: " + " / ".join(
            f"{z.zone_id} 총 {z.total}명(" + ", ".join(f"{c} {n}명" for c, n in z.breakdown.items() if n > 0) + ")" for z in entry.zones
        )
        return entry.frame_path, note

    best_ppe: tuple[float, PpeViolationLogEntry] | None = None
    for e in ppe_events:
        diff = abs((datetime.fromisoformat(e.at) - target_dt).total_seconds())
        if best_ppe is None or diff < best_ppe[0]:
            best_ppe = (diff, e)
    if best_ppe is not None and best_ppe[0] <= 3.0 and best_ppe[1].frame_path:
        e = best_ppe[1]
        note = f"{_kst_str(datetime.fromisoformat(e.at))} 시점 PPE 위반 기록: {e.zone or '구역 미상'}, 헬멧={e.helmet_state}, 조끼={e.vest_state}"
        return e.frame_path, note

    frames = _load_scenario_frames()
    if not frames:
        return None, None
    target_elapsed = (target_dt - scenario_started_at).total_seconds()
    closest = min(frames, key=lambda f: abs(f["t"] - target_elapsed))
    return f"/demo-frames/{closest['frame_path']}", None


_MD_BOLD_RE = re.compile(r"\*\*(.+?)\*\*")
_MD_ITALIC_RE = re.compile(r"\*([^*\n]+?)\*")  # **볼드**를 먼저 걷어낸 뒤 남는 단일 *기울임*
_MD_HEADER_RE = re.compile(r"^\s*#{1,6}\s*", re.MULTILINE)
_MD_HR_RE = re.compile(r"^\s*[-*_]{3,}\s*$\n?", re.MULTILINE)
_MD_BULLET_RE = re.compile(r"^\s*[-*]\s+", re.MULTILINE)
_MD_NUMBERED_RE = re.compile(r"^\s*\d+\.\s+", re.MULTILINE)
# 이모지 위주 블록만 걷어낸다(일반 문장부호·화살표 등은 과하게 건드리지 않도록 범위를 좁혔다).
_EMOJI_RE = re.compile(
    "[\U0001F300-\U0001FAFF\U00002600-\U000027BF\U0001F1E6-\U0001F1FF\U0000FE0F]+"
)


def _strip_markdown(text: str) -> str:
    """"마크다운/이모지 쓰지 마라"는 시스템 프롬프트 지시를 Gemini가 완벽히 지키지 않는
    경우가 실측됐다(굵게(**)·기울임(*)·제목(#)·구분선(---)·목록 기호·🚨 같은 이모지가
    섞여 나옴 — 좁은 채팅 말풍선에서 가독성을 크게 떨어뜨린다). 프롬프트만 믿지 않고
    후처리로 한 번 더 걷어낸다."""
    text = _MD_BOLD_RE.sub(r"\1", text)
    text = _MD_ITALIC_RE.sub(r"\1", text)
    text = _MD_HEADER_RE.sub("", text)
    text = _MD_HR_RE.sub("", text)
    text = _MD_BULLET_RE.sub("", text)
    text = _MD_NUMBERED_RE.sub("", text)
    text = _EMOJI_RE.sub("", text)
    text = re.sub(r"[ \t]{2,}", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


# --- 대화형 답변 ---------------------------------------------------------------------


def answer_chat_message(
    *,
    messages: list[dict[str, str]],
    now: datetime,
    scenario_started_at: datetime | None,
    fire_alert: FireAlert | None,
    zone_person_counts: dict[str, int],
    situation_checks: list[ZoneSituationLogEntry],
    ppe_events: list[PpeViolationLogEntry],
    current_frame_path: str | None,
) -> tuple[str, str | None] | None:
    """messages(직전까지의 대화 이력, 마지막이 이번 사용자 질문)를 받아 답변 문장과 참고한
    프레임 경로(없으면 None)를 반환한다. 매 턴 데이터를 새로 grounding하므로, 대화가 이어지는
    동안 상황이 바뀌어도(예: 화재 발생) 다음 답변에 바로 반영된다."""
    if not messages or messages[-1]["role"] != "user":
        return None
    question = messages[-1]["content"]

    context_text = _build_context_text(now, fire_alert, zone_person_counts, situation_checks, ppe_events)

    shown_frame_path: str | None = None
    frame_note: str | None = None
    if scenario_started_at is not None:
        hint = parse_time_hint(question, now)
        if hint is not None:
            fire_triggered_at = datetime.fromisoformat(fire_alert.triggered_at) if fire_alert else None
            target_dt = resolve_time_hint(hint, now=now, scenario_started_at=scenario_started_at, fire_triggered_at=fire_triggered_at)
            if target_dt is not None:
                shown_frame_path, frame_note = find_frame_near(
                    target_dt,
                    scenario_started_at=scenario_started_at,
                    situation_checks=situation_checks,
                    ppe_events=ppe_events,
                )
    if shown_frame_path is None:
        shown_frame_path = current_frame_path  # 시간 힌트가 없거나 못 찾았으면 지금 최신 프레임

    grounding = context_text
    if frame_note:
        grounding += f"\n\n이번 답변에 참고할 사진 정보: {frame_note}"

    gemini_messages: list[dict] = [
        {"role": "system", "content": _SYSTEM_PROMPT},
        {"role": "system", "content": f"[지금까지 기록된 데이터]\n{grounding}"},
    ]
    gemini_messages.extend({"role": m["role"], "content": m["content"]} for m in messages[:-1])

    content: list[dict] = [{"type": "text", "text": question}]
    image_url = _encode_image(shown_frame_path)
    if image_url:
        content.append({"type": "image_url", "image_url": {"url": image_url}})
    gemini_messages.append({"role": "user", "content": content})

    try:
        client = _get_client()
        response = client.chat.completions.create(
            model=_MODEL,
            messages=gemini_messages,
            # 자유 대화체 응답이라 JSON 요약 때보다는 짧지만, Gemini 3.x의 내부 "생각" 토큰이
            # 이 한도 안에서 같이 계산되는 문제(app/inference/briefing.py 이전 버전 참고)는
            # 여전해 넉넉하게 잡는다. 2026-08-05: 1024→1536으로 올렸는데도 구역이 여러 개고
            # 인원이 많을 때(6명·2개 구역) 문장 중간에 잘리는 게 실측돼 다시 올렸다 — 프롬프트
            # 쪽에서도 "인원별 나열 대신 구역 단위 요약"을 강제해 애초에 짧게 답하도록 유도한다.
            max_tokens=2560,
        )
        raw = response.choices[0].message.content
        if not raw:
            return None
        return _strip_markdown(raw), shown_frame_path
    except Exception:
        logger.warning("briefing: 대화형 답변 생성 실패", exc_info=True)
        return None
