import { useEffect, useMemo, useRef, useState } from "react";
import {
  Activity,
  AlertTriangle,
  Camera,
  CheckCircle2,
  ChevronRight,
  Clock3,
  Flame,
  HardHat,
  MapPinned,
  Play,
  ShieldCheck,
  Sparkles,
  Users,
  Video,
  X,
} from "lucide-react";
import "./App.css";
import { DEMO_VIDEO_URL, fetchZoneMap, resetScenario, startScenario } from "./api";
import { AppNavigation, NAV_ITEMS, type TabId } from "./components/AppNavigation";
import { DashboardTimeline } from "./components/DashboardTimeline";
import { DetectionOverlay } from "./components/DetectionOverlay";
import { FireAlertModal } from "./components/FireAlertModal";
import { FigmaIcon } from "./components/FigmaIcon";
import { PpeViolationCard } from "./components/PpeViolationCard";
import { PpeViolationEditModal } from "./components/PpeViolationEditModal";
import { SituationCard } from "./components/SituationCard";
import { SituationChatPanel } from "./components/SituationChatPanel";
import { SituationDetailModal } from "./components/SituationDetailModal";
import { StatCard } from "./components/StatCard";
import { ZoneGuideImage } from "./components/ZoneGuideImage";
import { useLiveState } from "./hooks/useLiveState";
import { buildSituationIntervals } from "./situationUtils";
import type { ZoneMapConfig } from "./types";

const DEMO_CAMERA_ID = "demo-camera";
const VALID_TABS = new Set<TabId>(NAV_ITEMS.map((item) => item.id));

