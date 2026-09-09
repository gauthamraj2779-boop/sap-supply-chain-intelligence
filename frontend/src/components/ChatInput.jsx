import React, { useState, useRef, useEffect } from 'react';
import { ArrowUp, Sparkles, Clock, AlertCircle, CornerDownLeft, StopCircle } from 'lucide-react';

export default function ChatInput({
  onSubmit,
  isLoading,
  onCancel,
  initialQuery = '',
}) {
  const [text, setText] = useState(initialQuery);
  const textareaRef = useRef(null);

  useEffect(() => {
    if (initialQuery) {
      setText(initialQuery);
      if (textareaRef.current) {
        textareaRef.current.focus();
      }
    }
  }, [initialQuery]);

  // Auto-resize textarea height based on content
  useEffect(() => {
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto';
      textareaRef.current.style.height = `${Math.min(textareaRef.current.scrollHeight, 180)}px`;
    }
  }, [text]);

  const handleSubmit = (e) => {
    if (e) e.preventDefault();
    if (!text.trim() || isLoading) return;
    onSubmit(text.trim());
  };

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSubmit();
    }
  };

  const addDelayModifier = (days) => {
    if (!text.trim()) {
      setText(`Apex Microelectronics delayed by ${days} days. What is our risk?`);
    } else if (text.match(/delayed by \d+ days/i)) {
      setText(text.replace(/delayed by \d+ days/i, `delayed by ${days} days`));
    } else {
      setText(`${text.trim()} (simulating +${days} days delay)`);
    }
  };

  return (
    <div className="chat-input-wrapper">
      <div className="chat-input-container">
        {/* Quick parameter pills */}
        <div className="input-pills-bar">
          <span className="pills-label">
            <Clock size={12} />
            <span>Simulate Delay:</span>
          </span>
          <button type="button" className="delay-pill" onClick={() => addDelayModifier(7)}>
            +7 Days
          </button>
          <button type="button" className="delay-pill active-pill" onClick={() => addDelayModifier(14)}>
            +14 Days (Flagship)
          </button>
          <button type="button" className="delay-pill" onClick={() => addDelayModifier(21)}>
            +21 Days
          </button>
          <button type="button" className="delay-pill" onClick={() => addDelayModifier(30)}>
            +30 Days (Crisis)
          </button>
        </div>

        <form onSubmit={handleSubmit} className="input-form">
          <textarea
            ref={textareaRef}
            rows={1}
            value={text}
            onChange={(e) => setText(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Ask anything about supplier delays, financial risk, or preventive avoidance..."
            className="chat-textarea"
            disabled={isLoading}
          />

          <div className="input-actions-row">
            <div className="input-left-hints">
              <span className="input-hint-badge">
                <Sparkles size={11} className="text-violet" />
                <span>Deterministic Math + Azure LLM</span>
              </span>
            </div>

            {isLoading ? (
              <button
                type="button"
                className="submit-circle-btn stop-btn"
                onClick={onCancel}
                title="Stop generation"
              >
                <StopCircle size={18} />
              </button>
            ) : (
              <button
                type="submit"
                disabled={!text.trim()}
                className={`submit-circle-btn ${text.trim() ? 'ready' : 'disabled'}`}
                title="Send query"
              >
                <ArrowUp size={18} />
              </button>
            )}
          </div>
        </form>
      </div>

      <div className="chat-disclaimer">
        <span>
          Outputs are backed by SAP DDIC table lineage &amp; W3C SHACL constraints. Calculations are deterministic.
        </span>
      </div>
    </div>
  );
}
