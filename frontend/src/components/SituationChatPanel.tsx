import { useEffect, useRef, useState } from "react";
import { frameUrl, sendChatMessage } from "../api";
import type { ChatMessage } from "../types";

export function SituationChatPanel() {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [lightboxSrc, setLightboxSrc] = useState<string | null>(null);
  const listRef = useRef<HTMLDivElement>(null);

  const ask = async (question: string) => {
    const history = [...messages, { role: "user" as const, content: question }];
    setMessages(history);
    setLoading(true);
    setError(null);
    try {
      const res = await sendChatMessage(history);
      setMessages([...history, { role: "assistant", content: res.reply, frame_path: res.frame_path }]);
    } catch {
      setError("답변을 받지 못했습니다. 다시 시도해주세요.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    listRef.current?.scrollTo({ top: listRef.current.scrollHeight });
  }, [messages, loading]);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    const question = input.trim();
    if (!question || loading) return;
    setInput("");
    void ask(question);
  };

  return (
    <div className="chat-panel">
      <div className="chat-panel__header">
        <span>구조 브리핑 챗봇</span>
        <span className="chat-panel__disclaimer">AI가 자동 생성한 추정 정보 — 관리자 판단을 대체하지 않음</span>
      </div>
      <div className="chat-panel__list" ref={listRef}>
        {messages.length === 0 && !loading && (
          <p className="empty-hint">궁금한 걸 물어보세요 — 예: "지금 상황 어때?", "74초쯤 무슨 일이 있었어?"</p>
        )}
        {messages.map((m, i) => (
          <div key={i} className={`chat-bubble chat-bubble--${m.role}`}>
            <p>{m.content}</p>
            {m.frame_path && (
              <button className="chat-bubble__thumb" onClick={() => setLightboxSrc(frameUrl(m.frame_path!))}>
                <img src={frameUrl(m.frame_path)} alt="참고 프레임" />
              </button>
            )}
          </div>
        ))}
        {loading && (
          <div className="chat-bubble chat-bubble--assistant chat-bubble--loading">
            <p>답변 작성 중...</p>
          </div>
        )}
      </div>
      {error && <p className="chat-panel__error">{error}</p>}
      <form className="chat-panel__form" onSubmit={handleSubmit}>
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="예: 74초쯤 무슨 일이 있었어?"
          disabled={loading}
        />
        <button type="submit" disabled={loading || !input.trim()}>
          전송
        </button>
      </form>

      {lightboxSrc && (
        <div className="modal-backdrop" onClick={() => setLightboxSrc(null)}>
          <img className="chat-panel__lightbox-image" src={lightboxSrc} alt="확대된 참고 프레임" onClick={(e) => e.stopPropagation()} />
        </div>
      )}
    </div>
  );
}