function tabFromHash(): TabId {
  const hash = window.location.hash.replace(/^#\/?/, "") as TabId;
  return VALID_TABS.has(hash) ? hash : "overview";
}

function formatTime(value: string | null | undefined) {
  if (!value) return "기록 없음";
  return new Date(value).toLocaleTimeString("ko-KR", { hour: "2-digit", minute: "2-digit", second: "2-digit" });
}

interface PageHeadingProps {
  eyebrow: string;
  title: string;
  description: string;
  action?: React.ReactNode;
}

function PageHeading({ eyebrow, title, description, action }: PageHeadingProps) {
  return (
    <div className="page-heading">
      <div>
        <span className="page-heading__eyebrow">{eyebrow}</span>
        <h1>{title}</h1>
        <p>{description}</p>
      </div>
      {action && <div className="page-heading__action">{action}</div>}
    </div>
  );
}

function EmptyState({ icon, title, description, action }: { icon: React.ReactNode; title: string; description: string; action?: React.ReactNode }) {
  return (
    <div className="empty-state">
      <span className="empty-state__icon">{icon}</span>
      <h3>{title}</h3>
      <p>{description}</p>
      {action}
    </div>
  );
}

function App() {
  const [liveRefreshKey, setLiveRefreshKey] = useState(0);
  const snapshot = useLiveState(liveRefreshKey);
  const [activeTab, setActiveTab] = useState<TabId>(tabFromHash);
  const [scenarioStarting, setScenarioStarting] = useState(false);
  const [scenarioActionError, setScenarioActionError] = useState<string | null>(null);
  const [selectedAt, setSelectedAt] = useState<string | null>(null);
  const [selectedPpeId, setSelectedPpeId] = useState<string | null>(null);
  const [showFireAlert, setShowFireAlert] = useState(false);
  const [showSituationChat, setShowSituationChat] = useState(false);
  const [zoneMap, setZoneMap] = useState<ZoneMapConfig | null>(null);
  const videoRef = useRef<HTMLVideoElement>(null);
  const emergencyRedirected = useRef(false);
  const emergencyMode = snapshot.fire_alert != null;

  const refreshZoneMap = () => {
    fetchZoneMap(DEMO_CAMERA_ID)
      .then(setZoneMap)
      .catch(() => setZoneMap(null));
  };

  useEffect(refreshZoneMap, []);

  useEffect(() => {
    const onHashChange = () => setActiveTab(tabFromHash());
    window.addEventListener("hashchange", onHashChange);
    return () => window.removeEventListener("hashchange", onHashChange);
  }, []);

  useEffect(() => {
    if (emergencyMode && !emergencyRedirected.current) {
      emergencyRedirected.current = true;
      setActiveTab("emergency");
      window.history.replaceState(null, "", "#emergency");
    }
    if (!emergencyMode) emergencyRedirected.current = false;
  }, [emergencyMode]);

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
  }, [snapshot.running, snapshot.frame_t, activeTab]);

  useEffect(() => {
    const video = videoRef.current;
    if (!video || !snapshot.running || snapshot.frame_t == null) return;
    if (Math.abs(video.currentTime - snapshot.frame_t) > 0.4) video.currentTime = snapshot.frame_t;
  }, [snapshot.frame_t, snapshot.running]);

  const navigate = (tab: TabId) => {
    setActiveTab(tab);
    window.history.replaceState(null, "", `#${tab}`);
    window.scrollTo({ top: 0, behavior: "smooth" });
  };

  const handleStartScenario = async () => {
    if (snapshot.running || scenarioStarting) return;
    setScenarioStarting(true);
    setScenarioActionError(null);
    try {
      await startScenario(1);
      setLiveRefreshKey((key) => key + 1);
    } catch (error) {
      setScenarioActionError(error instanceof Error ? error.message : "시나리오를 시작하지 못했습니다.");
    } finally {
      setScenarioStarting(false);
    }
  };

  const handleResetScenario = async () => {
    setScenarioActionError(null);
    try {
      await resetScenario();
      setLiveRefreshKey((key) => key + 1);
    } catch (error) {
      setScenarioActionError(error instanceof Error ? error.message : "시나리오를 초기화하지 못했습니다.");
    }
  };

  const scenarioActive = snapshot.running || scenarioStarting;

  const personCount = useMemo(
    () => snapshot.current_detections.filter((d) => d.object_class === "person").length,
    [snapshot.current_detections],
  );
  const situationChecksNewestFirst = useMemo(() => [...snapshot.situation_checks].reverse(), [snapshot.situation_checks]);
  const situationIntervals = useMemo(() => buildSituationIntervals(snapshot.situation_checks), [snapshot.situation_checks]);
  const situationIntervalsNewestFirst = useMemo(() => [...situationIntervals].reverse(), [situationIntervals]);
  const ppeEventsNewestFirst = useMemo(() => [...snapshot.ppe_violation_events].reverse(), [snapshot.ppe_violation_events]);
  const recentEvents = useMemo(() => [...snapshot.event_feed].reverse().slice(0, 7), [snapshot.event_feed]);
  const selectedEntry = selectedAt ? (snapshot.situation_checks.find((entry) => entry.at === selectedAt) ?? null) : null;
  const selectedInterval = selectedAt ? (situationIntervals.find((interval) => interval.end.at === selectedAt) ?? null) : null;
  const selectedPpeEntry = selectedPpeId ? (snapshot.ppe_violation_events.find((entry) => entry.id === selectedPpeId) ?? null) : null;
  const registeredZones = zoneMap?.zones ?? [];
  const observedZoneTotal = Object.values(snapshot.zone_person_counts).reduce((sum, count) => sum + count, 0);
  const helmetWarnings = snapshot.current_person_compliance.filter((item) => item.helmet === "not_worn").length;
  const vestWarnings = snapshot.current_person_compliance.filter((item) => item.vest === "not_worn").length;
  const eventElapsedLabel = (at: string) => {
    if (!snapshot.scenario_started_at) return formatTime(at);
    const elapsed = Math.max(0, Math.round((new Date(at).getTime() - new Date(snapshot.scenario_started_at).getTime()) / 1000));
    return elapsed === 0 ? "촬영 시작 +0초" : `영상 +${elapsed}초`;
  };
  const eventCategory = (text: string) => {
    if (/PPE|안전모|조끼|미착용/.test(text)) return "PPE";
    if (/검토|관리자/.test(text)) return "PPE 판정";
    return "시스템";
  };

  const liveCamera = (
    <section className="camera-panel surface-card">
      <div className="section-heading">
        <div>
          <span className="section-heading__eyebrow">LIVE · CAM-01</span>
          <h2>실시간 CCTV 분석</h2>
        </div>
        <span className={`live-pill ${scenarioActive ? "is-running" : ""}`}>
          <span /> {scenarioStarting ? "연결 중" : snapshot.running ? "분석 중" : "대기 중"}
        </span>
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
          {!scenarioActive && (
            <div className="camera-feed__standby">
              <Video size={28} />
              <strong>시나리오 대기 중</strong>
              <span>상단의 시작 버튼을 누르면 분석 결과가 표시됩니다.</span>
            </div>
          )}
        </div>
        <div className="camera-feed__caption">
          <span>demo-camera</span>
          <span>프레임 #{snapshot.frame_idx}</span>
          <span>{snapshot.frame_width} × {snapshot.frame_height}</span>
        </div>
      </div>
    </section>
  );

  const overviewPage = (
    <>
      <PageHeading eyebrow="OVERVIEW" title={emergencyMode ? "비상 대응 현황" : "오늘의 안전 현황"} description="현장의 주요 상태와 확인이 필요한 항목을 한 눈에 확인할 수 있어요." />
      <div
        className="metric-grid"
        tabIndex={0}
        aria-label="안전 현황 요약 카드 가로 목록"
        onWheel={(event) => {
          if (Math.abs(event.deltaY) <= Math.abs(event.deltaX)) return;
          event.currentTarget.scrollLeft += event.deltaY;
          event.preventDefault();
        }}
      >
        <StatCard label="PPE 미착용" value={`${snapshot.ppe_violations_today}건`} detail={snapshot.ppe_violations_today > 0 ? "관리자 검토 필요" : "신규 위반 없음"} tone={snapshot.ppe_violations_today > 0 ? "warning" : "default"} icon={<FigmaIcon name="ppe" size={25} />} onClick={() => navigate("ppe")} />
        <StatCard label="현재 관측 인원" value={`${snapshot.current_person_compliance.length}명`} detail={`구역 집계 ${observedZoneTotal}명`} icon={<FigmaIcon name="people" size={25} />} onClick={() => navigate("monitoring")} />
        <StatCard label="등록 구역" value={`${registeredZones.length}개`} detail="카메라 분석 구역" icon={<FigmaIcon name="area" size={25} />} onClick={() => navigate("monitoring")} />
        <StatCard label="시스템 모드" value={emergencyMode ? "비상" : "정상"} detail={emergencyMode ? "전체 화면 비상 상태 동기화" : "모든 분석 기능 연결됨"} tone={emergencyMode ? "danger" : "default"} icon={emergencyMode ? <Flame size={20} /> : <FigmaIcon name="settings" size={24} />} onClick={() => navigate(emergencyMode ? "emergency" : "monitoring")} />
      </div>

      <div className="overview-grid">
        <section className="surface-card zone-overview">
          <div className="section-heading">
            <div><span className="section-heading__eyebrow">ZONE STATUS</span><h2>구역별 관측 현황</h2></div>
            <button className="text-button" type="button" onClick={() => navigate("monitoring")}>구역 확인 <FigmaIcon name="arrow" size={16} /></button>
          </div>
          <div className="zone-card-grid">
            {registeredZones.length === 0 ? (
              <EmptyState icon={<MapPinned size={25} />} title="등록된 구역이 없습니다" description="백엔드에 저장된 구역 정보를 확인해 주세요." />
            ) : registeredZones.map((zone) => (
              <button key={zone.zone_id} className="zone-card" type="button" onClick={() => navigate("monitoring")}>
                <span className="zone-card__header"><strong>{zone.zone_id}</strong><span>{snapshot.zone_person_counts[zone.zone_id] ?? 0}명 관측</span></span>
                <span className="zone-card__preview"><span>참고 프레임 · 클릭하여 확대</span></span>
              </button>
            ))}
          </div>
        </section>

        <section className="surface-card event-feed-card">
          <div className="section-heading">
            <div><span className="section-heading__eyebrow">RECENT EVENT</span><h2>최근 이벤트</h2></div>
            <button className="text-button" type="button" onClick={() => navigate("timeline")}>전체 기록 <FigmaIcon name="arrow" size={16} /></button>
          </div>
          <div className="event-list">
            {recentEvents.length === 0 ? (
              <EmptyState icon={<Activity size={24} />} title="아직 이벤트가 없습니다" description="시나리오를 시작하면 주요 변화가 기록됩니다." />
            ) : recentEvents.map((event) => (
              <button key={`${event.at}-${event.text}`} type="button" className="event-row" onClick={() => navigate("timeline")}>
                <span>{eventElapsedLabel(event.at)}</span><i>·</i><strong>{eventCategory(event.text)}</strong><i>·</i><span>{event.text}</span>
              </button>
            ))}
          </div>
        </section>
      </div>
    </>
  );

  const monitoringPage = (
    <>
      <PageHeading eyebrow="LIVE MONITORING" title="실시간 관제" description="CCTV 영상 위에서 사람·PPE 판정과 구역별 관측 상태를 동시에 확인할 수 있어요." />
      <div className="monitor-layout">
        {liveCamera}
        <aside className="monitor-side">
          <section className="surface-card compact-card">
            <div className="section-heading"><div><span className="section-heading__eyebrow">CURRENT FRAME</span><h2>현재 프레임 판정</h2></div></div>
            <div className="frame-status-list">
              <div><span><Users size={17} /> 사람 관측</span><strong>{personCount}명</strong></div>
              <div><span><HardHat size={17} /> 안전모 확인 필요</span><strong className={helmetWarnings > 0 ? "is-warning" : ""}>{helmetWarnings}명</strong></div>
              <div><span><ShieldCheck size={17} /> 조끼 확인 필요</span><strong className={vestWarnings > 0 ? "is-warning" : ""}>{vestWarnings}명</strong></div>
              <div><span><Camera size={17} /> 카메라 상태</span><strong className="is-ok">연결됨</strong></div>
            </div>
          </section>
          <section className="surface-card compact-card">
            <div className="section-heading"><div><span className="section-heading__eyebrow">ZONE COUNTS</span><h2>구역별 인원</h2></div></div>
            <div className="zone-count-list">
              {registeredZones.map((zone) => <div key={zone.zone_id}><span>{zone.zone_id}</span><strong>{snapshot.zone_person_counts[zone.zone_id] ?? 0}명</strong></div>)}
              {registeredZones.length === 0 && <p className="inline-empty">구역을 등록하면 인원 집계가 표시됩니다.</p>}
            </div>
            <ZoneGuideImage
              zones={registeredZones}
              personCounts={snapshot.zone_person_counts}
              frameWidth={zoneMap?.image_width ?? snapshot.frame_width}
              frameHeight={zoneMap?.image_height ?? snapshot.frame_height}
            />
          </section>
        </aside>
      </div>
    </>
  );

  const timelinePage = (
    <>
      <PageHeading eyebrow="UNIFIED HISTORY" title="통합 타임라인" description="PPE 이벤트부터 화재 감지와 2차 확인까지 하나의 사건 흐름으로 연결하여 확인할 수 있어요." />
      <section id="unified-timeline" className="surface-card timeline-page-card">
        <div className="timeline-legend">
          <span><i className="legend-dot is-start" /> 시나리오 시작</span>
          <span><i className="legend-dot is-ppe" /> PPE 판정</span>
          <span><i className="legend-dot is-fire" /> 화재 감지</span>
          <span><i className="legend-dot is-check" /> 2차 확인</span>
        </div>
        {snapshot.scenario_started_at ? (
          <DashboardTimeline
            cameraId={DEMO_CAMERA_ID}
            scenarioStartedAt={snapshot.scenario_started_at}
            fireAlert={snapshot.fire_alert}
            ppeEvents={snapshot.ppe_violation_events}
            situationChecks={snapshot.situation_checks}
            onSelectPpe={(entry) => setSelectedPpeId(entry.id)}
            onSelectSituation={(entry) => setSelectedAt(entry.at)}
            onSelectFire={() => setShowFireAlert(true)}
            onDataChanged={() => setLiveRefreshKey((key) => key + 1)}
          />
        ) : (
          <EmptyState icon={<Clock3 size={28} />} title="타임라인이 비어 있습니다" description="시나리오를 시작하면 모든 주요 이벤트가 시간순으로 연결됩니다." action={<button type="button" className="primary-button" onClick={handleStartScenario} disabled={scenarioActive}><Play size={17} /> {scenarioStarting ? "연결 중" : "시나리오 시작"}</button>} />
        )}
      </section>
      <section className="surface-card timeline-summary-card">
        <div className="section-heading"><div><h2>최근 판정 기록</h2><span className="section-heading__eyebrow">EVENT SUMMARY</span></div><span className="timeline-summary-hint">노드를 눌러 상세 확인</span></div>
        <div className="timeline-summary-grid">
          <button type="button" onClick={() => navigate("ppe")}><FigmaIcon name="summaryPpe" size={25}/><strong>PPE 미착용</strong><small>관리자 검토 필요</small><b>{snapshot.ppe_violations_today}건</b><FigmaIcon name="arrow" size={25} className="shortcut-arrow"/></button>
          <button type="button" onClick={() => navigate("emergency")}><FigmaIcon name="summaryAlarm" size={24}/><strong>화재 경보</strong><small>자동 탐지</small><b>{snapshot.fire_alert ? 1 : 0}건</b><FigmaIcon name="arrow" size={25} className="shortcut-arrow"/></button>
          <button type="button" onClick={() => navigate("emergency")}><FigmaIcon name="summaryZoom" size={25}/><strong>2차 확인</strong><small>{snapshot.situation_checks.length}개 별도 구간</small><b>{situationIntervals.length}회</b><FigmaIcon name="arrow" size={25} className="shortcut-arrow"/></button>
          <button type="button" onClick={() => document.getElementById("unified-timeline")?.scrollIntoView({ behavior: "smooth", block: "start" })}><FigmaIcon name="summaryReport" size={25}/><strong>통합 기록</strong><small>동일인 중복 정리</small><b>{snapshot.event_feed.length}건</b><FigmaIcon name="arrow" size={25} className="shortcut-arrow"/></button>
        </div>
      </section>
    </>
  );

  const ppePage = (
    <>
      <PageHeading eyebrow="PPE REVIEW" title="안전장비 판정 검토" description="AI 원판정과 증거 프레임을 확인하고 안전모·조끼 상태를 관리자가 정정할 수 있어요." action={<span className="page-count-badge">총 {ppeEventsNewestFirst.length}건</span>} />
      <div className="info-banner"><CheckCircle2 size={19} /><span>관리자 검토 전·후 상태가 모두 보존됩니다. 카드를 눌러 착용/미착용을 확정하세요.</span></div>
      {ppeEventsNewestFirst.length === 0 ? (
        <section className="surface-card"><EmptyState icon={<HardHat size={30} />} title="검토할 PPE 기록이 없습니다" description="시나리오 실행 중 미착용이 감지되면 근거 사진과 함께 카드가 생성됩니다." /></section>
      ) : (
        <div className="worker-grid review-grid">
          {ppeEventsNewestFirst.map((entry) => <PpeViolationCard key={entry.id} entry={entry} onClick={() => setSelectedPpeId(entry.id)} />)}
        </div>
      )}
    </>
  );

  const emergencyPage = (
    <>
      <PageHeading eyebrow="EMERGENCY RESPONSE" title="비상 대응" description="화재 경보와 2차 확인 정보를 함께 보며 구조 판단 근거를 확인할 수 있어요." action={<button type="button" className="secondary-button" onClick={() => navigate("timeline")}><Activity size={17} /> 사고 흐름 보기</button>} />
      {!snapshot.fire_alert ? (
        <section className="surface-card emergency-ready"><EmptyState icon={<ShieldCheck size={32} />} title="현재 화재 경보가 없습니다" description="경보가 감지되면 모든 탭이 비상 모드로 동기화되고 이 화면으로 자동 이동합니다." /></section>
      ) : (
        <>
          <button type="button" className="emergency-hero" onClick={() => setShowFireAlert(true)}>
            <span className="emergency-hero__icon"><Flame size={28} /></span>
            <span><small>FIRE ALERT · {snapshot.fire_alert.source === "auto_detection" ? "자동 탐지" : "수동 경보"}</small><strong>{snapshot.fire_alert.zone_id ?? "구역 미확인"} 화재 경보</strong><span>{formatTime(snapshot.fire_alert.triggered_at)} 발생 · 신뢰도 {snapshot.fire_alert.confidence != null ? `${Math.round(snapshot.fire_alert.confidence * 100)}%` : "확인 중"}</span></span>
            <ChevronRight size={22} />
          </button>
          <div className="metric-grid emergency-metrics">
            <StatCard label="현재 화면 관측" value={`${personCount}명`} detail="이번 프레임 기준" icon={<Users size={20} />} />
            <StatCard label="상황 변화 구간" value={`${situationIntervals.length}건`} detail={`원본 확인 ${situationChecksNewestFirst.length}회 · 추정 정보`} tone="warning" icon={<Sparkles size={20} />} />
            <StatCard label="등록 구역" value={`${registeredZones.length}개`} detail="구역별 상황 집계" icon={<MapPinned size={20} />} />
            <StatCard label="경보 상태" value="대응 중" detail="전 탭 비상 모드 동기화" tone="danger" icon={<AlertTriangle size={20} />} />
          </div>
          <section className="surface-card">
            <div className="section-heading">
              <div><span className="section-heading__eyebrow">SECONDARY CHECK</span><h2>최근 2차 확인</h2></div>
              <span className="estimate-label">추정 정보 · 확정 아님</span>
            </div>
            {situationIntervalsNewestFirst.length === 0 ? (
              <EmptyState icon={<Sparkles size={26} />} title="2차 확인 진행 중" description="확인 결과가 생성되면 근거 프레임과 구역별 집계가 표시됩니다." />
            ) : (
              <div className="worker-grid emergency-grid">{situationIntervalsNewestFirst.map((interval) => <SituationCard key={interval.start.at} interval={interval} fireTriggeredAt={snapshot.fire_alert?.triggered_at ?? null} onClick={() => setSelectedAt(interval.end.at)} />)}</div>
            )}
          </section>
        </>
      )}
    </>
  );

  const pages: Record<TabId, React.ReactNode> = {
    overview: overviewPage,
    monitoring: monitoringPage,
    timeline: timelinePage,
    ppe: ppePage,
    emergency: emergencyPage,
  };

  return (
    <div className={`app-shell ${emergencyMode ? "app-shell--emergency" : "app-shell--normal"}`}>
      <AppNavigation activeTab={activeTab} emergencyMode={emergencyMode} running={snapshot.running} ppeCount={ppeEventsNewestFirst.length} situationCount={situationIntervals.length} onNavigate={navigate} />
      <div className="workspace">
        <header className="topbar">
          <div className="topbar__context">
            <span className={`topbar__mode ${emergencyMode ? "is-emergency" : ""}`}><span /> {emergencyMode ? "비상 모드" : "정상 모드"}</span>
            <span className="topbar__divider" />
            <span>{NAV_ITEMS.find((item) => item.id === activeTab)?.label}</span>
          </div>
          <div className="topbar__actions">
            <button type="button" className="secondary-button topbar-chat-button" onClick={() => setShowSituationChat(true)} aria-haspopup="dialog">
              <FigmaIcon name="chatAi" size={16} /> <span>구조 브리핑 AI 챗봇</span>
            </button>
            <button type="button" className="secondary-button" onClick={handleResetScenario}><span className="topbar-symbol" aria-hidden="true">↻</span> 초기화</button>
            <button type="button" className="primary-button" onClick={handleStartScenario} disabled={scenarioActive}><span className="topbar-symbol topbar-symbol--play" aria-hidden="true">▶</span> {scenarioStarting ? "연결 중" : snapshot.running ? "시나리오 실행 중" : "시나리오 시작"}</button>
          </div>
        </header>

        {scenarioActionError && (
          <div className="connection-error" role="alert">
            <AlertTriangle size={17} />
            <span>{scenarioActionError} Render 서버가 잠든 경우 첫 연결에 잠시 걸릴 수 있습니다.</span>
          </div>
        )}

        {emergencyMode && snapshot.fire_alert && (
          <button type="button" className="global-alert" onClick={() => navigate("emergency")}>
            <span><Flame size={19} fill="currentColor" /> 화재 경보</span>
            <strong>{snapshot.fire_alert.zone_id ?? "구역 미확인"}</strong>
            <span>{formatTime(snapshot.fire_alert.triggered_at)} · 모든 화면이 비상 모드로 동기화되었습니다.</span>
            <ChevronRight size={19} />
          </button>
        )}

        <main className="page-content">{pages[activeTab]}</main>
      </div>

      {showFireAlert && snapshot.fire_alert && <FireAlertModal alert={snapshot.fire_alert} onClose={() => setShowFireAlert(false)} onOpenEmergency={() => { setShowFireAlert(false); navigate("emergency"); }} />}
      {selectedEntry && <SituationDetailModal entry={selectedEntry} frameWidth={snapshot.frame_width} frameHeight={snapshot.frame_height} rangeStartAt={selectedInterval?.start.at} sampleCount={selectedInterval?.sampleCount} fireTriggeredAt={snapshot.fire_alert?.triggered_at ?? null} onClose={() => setSelectedAt(null)} onAskBriefing={() => { setSelectedAt(null); setShowSituationChat(true); }} />}
      {selectedPpeEntry && <PpeViolationEditModal entry={selectedPpeEntry} cameraId={DEMO_CAMERA_ID} frameWidth={snapshot.frame_width} frameHeight={snapshot.frame_height} onClose={() => setSelectedPpeId(null)} onSaved={() => setLiveRefreshKey((key) => key + 1)} />}
      <div className={`chat-drawer-backdrop ${showSituationChat ? "is-open" : ""}`} onClick={() => setShowSituationChat(false)} aria-hidden={!showSituationChat}>
        <aside className="chat-drawer" role="dialog" aria-modal="true" aria-labelledby="chat-drawer-title" onClick={(event) => event.stopPropagation()}>
          <div className="chat-drawer__header">
            <div><h2 id="chat-drawer-title">구조 브리핑 챗봇</h2><span>AI RESCUE BRIEFING</span></div>
            <button type="button" onClick={() => setShowSituationChat(false)} aria-label="구조 브리핑 챗봇 닫기"><X size={21} /></button>
          </div>
          <SituationChatPanel />
        </aside>
      </div>
    </div>
  );
}

export default App;
