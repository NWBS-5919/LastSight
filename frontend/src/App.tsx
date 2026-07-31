import { useMemo, useState } from "react";
import "./App.css";
import { frameUrl, resetScenario, startScenario } from "./api";
import { BriefingModal } from "./components/BriefingModal";
import { DetectionOverlay } from "./components/DetectionOverlay";
import { EventFeed } from "./components/EventFeed";
import { StatCard } from "./components/StatCard";
import { WorkerCard } from "./components/WorkerCard";
import { useLiveState } from "./hooks/useLiveState";

function App() {
  const snapshot = useLiveState();
  const [selected, setSelected] = useState<string | null>(null);
  const emergencyMode = snapshot.fire_alert != null;

  const summary = useMemo(() => {
    const counts = { inside_observed: 0, prolonged_presence: 0, tracking_lost: 0, camera_failure: 0 };
    for (const w of snapshot.workers) {
      counts[w.event] = (counts[w.event] ?? 0) + 1;
    }
    return counts;
  }, [snapshot.workers]);

  return (
    <div className={`app ${emergencyMode ? "app--emergency" : "app--normal"}`}>
      <header className="app__header">
        <div>
          <h1>LastSight AI</h1>
          <p className="app__subtitle">{emergencyMode ? "🔥 비상 대시보드" : "평상시 안전 대시보드"}</p>
        </div>
        <div className="app__controls">
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
          🔥 화재경보 — {new Date(snapshot.fire_alert.triggered_at).toLocaleTimeString("ko-KR")} 발생 · 트리거:{" "}
          {snapshot.fire_alert.source === "auto_detection" ? "자동탐지" : "수동"}
          {snapshot.fire_alert.confidence != null && ` · 신뢰도 ${(snapshot.fire_alert.confidence * 100).toFixed(0)}%`}
        </div>
      )}

      <div className="app__body">
        <div className="app__main">
          <div className="stat-row">
            {emergencyMode ? (
              <>
                <StatCard label="관측 대상 인원" value={snapshot.workers.length} />
                <StatCard label="관측 중" value={summary.inside_observed} tone="default" />
                <StatCard label="장기체류경고" value={summary.prolonged_presence} tone="warning" />
                <StatCard label="관측 안 됨" value={summary.tracking_lost} tone="danger" />
              </>
            ) : (
              <>
                <StatCard label="오늘 PPE 미착용 적발" value={snapshot.ppe_violations_today} tone="warning" />
                <StatCard label="현재 관측 인원" value={snapshot.workers.length} />
                {Object.entries(snapshot.zone_person_counts).map(([zone, count]) => (
                  <StatCard key={zone} label={zone} value={count} />
                ))}
              </>
            )}
          </div>

          {snapshot.frame_image_url && (
            <div className="camera-feed">
              <div className="camera-feed__frame">
                <img src={frameUrl(snapshot.frame_image_url)} alt="카메라 화면" />
                <DetectionOverlay
                  detections={snapshot.current_detections}
                  frameWidth={snapshot.frame_width}
                  frameHeight={snapshot.frame_height}
                />
              </div>
              <div className="camera-feed__caption">demo-camera · frame #{snapshot.frame_idx}</div>
            </div>
          )}

          <div className="worker-grid">
            {snapshot.workers.length === 0 && <p className="empty-hint">"시나리오 시작"을 누르면 작업자 상태가 표시됩니다.</p>}
            {snapshot.workers.map((w) => (
              <WorkerCard key={w.track_id} worker={w} onClick={() => setSelected(w.track_id)} />
            ))}
          </div>
        </div>

        <aside className="app__sidebar">
          <EventFeed events={snapshot.event_feed} />
        </aside>
      </div>

      {selected && <BriefingModal trackId={selected} onClose={() => setSelected(null)} />}
    </div>
  );
}

export default App;
