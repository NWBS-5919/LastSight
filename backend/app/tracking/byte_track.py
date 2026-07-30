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

    def _greedy_match(self, track_ids: list[str], detections: list[Detection]) -> tuple[list[tuple[str, int]], list[str], list[int]]:
        """트랙의 예측 위치와 탐지들 사이 IoU 기준 그리디 매칭.

        헝가리안 알고리즘 대신 그리디를 쓰는 이유: 한 프레임에 사람이 소수(수 명~수십 명)라
        전역 최적화 없이도 충분하고, scipy 등 추가 의존성 없이 순수 파이썬으로 구현 가능.

        후보로 남는 기준(threshold)은 IoU 하나뿐이지만, 그중 어느 후보를 먼저 확정할지
        정하는 순위는 IoU와 박스 크기 유사도를 함께 본다 — 두 사람이 스쳐 지나가며
        겹칠 때, 위치만으로는 헷갈려도 카메라 거리가 다르면 박스 크기가 달라서
        잘못된 매칭을 먼저 확정하는 걸 줄여준다(메인 기준은 여전히 위치).
        """
        candidates = []
        for tid in track_ids:
            predicted = self._tracks[tid].predict()
            for di, det in enumerate(detections):
                iou = _iou(predicted, det.bbox_xyxy)
                if iou >= self.iou_threshold:
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

    def update(self, detections: list[Detection]) -> list[TrackedObject]:
        """한 프레임의 person Detection들에 track_id를 부여/유지해 반환. 프레임 순서대로 호출할 것."""
        high = [d for d in detections if d.confidence >= self.high_conf_threshold]
        low = [d for d in detections if d.confidence < self.high_conf_threshold]

        all_track_ids = list(self._tracks.keys())

        matches1, unmatched_tracks1, unmatched_high = self._greedy_match(all_track_ids, high)
        for tid, di in matches1:
            self._tracks[tid].update_with(high[di].bbox_xyxy)

        matches2, unmatched_tracks2, _unmatched_low = self._greedy_match(unmatched_tracks1, low)
        for tid, di in matches2:
            self._tracks[tid].update_with(low[di].bbox_xyxy)

        for tid in unmatched_tracks2:
            self._tracks[tid].time_since_update += 1

        expired = [tid for tid, t in self._tracks.items() if t.time_since_update > self.max_lost_frames]
        for tid in expired:
            del self._tracks[tid]

        results: list[TrackedObject] = [TrackedObject(track_id=tid, detection=high[di]) for tid, di in matches1]
        results += [TrackedObject(track_id=tid, detection=low[di]) for tid, di in matches2]

        for di in unmatched_high:
            new_id = self._new_id()
            self._tracks[new_id] = _Track(track_id=new_id, bbox=high[di].bbox_xyxy)
            results.append(TrackedObject(track_id=new_id, detection=high[di]))

        return results
