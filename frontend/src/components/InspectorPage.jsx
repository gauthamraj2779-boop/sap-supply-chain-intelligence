import { useState, useEffect, useCallback } from 'react';

import TrajectoryPanel from './TrajectoryPanel';
import { runAgent, checkHealth, ApiError } from '../utils/api';
import { formatMoneyExact } from '../utils/format';

/**
 * Agent inspector — a standalone debugging surface at #/inspect.
 *
 * Not reachable from the console: no nav item, no link. It exists to show a run
 * in full — every tool call, its arguments, its raw result, its timing, the SAP
 * tables it read, which model chose it, and whether every figure in the final
 * answer traces back to something an engine computed.
 *
 * Density over polish, and nothing invented: when the backend has no agent
 * (no model configured) it returns 503 and this page reports that verbatim
 * rather than showing a simulated run.
 */

const EXAMPLES = [
  'Which customers are exposed to suppliers in Taiwan?',
  'Is MCU-32 sole sourced, and how much stock do we hold?',
  'Apex Microelectronics is delayed 21 days — what is our exposure and what can we do?',
  'Which production orders consume PWR-IC-7 at plant 1010, and who do they ship to?',
];

function Raw({ label, value, initiallyOpen = false }) {
  const [open, setOpen] = useState(initiallyOpen);
  return (
    <div className="insp-raw">
      <button className="traj-toggle" onClick={() => setOpen((v) => !v)}>
        {open ? '−' : '+'} {label}
      </button>
      {open && <pre className="traj-json">{JSON.stringify(value, null, 2)}</pre>}
    </div>
  );
}

/**
 * The agent is told to write plain text, and some providers emphasise anyway.
 * Render `**...**` as emphasis rather than leaving the markers on screen. The
 * byte-exact answer is still one toggle away under Raw response.
 */
function AnswerText({ text }) {
  const parts = String(text ?? '').split(/(\*\*[^*]+\*\*)/g);
  return (
    <p className="insp-answer">
      {parts.map((p, i) =>
        p.startsWith('**') && p.endsWith('**')
          ? <strong key={i}>{p.slice(2, -2)}</strong>
          : <span key={i}>{p}</span>,
      )}
    </p>
  );
}

function CrossCheck({ cross }) {
  if (!cross) {
    return (
      <p className="insp-note">
        No impact report in this run, so there were no computed figures to check
        the answer against.
      </p>
    );
  }
  const clean = cross.discrepancies.length === 0;
  return (
    <div className={`insp-xcheck ${clean ? 'clean' : 'dirty'}`}>
      <div className="insp-xcheck-head">
        <span className="insp-xcheck-verdict">
          {clean ? 'All stated figures trace to a computed value' : 'Unmatched figures found'}
        </span>
        <span className="insp-xcheck-stat">
          {cross.matched}/{cross.checked} matched · agreement{' '}
          {(cross.agreement * 100).toFixed(0)}%
        </span>
      </div>
      {cross.discrepancies.map((d, i) => (
        <div key={i} className="insp-discrepancy">
          <span className="insp-disc-num">
            stated {formatMoneyExact(d.stated)} · nearest computed{' '}
            {formatMoneyExact(d.nearest_computed)} · off by{' '}
            {(d.relative_error * 100).toFixed(1)}%
          </span>
          <span className="insp-disc-ctx">…{d.context}…</span>
        </div>
      ))}
      {cross.notes.map((n, i) => <p key={i} className="insp-note">{n}</p>)}
    </div>
  );
}

function ReportFacts({ report }) {
  const fe = report.financial_exposure;
  const rows = [
    ['Total financial exposure', formatMoneyExact(fe.total_financial_exposure)],
    ['PO stranded value', formatMoneyExact(fe.po_stranded_value)],
    ['Production halt cost', formatMoneyExact(fe.production_halt_cost)],
    ['Revenue at risk', formatMoneyExact(fe.revenue_at_risk)],
    ['Penalty exposure', formatMoneyExact(fe.penalty_exposure)],
    ['Components reconcile', String(fe.components_reconcile)],
    ['Confidence', `${Math.round(report.confidence.overall * 100)}%`],
    ['Hops failed', report.traversal.hops_failed.join(', ') || 'none'],
  ];
  return (
    <>
      <div className="insp-facts">
        {rows.map(([k, v]) => (
          <div key={k} className="insp-fact">
            <span className="insp-fact-k">{k}</span>
            <span className="insp-fact-v">{v}</span>
          </div>
        ))}
      </div>
      {/* The hop chain is one long value; a grid cell would wrap it to shreds. */}
      <div className="insp-hops">
        <span className="traj-meta-label">Hops completed</span>
        <div className="traj-tables">
          {report.traversal.hops_completed.map((h) => (
            <span key={h} className="traj-table">{h}</span>
          ))}
        </div>
      </div>
    </>
  );
}

