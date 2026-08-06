import {
  Activity,
  AlertTriangle,
  ClipboardCheck,
  LayoutDashboard,
  ShieldCheck,
  Video,
} from "lucide-react";

export type TabId = "overview" | "monitoring" | "timeline" | "ppe" | "emergency";

export const NAV_ITEMS = [
  { id: "overview", label: "안전 현황", shortLabel: "현황", icon: LayoutDashboard },
  { id: "monitoring", label: "실시간 관제", shortLabel: "관제", icon: Video },
  { id: "timeline", label: "통합 타임라인", shortLabel: "기록", icon: Activity },
  { id: "ppe", label: "PPE 검토", shortLabel: "PPE", icon: ClipboardCheck },
  { id: "emergency", label: "비상 대응", shortLabel: "비상", icon: AlertTriangle },
] as const satisfies ReadonlyArray<{
  id: TabId;
  label: string;
  shortLabel: string;
  icon: typeof LayoutDashboard;
}>;

interface Props {
  activeTab: TabId;
  emergencyMode: boolean;
  running: boolean;
  ppeCount: number;
  situationCount: number;
  onNavigate: (tab: TabId) => void;
}

function NavItems({
  activeTab,
  emergencyMode,
  ppeCount,
  situationCount,
  onNavigate,
  mobile = false,
}: Omit<Props, "running"> & { mobile?: boolean }) {
  return (
    <nav className={mobile ? "mobile-nav__items" : "side-nav"} aria-label="주요 화면">
      {NAV_ITEMS.map((item) => {
        const Icon = item.icon;
        const count = item.id === "ppe" ? ppeCount : item.id === "emergency" ? situationCount : null;
        return (
          <button
            key={item.id}
            type="button"
            className={`${mobile ? "mobile-nav__item" : "side-nav__item"} ${activeTab === item.id ? "is-active" : ""}`}
            onClick={() => onNavigate(item.id)}
            aria-current={activeTab === item.id ? "page" : undefined}
          >
            <span className="nav-icon-wrap">
              <Icon size={mobile ? 19 : 20} strokeWidth={1.9} aria-hidden="true" />
              {mobile && count != null && count > 0 && <span className="mobile-nav__dot" />}
            </span>
            <span>{mobile ? item.shortLabel : item.label}</span>
            {!mobile && count != null && count > 0 && <span className={`side-nav__count ${emergencyMode && item.id === "emergency" ? "is-danger" : ""}`}>{count}</span>}
          </button>
        );
      })}
    </nav>
  );
}

export function AppNavigation(props: Props) {
  return (
    <>
      <aside className="sidebar">
        <div className="brand">
          <span className="brand__mark"><ShieldCheck size={24} strokeWidth={2.1} /></span>
          <span>
            <strong>LastSight</strong>
            <small>AI Safety Console</small>
          </span>
        </div>

        <div className={`mode-card ${props.emergencyMode ? "mode-card--emergency" : ""}`}>
          <span className="mode-card__pulse" />
          <span>
            <small>현재 시스템 모드</small>
            <strong>{props.emergencyMode ? "비상 대응 모드" : "평상시 모니터링"}</strong>
          </span>
        </div>

        <NavItems {...props} />

        <div className="sidebar__footer">
          <span className={`connection-dot ${props.running ? "is-live" : ""}`} />
          <span>
            <strong>{props.running ? "데모 시나리오 실행 중" : "시스템 연결됨"}</strong>
            <small>CAM-01 · demo-camera</small>
          </span>
        </div>
      </aside>

      <div className="mobile-nav">
        <NavItems {...props} mobile />
      </div>
    </>
  );
}
