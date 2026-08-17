import type { CSSProperties } from "react";
import area from "../assets/figma/area.svg?raw";
import arrow from "../assets/figma/arrow.svg?raw";
import cameraNav from "../assets/figma/camera-nav.svg?raw";
import cctvFooter from "../assets/figma/cctv-footer.svg?raw";
import chatAi from "../assets/figma/chat-ai.svg?raw";
import connected from "../assets/figma/connected.svg?raw";
import emergency from "../assets/figma/emergency.svg?raw";
import people1 from "../assets/figma/people-1.svg?raw";
import people2 from "../assets/figma/people-2.svg?raw";
import people3 from "../assets/figma/people-3.svg?raw";
import ppe from "../assets/figma/ppe.svg?raw";
import ppeNav from "../assets/figma/ppe-nav.svg?raw";
import safetyNav from "../assets/figma/safety-nav.svg?raw";
import settings from "../assets/figma/settings.svg?raw";
import summaryAlarm from "../assets/figma/summary-alarm.svg?raw";
import summaryPpe from "../assets/figma/summary-ppe.svg?raw";
import summaryReport1 from "../assets/figma/summary-report-1.svg?raw";
import summaryReport2 from "../assets/figma/summary-report-2.svg?raw";
import summaryZoom from "../assets/figma/summary-zoom.svg?raw";
import timelineNav from "../assets/figma/timeline-nav.svg?raw";

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

function IconGlyph({ source, inset = 0 }: { source: string; inset?: CSSProperties["inset"] }) {
  const colorableSource = source.replace(/fill="#[0-9a-f]{6}"/gi, 'fill="currentColor"');
  return (
    <span
      className="figma-icon__glyph"
      style={{ inset }}
      dangerouslySetInnerHTML={{ __html: colorableSource }}
    />
  );
}

export function FigmaIcon({ name, size = 24, className = "", decorative = true }: Props) {
  const label = decorative ? undefined : name;
  if (name === "people") {
    return (
      <span className={`figma-icon ${className}`} style={{ width: size, height: size }} role={decorative ? undefined : "img"} aria-label={label} aria-hidden={decorative || undefined}>
        <IconGlyph source={people1} inset="54.71% 4.17% 16.67% 69.46%" />
        <IconGlyph source={people2} inset="16.67% 45.83% 50% 20.83%" />
        <IconGlyph source={people3} inset="16.67% 20.83% 16.67% 4.17%" />
      </span>
    );
  }
  if (name === "summaryReport") {
    return (
      <span className={`figma-icon ${className}`} style={{ width: size, height: size }} role={decorative ? undefined : "img"} aria-label={label} aria-hidden={decorative || undefined}>
        <IconGlyph source={summaryReport1} inset="40.63% 31.25% 21.88%" />
        <IconGlyph source={summaryReport2} inset="6.25% 15.63%" />
      </span>
    );
  }
  return <span className={`figma-icon ${className}`} style={{ width: size, height: size }} role={decorative ? undefined : "img"} aria-label={label} aria-hidden={decorative || undefined}><IconGlyph source={SIMPLE_ICONS[name]!} inset={ICON_INSETS[name] ?? 0} /></span>;
}
