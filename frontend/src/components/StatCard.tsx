import type { ReactNode } from "react";

interface Props {
  label: string;
  value: string | number;
  tone?: "default" | "danger" | "warning" | "muted";
  detail?: string;
  icon?: ReactNode;
  onClick?: () => void;
}

export function StatCard({ label, value, tone = "default", detail, icon, onClick }: Props) {
  const content = (
    <>
      <div className="stat-card__top">
        <div className="stat-card__label">{label}</div>
        {icon && <span className="stat-card__icon">{icon}</span>}
      </div>
      <div className="stat-card__value">{value}</div>
      {detail && <div className="stat-card__detail">{detail}</div>}
    </>
  );

  return onClick ? (
    <button type="button" className={`stat-card stat-card--${tone} stat-card--clickable`} onClick={onClick}>
      {content}
    </button>
  ) : (
    <div className={`stat-card stat-card--${tone}`}>{content}</div>
  );
}
