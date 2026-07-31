import type { EventFeedEntry } from "../types";

export function EventFeed({ events }: { events: EventFeedEntry[] }) {
  const ordered = [...events].reverse();
  return (
    <div className="event-feed">
      <h3>최근 이벤트</h3>
      {ordered.length === 0 && <div className="event-feed__empty">아직 이벤트가 없습니다.</div>}
      <ul>
        {ordered.map((e, i) => (
          <li key={i}>
            <span className="event-feed__time">{new Date(e.at).toLocaleTimeString("ko-KR")}</span>
            <span>{e.text}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}
