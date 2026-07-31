from app.rules.ppe_compliance import ComplianceState, evaluate_ppe_compliance

PERSON = (100.0, 100.0, 200.0, 300.0)


def test_head_and_matching_helmet_is_worn():
    head = (130.0, 100.0, 170.0, 140.0)
    helmet = (128.0, 95.0, 172.0, 138.0)  # head와 크게 겹침
    result = evaluate_ppe_compliance(PERSON, head_boxes=[head], helmet_boxes=[helmet])
    assert result.helmet == ComplianceState.WORN
    assert result.helmet_iou is not None and result.helmet_iou >= 0.5


def test_head_without_overlapping_helmet_is_not_worn():
    head = (130.0, 100.0, 170.0, 140.0)
    # 헬멧 박스가 사람 안에는 있지만 머리와는 거의 안 겹침(예: 손에 든 헬멧)
    helmet_far = (100.0, 250.0, 140.0, 290.0)
    result = evaluate_ppe_compliance(PERSON, head_boxes=[head], helmet_boxes=[helmet_far])
    assert result.helmet == ComplianceState.NOT_WORN


def test_helmet_color_alone_does_not_force_worn_when_head_present_but_not_aligned():
    # 색상만 보고 "헬멧 클래스가 잡혔으니 착용"이라 판단하지 않는다는 게 이 규칙의 핵심 —
    # head가 있는데 helmet과 안 겹치면(다른 위치의 밝은 색 물체 등) NOT_WORN이어야 한다.
    head = (130.0, 100.0, 170.0, 140.0)
    unrelated_bright_object = (180.0, 200.0, 220.0, 240.0)
    result = evaluate_ppe_compliance(PERSON, head_boxes=[head], helmet_boxes=[unrelated_bright_object])
    assert result.helmet == ComplianceState.NOT_WORN


def test_no_head_falls_back_to_direct_helmet_signal():
    helmet_box = (130.0, 100.0, 170.0, 140.0)
    result = evaluate_ppe_compliance(PERSON, helmet_boxes=[helmet_box])
    assert result.helmet == ComplianceState.WORN


def test_no_head_and_no_helmet_signal_is_unknown():
    # no_helmet 클래스를 뺀 뒤로는, head가 안 잡히면 미착용을 확정할 근거가 없어 UNKNOWN이어야 한다.
    result = evaluate_ppe_compliance(PERSON)
    assert result.helmet == ComplianceState.UNKNOWN
    assert result.helmet_iou is None  # head가 없어 IoU 자체를 계산하지 않음


def test_vest_present_is_worn():
    vest_box = (110.0, 150.0, 190.0, 250.0)
    result = evaluate_ppe_compliance(PERSON, vest_boxes=[vest_box])
    assert result.vest == ComplianceState.WORN


def test_no_vest_present_is_not_worn():
    no_vest_box = (110.0, 150.0, 190.0, 250.0)
    result = evaluate_ppe_compliance(PERSON, no_vest_boxes=[no_vest_box])
    assert result.vest == ComplianceState.NOT_WORN


def test_vest_missing_entirely_is_unknown_not_worn():
    # CLAUDE.md 절대 원칙과 같은 방향 — 판단 근거가 없으면 미착용이 아니라 UNKNOWN이어야 한다.
    result = evaluate_ppe_compliance(PERSON)
    assert result.vest == ComplianceState.UNKNOWN


def test_conflicting_vest_signals_prefer_not_worn():
    vest_box = (110.0, 150.0, 190.0, 250.0)
    no_vest_box = (110.0, 150.0, 190.0, 250.0)
    result = evaluate_ppe_compliance(PERSON, vest_boxes=[vest_box], no_vest_boxes=[no_vest_box])
    assert result.vest == ComplianceState.NOT_WORN


def test_boxes_outside_person_are_ignored():
    far_away_helmet = (1000.0, 1000.0, 1040.0, 1040.0)
    result = evaluate_ppe_compliance(PERSON, helmet_boxes=[far_away_helmet])
    assert result.helmet == ComplianceState.UNKNOWN
