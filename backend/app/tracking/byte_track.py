"""다중 객체 추적 — ByteTrack 핵심 아이디어를 경량화한 자체 구현(순수 파이썬, 외부 추적 라이브러리 없음).

app.inference.detector 의 프레임별 person Detection을 입력받아
영상 전체에서 유지되는 임시 track_id를 부여한다. 카메라 1대(영상 1개)당
ByteTracker 인스턴스 하나를 만들고, 프레임 순서대로 update()를 호출한다.

ByteTrack 핵심 아이디어:
1) 신뢰도 높은 탐지부터 기존 트랙(직전 위치로 예측한 박스)과 IoU로 매칭
2) 아직 안 매칭된 트랙은 신뢰도 낮은 탐지와 한 번 더 매칭 시도
   (가려짐 등으로 확신이 떨어진 사람도 새 사람으로 잘못 만들지 않고 같은 ID로 살려서 씀)
3) 그래도 안 매칭된 트랙은 max_lost_frames 프레임까지는 그대로 유지(잠깐 가려져도 ID 유지),
   넘으면 제거
4) 안 매칭된 "고신뢰" 탐지만 새 트랙(새 ID) 생성 — 저신뢰 미매칭 탐지로는 새 ID를 만들지 않아
   오탐이 새 사람으로 둔갑하는 걸 방지

주의(CLAUDE.md 2번): 복장 색상 등 외형만으로 서로 다른 두 track_id를 같은 사람으로
병합하는 로직을 넣지 말 것. ID 유지/전환은 이 파일의 위치 기반(IoU) 판단에만 맡긴다.
"""

import math
from dataclasses import dataclass, field

from app.inference.detector import Detection

BBox = tuple[float, float, float, float]  # x1, y1, x2, y2


def _iou(a: BBox, b: BBox) -> float:
    ax1, ay1, ax2, ay2 = a
    bx1, by1, bx2, by2 = b
    ix1, iy1 = max(ax1, bx1), max(ay1, by1)
    ix2, iy2 = min(ax2, bx2), min(ay2, by2)
    inter = max(0.0, ix2 - ix1) * max(0.0, iy2 - iy1)
    area_a = max(0.0, ax2 - ax1) * max(0.0, ay2 - ay1)
    area_b = max(0.0, bx2 - bx1) * max(0.0, by2 - by1)
    union = area_a + area_b - inter
    return inter / union if union > 0 else 0.0


def _center(b: BBox) -> tuple[float, float]:
    return ((b[0] + b[2]) / 2, (b[1] + b[3]) / 2)


def _size_similarity(a: BBox, b: BBox) -> float:
    """두 박스의 가로·세로 크기가 얼마나 비슷한지 (0~1, 1이면 동일 크기).

    카메라와의 거리가 다른 두 사람은 박스 크기도 다르게 찍히므로, 겹침(IoU)만으로
    헷갈리는 순간(두 사람이 스치듯 겹쳐 지나가는 등)에 크기 정보로 보조 판단한다.
    얼굴·복장 색상 등 신원과 관련된 정보는 전혀 쓰지 않는다(CLAUDE.md 2번 절대 원칙 —
    "동일 복장 = 동일인이 아니다") — 순전히 박스의 기하학적 크기만 비교한다.
    """
    aw, ah = a[2] - a[0], a[3] - a[1]
    bw, bh = b[2] - b[0], b[3] - b[1]
    if aw <= 0 or ah <= 0 or bw <= 0 or bh <= 0:
        return 0.0
    width_ratio = min(aw, bw) / max(aw, bw)
    height_ratio = min(ah, bh) / max(ah, bh)
    return width_ratio * height_ratio


@dataclass
class _Track:
    track_id: str
    bbox: BBox
    velocity: tuple[float, float] = (0.0, 0.0)
    time_since_update: int = 0

    def predict(self) -> BBox:
        """등속 이동 가정으로 다음 프레임 위치를 단순 외삽(칼만 필터 없는 경량 버전)."""
        vx, vy = self.velocity
        x1, y1, x2, y2 = self.bbox
        return (x1 + vx, y1 + vy, x2 + vx, y2 + vy)

    def update_with(self, bbox: BBox) -> None:
        old_cx, old_cy = _center(self.bbox)
        new_cx, new_cy = _center(bbox)
        self.velocity = (new_cx - old_cx, new_cy - old_cy)
        self.bbox = bbox
        self.time_since_update = 0


@dataclass
class TrackedObject:
    track_id: str
    detection: Detection


_STALE_IOU_CAP = 0.95  # 오래 놓친 트랙이 재매칭되려면 요구되는 IoU의 상한(사실상 재사용 불가 수준)


