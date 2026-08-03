import { useEffect, useMemo, useRef, useState } from "react";
import "./App.css";
import { DEMO_VIDEO_URL, fetchZoneMap, resetScenario, startScenario } from "./api";
import { DashboardTimeline } from "./components/DashboardTimeline";
import { DetectionOverlay } from "./components/DetectionOverlay";
import { FireAlertModal } from "./components/FireAlertModal";
import { PpeViolationCard } from "./components/PpeViolationCard";
import { PpeViolationEditModal } from "./components/PpeViolationEditModal";
import { SituationCard } from "./components/SituationCard";
import { SituationDetailModal } from "./components/SituationDetailModal";
import { StatCard } from "./components/StatCard";
import { ZoneMapModal } from "./components/ZoneMapModal";
import { useLiveState } from "./hooks/useLiveState";
import type { ZoneMapConfig } from "./types";

const DEMO_CAMERA_ID = "demo-camera";

function App() {
  const snapshot = useLiveState();
  const [selectedAt, setSelectedAt] = useState<string | null>(null);
  const [selectedPpeId, setSelectedPpeId] = useState<string | null>(null);
  const [showFireAlert, setShowFireAlert] = useState(false);
  const [showPpeCards, setShowPpeCards] = useState(false);
  const [showSituationCards, setShowSituationCards] = useState(false);
  const [showZoneMap, setShowZoneMap] = useState(false);
  const [zoneMap, setZoneMap] = useState<ZoneMapConfig | null>(null);
  const emergencyMode = snapshot.fire_alert != null;
  const videoRef = useRef<HTMLVideoElement>(null);

  // 구역 목록은 대시보드 카드가 "0명"도 항상 보여줄 수 있게 미리 받아둔다 — 구역
  // 편집 모달에서 저장하면(onSaved) 다시 불러와 새/삭제된 구역이 카드에 바로 반영된다.
  const refreshZoneMap = () => {
    fetchZoneMap(DEMO_CAMERA_ID)
      .then(setZoneMap)
      .catch(() => setZoneMap(null));
  };
  useEffect(refreshZoneMap, []);

  // 사전계산 샘플(초당 1장) 정지 이미지 대신 원본 영상을 그대로 재생한다 — 박스만 웹소켓으로
  // 주기적으로 갱신되고, 화면 자체는 원본 프레임 그대로 매끄럽게 흘러간다(annotate_pipeline_video.py로
  // 만든 오프라인 데모 영상과 같은 방식). 시나리오 시작/초기화에 맞춰 재생을 같이 제어한다.
  useEffect(() => {
    const video = videoRef.current;
    if (!video) return;
    if (!snapshot.running) {
      video.pause();
      return;
    }
    if (video.paused) {
      video.currentTime = snapshot.frame_t ?? 0;
      video.play().catch(() => {});
    }
  }, [snapshot.running]);

  // 2026-08-03: <video> 재생과 박스 갱신(백엔드 target_elapsed 페이싱)은 서로 독립된
  // 시계다 — 시작 시점의 웹소켓 왕복 지연·영상 디코딩 지연 때문에 초기 오프셋이 생기고,
  // 화재 이후 구간처럼 갱신이 촘촘해지면(0.25초) 그 오프셋이 눈에 띄게 느껴진다. 매
  // 스냅샷마다 영상 재생 위치와 박스가 나타내는 시각(frame_t)의 차이를 확인해서, 일정
  // 이상(threshold) 벌어지면 그 시각으로 다시 맞춘다 — 매번 강제로 맞추면(threshold=0)
  // 자연스러운 재생이 뚝뚝 끊겨 보이므로, 눈에 띄게 벌어졌을 때만 보정한다.
  useEffect(() => {
    const video = videoRef.current;
    if (!video || !snapshot.running || snapshot.frame_t == null) return;
    const drift = Math.abs(video.currentTime - snapshot.frame_t);
    if (drift > 0.4) {
      video.currentTime = snapshot.frame_t;
    }
  }, [snapshot.frame_t, snapshot.running]);

  const personCount = useMemo(
    () => snapshot.current_detections.filter((d) => d.object_class === "person").length,
    [snapshot.current_detections],
  );

  const situationChecksNewestFirst = useMemo(() => [...snapshot.situation_checks].reverse(), [snapshot.situation_checks]);
  const selectedEntry = selectedAt ? (snapshot.situation_checks.find((e) => e.at === selectedAt) ?? null) : null;
  const ppeEventsNewestFirst = useMemo(() => [...snapshot.ppe_violation_events].reverse(), [snapshot.ppe_violation_events]);
  const selectedPpeEntry = selectedPpeId ? (snapshot.ppe_violation_events.find((e) => e.id === selectedPpeId) ?? null) : null;

  return (
    <div className={`app ${emergencyMode ? "app--emergency" : "app--normal"}`}>
      <header className="app__header">
        <div>
          <div className="app__title">
            <h1>LastSight AI</h1>
            <span className="app__status">
              <span className="app__status-dot" />
              {emergencyMode ? "SYS-ALERT" : "SYS-NORMAL"}
            </span>
          </div>
          <p className="app__subtitle">{emergencyMode ? "비상 대시보드" : "평상시 안전 대시보드"}</p>
        </div>
        <div className="app__controls">
          <button onClick={() => setShowZoneMap(true)} className="app__controls-reset">
            구역 보기
          </button>
          <button onClick={() => startScenario(1.0)} disabled={snapshot.running}>
            {snapshot.running ? "시나리오 재생 중..." : "시나리오 시작"}
          </button>
          <button onClick={() => resetScenario()} className="app__controls-reset">
            초기화
          </button>
        </div>
      </header>

      {emergencyMode && snapshot.fire_alert && (
        <div className="fire-banner">
          <span className="fire-banner__tag">화재경보</span>
          {new Date(snapshot.fire_alert.triggered_at).toLocaleTimeString("ko-KR")} 발생 · 트리거:{" "}
          {snapshot.fire_alert.source === "auto_detection" ? "자동탐지" : "수동"}
          {snapshot.fire_alert.confidence != null && ` · 신뢰도 ${(snapshot.fire_alert.confidence * 100).toFixed(0)}%`}
        </div>
      )}

      <div className="app__body">
        <div className="app__main">
          <div className="stat-row">
            {emergencyMode ? (
              <>
                <StatCard label="현재 관측 인원" value={personCount} />
                {zoneMap?.zones.map((z) => (
                  <StatCard key={z.zone_id} label={z.zone_id} value={snapshot.zone_person_counts[z.zone_id] ?? 0} />
                ))}
              </>
            ) : (
              <>
                <StatCard label="오늘 PPE 미착용 적발" value={snapshot.ppe_violations_today} tone="warning" />
                <StatCard label="현재 관측 인원" value={snapshot.current_person_compliance.length} />
                {zoneMap?.zones.map((z) => (
                  <StatCard key={z.zone_id} label={z.zone_id} value={snapshot.zone_person_counts[z.zone_id] ?? 0} />
                ))}
              </>
            )}
          </div>

          <div className="camera-feed">
            <div className="camera-feed__frame">
              <video ref={videoRef} src={DEMO_VIDEO_URL} muted playsInline />
              <DetectionOverlay
                detections={snapshot.current_detections}
                complianceBoxes={snapshot.current_person_compliance}
                emergencyMode={emergencyMode}
                frameWidth={snapshot.frame_width}
                frameHeight={snapshot.frame_height}
              />
            </div>
            <div className="camera-feed__caption">demo-camera · 박스 갱신 #{snapshot.frame_idx}</div>
          </div>

          {snapshot.scenario_started_at && (
            <DashboardTimeline
              cameraId={DEMO_CAMERA_ID}
              scenarioStartedAt={snapshot.scenario_started_at}
              fireAlert={snapshot.fire_alert}
              ppeEvents={snapshot.ppe_violation_events}
              situationChecks={snapshot.situation_checks}
              onSelectPpe={(entry) => setSelectedPpeId(entry.id)}
              onSelectSituation={(entry) => setSelectedAt(entry.at)}
              onSelectFire={() => setShowFireAlert(true)}
            />
          )}

          {showFireAlert && snapshot.fire_alert && (
            <FireAlertModal alert={snapshot.fire_alert} onClose={() => setShowFireAlert(false)} />
          )}

          <div className="card-section">
            <button className="card-section__toggle" onClick={() => setShowPpeCards((v) => !v)}>
              <span>안전장비 위반 카드 ({ppeEventsNewestFirst.length})</span>
              <span className="card-section__chevron">{showPpeCards ? "숨기기 ▲" : "펼치기 ▼"}</span>
            </button>
            {showPpeCards && (
              <div className="worker-grid">
                {ppeEventsNewestFirst.length === 0 && <p className="empty-hint">"시나리오 시작"을 누르면 PPE 위반이 감지될 때 여기 기록됩니다.</p>}
                {ppeEventsNewestFirst.map((entry) => (
                  <PpeViolationCard key={entry.id} entry={entry} onClick={() => setSelectedPpeId(entry.id)} />
                ))}
              </div>
            )}
          </div>

          <div className="card-section">
            <button className="card-section__toggle" onClick={() => setShowSituationCards((v) => !v)}>
              <span>구조 카드 ({situationChecksNewestFirst.length})</span>
              <span className="card-section__chevron">{showSituationCards ? "숨기기 ▲" : "펼치기 ▼"}</span>
            </button>
            {showSituationCards && (
              <div className="worker-grid">
                {situationChecksNewestFirst.length === 0 && <p className="empty-hint">화재 발생 후 1초마다 2차 확인 카드가 쌓입니다.</p>}
                {situationChecksNewestFirst.map((entry) => (
                  <SituationCard
                    key={entry.at}
                    entry={entry}
                    fireTriggeredAt={snapshot.fire_alert?.triggered_at ?? null}
                    onClick={() => setSelectedAt(entry.at)}
                  />
                ))}
              </div>
            )}
          </div>
        </div>
      </div>

      {selectedEntry && (
        <SituationDetailModal
          entry={selectedEntry}
          frameWidth={snapshot.frame_width}
          frameHeight={snapshot.frame_height}
          onClose={() => setSelectedAt(null)}
        />
      )}

      {selectedPpeEntry && (
        <PpeViolationEditModal
          entry={selectedPpeEntry}
          cameraId={DEMO_CAMERA_ID}
          frameWidth={snapshot.frame_width}
          frameHeight={snapshot.frame_height}
          onClose={() => setSelectedPpeId(null)}
          onSaved={() => {}}
        />
      )}

      {showZoneMap && (
        <ZoneMapModal
          cameraId={DEMO_CAMERA_ID}
          frameWidth={snapshot.frame_width}
          frameHeight={snapshot.frame_height}
          onClose={() => setShowZoneMap(false)}
          onSaved={refreshZoneMap}
        />
      )}
    </div>
  );
}

export default App;
