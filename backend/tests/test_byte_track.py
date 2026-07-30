from app.inference.detector import Detection
from app.models.schemas import ObjectClass
from app.tracking.byte_track import ByteTracker


def _det(x1, y1, x2, y2, confidence=0.9) -> Detection:
    return Detection(object_class=ObjectClass.PERSON, confidence=confidence, bbox_xyxy=(x1, y1, x2, y2))


def test_single_person_keeps_same_id_across_frames():
    tracker = ByteTracker()
    r1 = tracker.update([_det(0, 0, 10, 20)])
    r2 = tracker.update([_det(1, 1, 11, 21)])  # 살짝 이동
    r3 = tracker.update([_det(2, 2, 12, 22)])
    assert len(r1) == len(r2) == len(r3) == 1
    assert r1[0].track_id == r2[0].track_id == r3[0].track_id


def test_two_people_do_not_swap_ids():
    tracker = ByteTracker()
    r1 = tracker.update([_det(0, 0, 10, 20), _det(100, 0, 110, 20)])
    r2 = tracker.update([_det(2, 0, 12, 20), _det(102, 0, 112, 20)])

    left_id_1 = next(r.track_id for r in r1 if r.detection.bbox_xyxy[0] == 0)
    right_id_1 = next(r.track_id for r in r1 if r.detection.bbox_xyxy[0] == 100)
    left_id_2 = next(r.track_id for r in r2 if r.detection.bbox_xyxy[0] == 2)
    right_id_2 = next(r.track_id for r in r2 if r.detection.bbox_xyxy[0] == 102)

    assert left_id_1 == left_id_2
    assert right_id_1 == right_id_2
    assert left_id_1 != right_id_1


def test_brief_occlusion_keeps_same_id():
    tracker = ByteTracker(max_lost_frames=5)
    r1 = tracker.update([_det(0, 0, 10, 20)])
    tracker.update([])  # 1프레임 사라짐
    tracker.update([])  # 2프레임 사라짐
    r4 = tracker.update([_det(3, 0, 13, 20)])  # 다시 나타남 (조금 이동)
    assert r1[0].track_id == r4[0].track_id


def test_long_loss_expires_track_and_new_appearance_gets_new_id():
    tracker = ByteTracker(max_lost_frames=2)
    r1 = tracker.update([_det(0, 0, 10, 20)])
    for _ in range(5):
        tracker.update([])  # max_lost_frames보다 오래 사라짐 → 트랙 만료
    r_new = tracker.update([_det(0, 0, 10, 20)])
    assert r_new[0].track_id != r1[0].track_id


def test_low_confidence_detection_alone_does_not_spawn_new_track():
    tracker = ByteTracker(high_conf_threshold=0.5)
    results = tracker.update([_det(0, 0, 10, 20, confidence=0.2)])
    assert results == []


def test_low_confidence_detection_rescues_existing_track_through_occlusion():
    tracker = ByteTracker(high_conf_threshold=0.5)
    r1 = tracker.update([_det(0, 0, 10, 20, confidence=0.9)])
    # 가려져서 확신이 낮아진 채로 같은 위치 근처에 탐지됨
    r2 = tracker.update([_det(1, 1, 11, 21, confidence=0.3)])
    assert len(r2) == 1
    assert r2[0].track_id == r1[0].track_id


def test_size_similarity_breaks_ties_toward_matching_scale():
    """IoU만 보면 더 큰 박스(20x20)가 근소하게 앞서지만(0.25 > 0.22),
    원래 크기(10x10)와 비슷한 박스가 크기 유사도 가중치 덕분에 같은 트랙으로 이어져야 한다."""
    tracker = ByteTracker(iou_threshold=0.2)
    r1 = tracker.update([_det(0, 0, 10, 10)])
    original_id = r1[0].track_id

    r2 = tracker.update(
        [
            _det(4, 4, 14, 14),  # 크기(10x10)는 같지만 IoU는 더 낮음(≈0.22)
            _det(0, 0, 20, 20),  # 크기(20x20)는 다르지만 IoU는 더 높음(0.25)
        ]
    )

    matched = next(r for r in r2 if r.detection.bbox_xyxy == (4, 4, 14, 14))
    assert matched.track_id == original_id
    assert len(r2) == 2  # 크기가 다른 큰 박스는 원래 트랙에 붙지 않고 새 트랙으로 분리됨
