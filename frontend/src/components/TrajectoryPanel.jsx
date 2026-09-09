import { useState } from 'react';

/**
 * The agent's trajectory, step by step.
 *
 * Every row here is one tool call that actually ran: the reason the model gave
 * before making it, the arguments as dispatched, the SAP tables the handler
 * reports having read, how long it took, and the raw result that was fed back
 * into the model's context. Nothing is reconstructed or summarised on this side
 * — if the backend sends no steps, this panel shows none.
 */

const STOP_REASON = {
  answered: 'The model concluded on its own.',
  step_cap: 'Step budget exhausted — the model was made to answer with what it had.',
  model_unreachable: 'The model stopped responding mid-run.',
  no_tool_progress: 'The model returned no tool call and no answer.',
};

function Json({ value }) {
  return <pre className="traj-json">{JSON.stringify(value, null, 2)}</pre>;
}

function Step({ step }) {
  const [open, setOpen] = useState(false);
  const args = Object.entries(step.args ?? {});

  return (
    <div className={`traj-step ${step.ok ? '' : 'failed'}`}>
      <div className="traj-step-head">
        <span className="traj-step-num">{String(step.step).padStart(2, '0')}</span>
        <span className="traj-tool">{step.tool}</span>
        <span className="traj-dur">{step.duration_ms} ms</span>
        {!step.ok && <span className="traj-flag">refused</span>}
      </div>

      {step.thought && <p className="traj-thought">{step.thought}</p>}

      <div className="traj-args">
        {args.length === 0 ? (
          <span className="traj-arg-empty">no arguments</span>
        ) : (
          args.map(([k, v]) => (
            <span key={k} className="traj-arg">
              <span className="traj-arg-k">{k}</span>
              <span className="traj-arg-v">
                {typeof v === 'object' ? JSON.stringify(v) : String(v)}
              </span>
            </span>
          ))
        )}
      </div>

      <div className="traj-result">{step.result_summary}</div>

      <div className="traj-step-foot">
        <div className="traj-tables">
          {step.sap_tables_touched?.length > 0 ? (
            step.sap_tables_touched.map((t) => (
              <span key={t} className="traj-table">{t}</span>
            ))
          ) : (
            <span className="traj-arg-empty">no SAP records read</span>
          )}
        </div>
        <button className="traj-toggle" onClick={() => setOpen((v) => !v)}>
          {open ? '− hide' : '+ show'} raw result
        </button>
      </div>

      {open && <Json value={step.result} />}
    </div>
  );
}

export default function TrajectoryPanel({ trajectory }) {
  if (!trajectory) return null;

  const steps = trajectory.steps ?? [];
  const tables = trajectory.sap_tables_touched ?? [];

  return (
    <div className="traj-panel">
      <div className="section-head">
        <h2 className="section-title">Agent trajectory</h2>
        <p className="section-sub">
          Each step is one real tool call. The reason is the model's own, written
          before the call; the SAP tables are reported by the handler that ran, not
          claimed by the model.
        </p>
      </div>

      <div className="traj-meta">
        <div className="traj-meta-item">
          <span className="traj-meta-label">Steps</span>
          <span className="traj-meta-value">
            {trajectory.step_count} of 8
          </span>
        </div>
        <div className="traj-meta-item">
          <span className="traj-meta-label">Wall clock</span>
          <span className="traj-meta-value">
            {(trajectory.total_duration_ms / 1000).toFixed(2)} s
          </span>
        </div>
        <div className="traj-meta-item">
          <span className="traj-meta-label">Stopped</span>
          <span className="traj-meta-value">{trajectory.stopped_because}</span>
        </div>
        <div className="traj-meta-item">
          <span className="traj-meta-label">Model</span>
          <span className="traj-meta-value">
            {trajectory.provider}:{trajectory.model ?? '—'}
          </span>
        </div>
      </div>

      <p className="traj-stop-note">
        {STOP_REASON[trajectory.stopped_because] ?? trajectory.stopped_because}
      </p>

      {tables.length > 0 && (
        <div className="traj-tables-all">
          <span className="traj-meta-label">SAP tables read across the run</span>
          <div className="traj-tables">
            {tables.map((t) => <span key={t} className="traj-table">{t}</span>)}
          </div>
        </div>
      )}

      {steps.length === 0 ? (
        <p className="traj-empty">
          No tool was called. The model answered — or declined to — directly from
          the question.
        </p>
      ) : (
        <div className="traj-steps">
          {steps.map((s) => <Step key={s.step} step={s} />)}
        </div>
      )}
    </div>
  );
}
