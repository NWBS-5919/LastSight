"""precompute_demo_dense_head.py가 precompute_demo_dense_tail.py의 프레임 파일을 이름
충돌로 덮어쓴 버그를 복구한다 (development_log.md 참고, "구조카드 초반 프레임이 안 맞는다"
사용자 리포트로 발견).

문제: dense_head가 자기 프레임을 0000.jpg~0115.jpg로 저장하면서, dense_tail이 이미
0058.jpg~0115.jpg로 저장해둔 화재 직후(t=58.0~72.25s) 프레임을 그대로 덮어썼다. 두
스크립트 모두 로컬 idx(0부터 다시 시작)로 파일명을 정했기 때문 — t 범위가 안 겹치는데도
파일명 범위가 겹친 것. detection 데이터(JSON)는 멀쩡하고 그림 파일만 잘못됐으므로, ZERO를
다시 호출할 필요 없이 원본 영상에서 해당 t의 프레임만 다시 뽑으면 된다.

같은 버그가 재발하지 않도록 두 스크립트의 프레임 파일명도 t 기반으로 바꿔서(head는
t<58, tail은 t>=58 — 범위가 안 겹치므로 파일명도 절대 안 겹침) 어느 순서로 다시 실행해도
안전하게 만든다.
"""

import json
from pathlib import Path

import cv2

VIDEO_PATH = Path(__file__).resolve().parents[2] / "LastSight_Demo.mp4"
SCENARIO_PATH = Path(__file__).resolve().parents[1] / "data" / "demo" / "scenario.json"
FRAMES_DIR = Path(__file__).resolve().parents[1] / "data" / "demo" / "frames"


def main() -> None:
    scenario = json.loads(SCENARIO_PATH.read_text(encoding="utf-8"))
    frames = scenario["frames"]

    by_path: dict[str, list[dict]] = {}
    for f in frames:
        by_path.setdefault(f["frame_path"], []).append(f)
    collisions = {k: v for k, v in by_path.items() if len(v) > 1}
    print(f"충돌 그룹 {len(collisions)}개 발견")
    if not collisions:
        print("고칠 게 없습니다.")
        return

    cap = cv2.VideoCapture(str(VIDEO_PATH))
    if not cap.isOpened():
        raise SystemExit(f"영상을 열 수 없습니다: {VIDEO_PATH}")
    fps = cap.get(cv2.CAP_PROP_FPS)
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

    fixed = 0
    for path, entries in collisions.items():
        # 가장 이른 t를 가진 항목(파일명을 실제로 덮어쓴 쪽 = 지금 디스크에 있는 그림과
        # 일치)은 그대로 두고, 나머지(더 늦은 t, 즉 덮어써진 쪽)만 새 파일로 다시 뽑는다.
        entries_sorted = sorted(entries, key=lambda e: e["t"])
        for e in entries_sorted[1:]:
            t = e["t"]
            src_frame_idx = min(round(t * fps), total_frames - 1)
            cap.set(cv2.CAP_PROP_POS_FRAMES, src_frame_idx)
            ok, frame = cap.read()
            if not ok:
                print(f"  idx={e['idx']} t={t:.2f}s 읽기 실패 — 건너뜀")
                continue
            new_path = FRAMES_DIR / f"fix_{e['idx']:04d}.jpg"
            cv2.imwrite(str(new_path), frame)
            e["frame_path"] = f"frames/{new_path.name}"
            fixed += 1
            print(f"  복구: idx={e['idx']} t={t:.2f}s (원래 {path}) → {new_path.name}")

    cap.release()

    backup_path = SCENARIO_PATH.with_suffix(".json.bak3")
    backup_path.write_text(json.dumps(scenario, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"백업: {backup_path}")

    SCENARIO_PATH.write_text(json.dumps(scenario, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"완료: {fixed}개 프레임 복구 → {SCENARIO_PATH}")

    # 검증
    by_path2: dict[str, int] = {}
    for f in scenario["frames"]:
        by_path2[f["frame_path"]] = by_path2.get(f["frame_path"], 0) + 1
    remaining = {k: v for k, v in by_path2.items() if v > 1}
    print(f"남은 충돌: {len(remaining)}개")


if __name__ == "__main__":
    main()