export default function InspectorPage() {
  const [question, setQuestion] = useState(EXAMPLES[0]);
  const [result, setResult] = useState(null);
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(false);
  const [elapsed, setElapsed] = useState(0);
  const [health, setHealth] = useState(null);

  useEffect(() => {
    let live = true;
    checkHealth()
      .then((h) => live && setHealth(h))
      .catch(() => live && setHealth(null));
    return () => { live = false; };
  }, []);

  useEffect(() => {
    if (!loading) return undefined;
    const started = Date.now();
    const tick = setInterval(
      () => setElapsed(Math.floor((Date.now() - started) / 1000)), 250,
    );
    return () => clearInterval(tick);
  }, [loading]);

  const run = useCallback(async (q) => {
    const text = (q ?? '').trim();
    if (!text || text.length < 3) return;
    setLoading(true);
    setError(null);
    setResult(null);
    setElapsed(0);
    try {
      setResult(await runAgent(text));
    } catch (err) {
      setError(err instanceof ApiError ? err : new ApiError(err.message));
    } finally {
      setLoading(false);
    }
  }, []);

  const agentic = health?.capabilities?.agentic_reasoning;

  return (
    <div className="insp-page">
      <header className="insp-header">
        <div>
          <h1 className="insp-title">Agent inspector</h1>
          <p className="insp-sub">
            One question, every step. Tool calls, arguments, raw results, timings,
            SAP tables and the figure cross-check.
          </p>
        </div>
        <div className="insp-chips">
          <span className="insp-chip">
            {health?.llm?.provider ?? '—'} · {health?.llm?.model ?? 'no model'}
          </span>
          <span className="insp-chip">
            {health?.graph?.backend ?? '—'} graph · {health?.graph?.records ?? 0} records
          </span>
          <span className={`insp-chip ${agentic ? 'on' : 'off'}`}>
            {agentic === undefined
              ? 'backend unreachable'
              : agentic
                ? 'agent available'
                : 'agent unavailable'}
          </span>
        </div>
      </header>

      <div className="insp-query">
        <textarea
          className="insp-input"
          value={question}
          rows={2}
          spellCheck={false}
          onChange={(e) => setQuestion(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
              e.preventDefault();
              run(question);
            }
          }}
          placeholder="Ask the agent a supply-chain question…"
        />
        <button className="insp-run" onClick={() => run(question)} disabled={loading}>
          {loading ? `running… ${elapsed}s` : 'Run agent'}
        </button>
      </div>

      <div className="insp-examples">
        {EXAMPLES.map((ex) => (
          <button
            key={ex}
            className="insp-example"
            onClick={() => { setQuestion(ex); run(ex); }}
          >
            {ex}
          </button>
        ))}
      </div>

      {error && (
        <div className="insp-error">
          <span className="insp-error-title">
            {error.status === 503 ? 'No agent available (HTTP 503)' : 'Agent run failed'}
          </span>
          <p className="insp-error-msg">{error.message}</p>
          <p className="insp-note">
            Nothing is simulated here. With no model configured the endpoint refuses
            rather than inventing a trajectory; the deterministic report at
            POST /api/impact is unaffected.
          </p>
        </div>
      )}

      {loading && (
        <p className="insp-note">
          The agent is choosing and running tools. Each step is a real model call
          followed by a real query against the graph.
        </p>
      )}

      {result && (
        <div className="insp-results">
          <section className="insp-section">
            <h2 className="section-title">Answer</h2>
            <AnswerText text={result.answer} />
          </section>

          <section className="insp-section">
            <h2 className="section-title">Figure cross-check</h2>
            <p className="section-sub">
              Every monetary figure in the answer, matched against the set the
              deterministic engines produced. The computed values are authoritative.
            </p>
            <CrossCheck cross={result.cross_check} />
          </section>

          <section className="insp-section">
            <TrajectoryPanel trajectory={result.trajectory} />
          </section>

          <section className="insp-section">
            <h2 className="section-title">Impact report</h2>
            {result.report ? (
              <>
                <p className="section-sub">
                  Returned because the run called supplier_delay_impact. Identical to
                  what POST /api/impact serves for the same supplier and delay.
                </p>
                <ReportFacts report={result.report} />
                {result.report.warnings?.length > 0 && (
                  <ul className="insp-warnings">
                    {result.report.warnings.map((w, i) => <li key={i}>{w}</li>)}
                  </ul>
                )}
                <Raw label="raw ImpactReport JSON" value={result.report} />
              </>
            ) : (
              <p className="insp-note">
                This run never called supplier_delay_impact, so no report was
                produced and no financial figure was computed.
              </p>
            )}
          </section>

          <section className="insp-section">
            <h2 className="section-title">Raw response</h2>
            <Raw label="full /api/agent payload" value={result} />
          </section>
        </div>
      )}
    </div>
  );
}
