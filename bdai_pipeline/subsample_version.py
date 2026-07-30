"""이미 업로드·라벨링된 버전에서 부분집합만 골라 새 스냅샷(버전) 생성.

AI Hub 176 화재씬 데이터가 영상 8개에서 뽑은 연속 프레임(13,159장)이라 프레임 간
중복이 심하다는 게 확인됐다(development_log.md 15번 참고). 재업로드·재라벨링 없이
`versions.create(selection={"asset_ids": [...]})`로 클립별 stride 샘플링한 부분집합만
새 버전으로 얼린다.

사용 예:
    python -m bdai_pipeline.subsample_version \
        --project-id abad271f-68e8-4f63-a37a-f53e04b532d6 \
        --source-version-id 3ff88094-de46-4472-9668-f2038a073059 \
        --name fire-smoke-v3-subsampled --stride 8
"""

import argparse
import re
from collections import defaultdict

from bdai_pipeline.client import get_client

# AI Hub 176 파일명: <클립ID>MF<프레임번호>.jpg (예: S3-N1452MF01832.jpg)
_AIHUB_PATTERN = re.compile(r"^(?P<clip>.+)MF(?P<frame>\d+)\.jpg$", re.IGNORECASE)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-id", required=True)
    parser.add_argument("--source-version-id", required=True)
    parser.add_argument("--name", required=True)
    parser.add_argument("--stride", type=int, required=True, help="클립 내 프레임 샘플링 간격 (8 = 8장마다 1장)")
    args = parser.parse_args()

    client = get_client()

    clips: dict[str, list[tuple[int, str]]] = defaultdict(list)  # clip -> [(frame_num, asset_id)]
    baseline_ids: list[str] = []

    print("버전의 전체 프리즌 에셋 목록 조회 중...")
    total = 0
    for asset in client.versions.list_assets(args.project_id, args.source_version_id):
        total += 1
        m = _AIHUB_PATTERN.match(asset.filename)
        if m:
            clips[m.group("clip")].append((int(m.group("frame")), str(asset.asset_id)))
        else:
            baseline_ids.append(str(asset.asset_id))

    print(f"총 {total}장 확인: AI Hub 176 클립 {len(clips)}개, 그 외(baseline) {len(baseline_ids)}장")

    selected_ids: list[str] = list(baseline_ids)
    for clip, frames in sorted(clips.items()):
        frames.sort(key=lambda t: t[0])
        picked = frames[:: args.stride]
        selected_ids.extend(asset_id for _, asset_id in picked)
        print(f"  {clip}: {len(frames)}장 → {len(picked)}장 (stride={args.stride})")

    print(f"최종 선택: {len(selected_ids)}장 (baseline {len(baseline_ids)}장 + AI Hub 176 서브샘플)")

    version = client.versions.create(
        args.project_id, name=args.name, selection={"asset_ids": selected_ids}
    )
    print(f"버전 생성 시작: {version.name} ({version.id}) status={version.status}")
    version = client.versions.wait_ready(args.project_id, version.id)
    print(f"버전 준비 완료: status={version.status}, 에셋 {version.frozen_asset_count}개, 클래스 {version.frozen_class_count}개")


if __name__ == "__main__":
    main()
