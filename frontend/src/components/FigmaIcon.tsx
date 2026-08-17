import area from "../assets/figma/area.svg";
import arrow from "../assets/figma/arrow.svg";
import cameraNav from "../assets/figma/camera-nav.svg";
import cctvFooter from "../assets/figma/cctv-footer.svg";
import chatAi from "../assets/figma/chat-ai.svg";
import connected from "../assets/figma/connected.svg";
import emergency from "../assets/figma/emergency.svg";
import emergencyArea from "../assets/figma/emergency/area.svg";
import emergencyArrow from "../assets/figma/emergency/arrow.svg";
import emergencyChatAi from "../assets/figma/emergency/chat-ai.svg";
import emergencyPeople1 from "../assets/figma/emergency/people-1.svg";
import emergencyPeople2 from "../assets/figma/emergency/people-2.svg";
import emergencyPeople3 from "../assets/figma/emergency/people-3.svg";
import emergencyPpe from "../assets/figma/emergency/ppe.svg";
import emergencySettings from "../assets/figma/emergency/settings.svg";
import people1 from "../assets/figma/people-1.svg";
import people2 from "../assets/figma/people-2.svg";
import people3 from "../assets/figma/people-3.svg";
import ppe from "../assets/figma/ppe.svg";
import ppeNav from "../assets/figma/ppe-nav.svg";
import safetyNav from "../assets/figma/safety-nav.svg";
import settings from "../assets/figma/settings.svg";
import summaryAlarm from "../assets/figma/summary-alarm.svg";
import summaryPpe from "../assets/figma/summary-ppe.svg";
import summaryReport1 from "../assets/figma/summary-report-1.svg";
import summaryReport2 from "../assets/figma/summary-report-2.svg";
import summaryZoom from "../assets/figma/summary-zoom.svg";
import timelineNav from "../assets/figma/timeline-nav.svg";

export type FigmaIconName =
  | "area" | "arrow" | "cameraNav" | "cctvFooter" | "chatAi" | "connected"
  | "emergency" | "people" | "ppe" | "ppeNav" | "safetyNav" | "settings"
  | "summaryAlarm" | "summaryPpe" | "summaryReport" | "summaryZoom" | "timelineNav";

const SIMPLE_ICONS: Partial<Record<FigmaIconName, string>> = {
  area,
  arrow,
  cameraNav,
  cctvFooter,
  chatAi,
  connected,
  emergency,
  ppe,
  ppeNav,
  safetyNav,
  settings,
  summaryAlarm,
  summaryPpe,
  summaryZoom,
  timelineNav,
};

const EMERGENCY_ICONS: Partial<Record<FigmaIconName, string>> = {
  area: emergencyArea,
  arrow: emergencyArrow,
  chatAi: emergencyChatAi,
  ppe: emergencyPpe,
  settings: emergencySettings,
  summaryPpe: emergencyPpe,
};

const ICON_INSETS: Partial<Record<FigmaIconName, string>> = {
  area: "12.5%",
  arrow: "25% 33.29% 24.96% 37.5%",
  cameraNav: "8.33%",
  cctvFooter: "8.33% 8.63% 8.33% 8.33%",
  chatAi: "4.16% 0 6.25% 8.33%",
  connected: "12.5% 4.17%",
  emergency: "12.5% 4.17% 16.67%",
  ppe: "16.67% 8.19% 16.67% 8.59%",
  ppeNav: "16.67% 8.19% 16.67% 8.59%",
  safetyNav: "8.62% 12.5% 8.58%",
  settings: "5.08% 6.25%",
  summaryAlarm: "10.42% 10.42% 14.58% 12.04%",
  summaryPpe: "16.67% 8.19% 16.67% 8.59%",
  summaryZoom: "8.33%",
  timelineNav: "8.33% 0 8.33% 4.17%",
};

interface Props {
  name: FigmaIconName;
  size?: number;
  className?: string;
  decorative?: boolean;
}

interface AssetProps {
  normal: string;
  emergency?: string;
  inset: string;
}

function IconAsset({ normal, emergency: emergencySource, inset }: AssetProps) {
  return (
    <>
      <img className="figma-icon__asset figma-icon__asset--normal" src={normal} alt="" style={{ inset }} />
      {emergencySource && <img className="figma-icon__asset figma-icon__asset--emergency" src={emergencySource} alt="" style={{ inset }} />}
    </>
  );
}

export function FigmaIcon({ name, size = 24, className = "", decorative = true }: Props) {
  const label = decorative ? undefined : name;
  const accessibilityProps = { role: decorative ? undefined : "img", "aria-label": label, "aria-hidden": decorative || undefined };

  if (name === "people") {
    return (
      <span className={`figma-icon figma-icon--dual ${className}`} style={{ width: size, height: size }} {...accessibilityProps}>
        <IconAsset normal={people1} emergency={emergencyPeople1} inset="54.71% 4.17% 16.67% 69.46%" />
        <IconAsset normal={people2} emergency={emergencyPeople2} inset="16.67% 45.83% 50% 20.83%" />
        <IconAsset normal={people3} emergency={emergencyPeople3} inset="16.67% 20.83% 16.67% 4.17%" />
      </span>
    );
  }

  if (name === "summaryReport") {
    return (
      <span className={`figma-icon ${className}`} style={{ width: size, height: size }} {...accessibilityProps}>
        <img className="figma-icon__asset" src={summaryReport1} alt="" style={{ inset: "40.63% 31.25% 21.88%" }} />
        <img className="figma-icon__asset" src={summaryReport2} alt="" style={{ inset: "6.25% 15.63%" }} />
      </span>
    );
  }

  const emergencySource = EMERGENCY_ICONS[name];
  return (
    <span className={`figma-icon ${emergencySource ? "figma-icon--dual" : ""} ${className}`} style={{ width: size, height: size }} {...accessibilityProps}>
      <IconAsset normal={SIMPLE_ICONS[name]!} emergency={emergencySource} inset={ICON_INSETS[name] ?? "0"} />
    </span>
  );
}