@dataclass
class ByteTracker:
    iou_threshold: float = 0.3
    high_conf_threshold: float = 0.5
    max_lost_frames: int = 30
    # 매칭 순위를 매길 때 크기 유사도를 얼마나 반영할지 (0=완전히 IoU만, 1=완전히 크기만).
    # 메인 기준은 항상 위치(IoU)이고, 크기 유사도는 어느 후보를 먼저 확정할지 정하는 보조 기준일 뿐이다.
    size_similarity_weight: float = 0.2

    _tracks: dict[str, _Track] = field(default_factory=dict, init=False, repr=False)
    _next_id: int = field(default=1, init=False, repr=False)

    def _new_id(self) -> str:
        track_id = f"T{self._next_id:04d}"
        self._next_id += 1
        return track_id

    def _required_iou(self, track: _Track) -> float:
        """트랙이 놓친 지 오래될수록 재매칭에 필요한 IoU를 더 엄격하게 요구한다.

        수정 전에는 놓친 지 1프레임이든 max_lost_frames 직전이든 항상 같은 느슨한
        기준(iou_threshold)을 썼다 — 그래서 화면이 완전히 비었다가(전원 화면 이탈)
        한참 뒤 전혀 다른 새 사람이 우연히 비슷한 위치에 나타나면, 죽지 않고 남아있던
        옛 트랙(유령 트랙)이 그 새 사람에게 잘못 재부착되는 버그가 있었다
        (development_log.md 20번 참고, 재현 테스트는 test_byte_track.py 참고).

        놓친 지 얼마 안 된 트랙(짧은 가려짐)은 기존처럼 관대하게 허용하되, max_lost_frames에
        가까워질수록 요구 IoU를 제곱으로 급격히 끌어올려 사실상 "완전히 같은 자리에 그대로
        있는 경우"만 재매칭되게 한다 — 우연히 근처에 나타난 다른 사람은 걸러지고, 짧게
        가려졌다 돌아오는 정상 케이스는 그대로 통과한다."""
        if self.max_lost_frames <= 0:
            return self.iou_threshold
        ratio = min(track.time_since_update / self.max_lost_frames, 1.0)
        return self.iou_threshold + (ratio**2) * (_STALE_IOU_CAP - self.iou_threshold)

    def _greedy_match(self, track_ids: list[str], detections: list[Detection]) -> tuple[list[tuple[str, int]], list[str], list[int]]:
        """트랙의 예측 위치와 탐지들 사이 IoU 기준 그리디 매칭.

        헝가리안 알고리즘 대신 그리디를 쓰는 이유: 한 프레임에 사람이 소수(수 명~수십 명)라
        전역 최적화 없이도 충분하고, scipy 등 추가 의존성 없이 순수 파이썬으로 구현 가능.

        후보로 남는 기준(threshold)은 IoU 하나뿐이지만, 그중 어느 후보를 먼저 확정할지
        정하는 순위는 IoU와 박스 크기 유사도를 함께 본다 — 두 사람이 스쳐 지나가며
        겹칠 때, 위치만으로는 헷갈려도 카메라 거리가 다르면 박스 크기가 달라서
        잘못된 매칭을 먼저 확정하는 걸 줄여준다(메인 기준은 여전히 위치). 필요 IoU 자체도
        트랙별로 다르다(_required_iou) — 오래 놓친 트랙일수록 더 엄격하게 본다.
        """
        candidates = []
        for tid in track_ids:
            track = self._tracks[tid]
            predicted = track.predict()
            required = self._required_iou(track)
            for di, det in enumerate(detections):
                iou = _iou(predicted, det.bbox_xyxy)
                if iou >= required:
                    size_sim = _size_similarity(predicted, det.bbox_xyxy)
                    score = (1 - self.size_similarity_weight) * iou + self.size_similarity_weight * size_sim
                    candidates.append((score, tid, di))
        candidates.sort(key=lambda c: c[0], reverse=True)

        matched_tracks: set[str] = set()
        matched_dets: set[int] = set()
        matches: list[tuple[str, int]] = []
        for _iou_val, tid, di in candidates:
            if tid in matched_tracks or di in matched_dets:
                continue
            matches.append((tid, di))
            matched_tracks.add(tid)
            matched_dets.add(di)

        unmatched_tracks = [t for t in track_ids if t not in matched_tracks]
        unmatched_dets = [i for i in range(len(detections)) if i not in matched_dets]
        return matches, unmatched_tracks, unmatched_dets

    def _required_radius(self, track: _Track) -> float:
        """거리 기반 폴백 매칭(_distance_fallback_match)에서 쓰는 반경(px).

        2026-08-03 실측: 처음엔 _required_iou처럼 time_since_update에 비례해 반경을
        선형으로 줄이기만 했는데, 유령 트랙 재부착 방지 테스트(놓친 지 8/10프레임, 겨우
        2px 떨어진 "다른 사람")가 깨졌다 — 8/10 지점에서도 반경이 12px나 남아있어서
        재부착됐다. 이 폴백의 목적은 "뛰는 사람처럼 바로 직전 프레임까지는 잘 이어지다가
        이번 프레임 하나에서만 IoU가 어긋난 경우"를 구제하는 것이지, 여러 프레임째 놓친
        트랙을 되살리는 게 아니다 — 그건 여전히 _required_iou의 몫이다. 그래서 아예
        time_since_update가 0(=바로 직전 프레임까지 정상 매칭됨)일 때만 반경을 주고,
        한 번이라도 놓친 트랙은 0을 반환해 이 폴백 대상에서 완전히 제외한다."""
        if track.time_since_update > 0:
            return 0.0
        return max(60.0, (track.bbox[2] - track.bbox[0]) * 1.5)

    def _distance_fallback_match(
        self, track_ids: list[str], detections: list[Detection]
    ) -> tuple[list[tuple[str, int]], list[str], list[int]]:
        """IoU 매칭에 실패한 트랙을 위한 2차 매칭 — 겹침 대신 중심점 거리로 이어붙인다.

        2026-08-03: 화재 이후 사람이 뛰어서 대피하면 1프레임(샘플 간격) 사이 이동 거리가
        커서 예측 박스와 실제 박스가 거의 안 겹친다(IoU≈0) — 그러면 _greedy_match가 실패해
        같은 사람인데도 매번 새 track_id가 발급됐다(실측: idx=61~87 26프레임에 T0001~T0020,
        20개 ID). 얼굴·복장 등 외형은 전혀 안 쓰고(CLAUDE.md 2번 원칙), 순수하게 "이 사람이
        직전에 있던 자리에서 그럴듯한 거리만큼만 움직였는가"만 기하학적으로 판단한다 —
        이 세션에서 PPE 판정 스트림 매칭에 쓴 것과 같은 접근이다. 예측 위치가 아니라
        마지막으로 실제 관측된 위치(track.bbox) 기준으로 재는데, 급격한 방향 전환·가속에서는
        등속 예측보다 마지막 실측 위치가 더 안정적인 기준이기 때문이다."""
        candidates = []
        for tid in track_ids:
            track = self._tracks[tid]
            radius = self._required_radius(track)
            if radius <= 0:
                continue
            last_center = _center(track.bbox)
            for di, det in enumerate(detections):
                dist = math.dist(last_center, _center(det.bbox_xyxy))
                if dist <= radius:
                    score = 1.0 - dist / radius
                    candidates.append((score, tid, di))
        candidates.sort(key=lambda c: c[0], reverse=True)

        matched_tracks: set[str] = set()
        matched_dets: set[int] = set()
        matches: list[tuple[str, int]] = []
        for _score, tid, di in candidates:
            if tid in matched_tracks or di in matched_dets:
                continue
            matches.append((tid, di))
            matched_tracks.add(tid)
            matched_dets.add(di)

        unmatched_tracks = [t for t in track_ids if t not in matched_tracks]
        unmatched_dets = [i for i in range(len(detections)) if i not in matched_dets]
        return matches, unmatched_tracks, unmatched_dets

    def update(self, detections: list[Detection]) -> list[TrackedObject]:
        """한 프레임의 person Detection들에 track_id를 부여/유지해 반환. 프레임 순서대로 호출할 것."""
        high = [d for d in detections if d.confidence >= self.high_conf_threshold]
        low = [d for d in detections if d.confidence < self.high_conf_threshold]

        all_track_ids = list(self._tracks.keys())

        matches1, unmatched_tracks1, unmatched_high = self._greedy_match(all_track_ids, high)
        for tid, di in matches1:
            self._tracks[tid].update_with(high[di].bbox_xyxy)

        matches2, unmatched_tracks2, unmatched_low = self._greedy_match(unmatched_tracks1, low)
        for tid, di in matches2:
            self._tracks[tid].update_with(low[di].bbox_xyxy)

        # IoU로 못 이은 트랙에 한해, 남은 탐지(고/저신뢰 모두) 중 거리로 이어붙일 수 있는지
        # 마지막으로 시도한다 — 뛰는 사람처럼 겹침이 거의 없는 경우를 구제한다.
        remaining = [("high", i, high[i]) for i in unmatched_high] + [("low", i, low[i]) for i in unmatched_low]
        matches3, unmatched_tracks3, unmatched_remaining_idx = self._distance_fallback_match(
            unmatched_tracks2, [d for _src, _i, d in remaining]
        )
        for tid, ri in matches3:
            self._tracks[tid].update_with(remaining[ri][2].bbox_xyxy)

        for tid in unmatched_tracks3:
            self._tracks[tid].time_since_update += 1

        expired = [tid for tid, t in self._tracks.items() if t.time_since_update > self.max_lost_frames]
        for tid in expired:
            del self._tracks[tid]

        results: list[TrackedObject] = [TrackedObject(track_id=tid, detection=high[di]) for tid, di in matches1]
        results += [TrackedObject(track_id=tid, detection=low[di]) for tid, di in matches2]
        results += [TrackedObject(track_id=tid, detection=remaining[ri][2]) for tid, ri in matches3]

        # 거리 폴백까지 실패한 고신뢰 탐지만 새 트랙 후보 — 저신뢰 미매칭 탐지로는 여전히
        # 새 ID를 만들지 않는다(오탐이 새 사람으로 둔갑하는 걸 방지, 기존 원칙 유지).
        unmatched_high = [remaining[ri][1] for ri in unmatched_remaining_idx if remaining[ri][0] == "high"]

        for di in unmatched_high:
            new_id = self._new_id()
            self._tracks[new_id] = _Track(track_id=new_id, bbox=high[di].bbox_xyxy)
            results.append(TrackedObject(track_id=new_id, detection=high[di]))

        return results
