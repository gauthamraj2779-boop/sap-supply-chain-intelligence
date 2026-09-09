import { useState, useEffect, useRef } from 'react';
import { getExampleQueries, getSuppliers } from '../utils/api';

/**
 * Query console. Example questions and supplier names are fetched from the
 * backend so the suggestions always name suppliers that actually exist in the
 * loaded graph.
 */
export default function QueryInput({ onSubmit, loading, health }) {
  const [query, setQuery] = useState('');
  const [examples, setExamples] = useState([]);
  const [suppliers, setSuppliers] = useState([]);
  const [showSuggest, setShowSuggest] = useState(false);
  const inputRef = useRef(null);

  useEffect(() => {
    let live = true;
    getExampleQueries()
      .then((d) => live && setExamples(d.examples ?? []))
      .catch(() => live && setExamples([]));
    getSuppliers()
      .then((d) => live && setSuppliers(d ?? []))
      .catch(() => live && setSuppliers([]));
    return () => { live = false; };
  }, [health?.graph?.records]);

  const submit = (q) => {
    const val = (q ?? query).trim();
    if (!val || loading) return;
    setQuery(val);
    setShowSuggest(false);
    onSubmit(val);
  };

  const matches = query.trim().length >= 2
    ? suppliers.filter((s) =>
        s.name?.toLowerCase().includes(query.toLowerCase().trim()) ||
        s.lifnr?.includes(query.trim()),
      ).slice(0, 5)
    : [];

  return (
    <div className="query-zone">
      <div className="query-row">
        <input
          ref={inputRef}
          className="query-field"
          type="text"
          value={query}
          onChange={(e) => { setQuery(e.target.value); setShowSuggest(true); }}
          onKeyDown={(e) => {
            if (e.key === 'Enter') submit();
            if (e.key === 'Escape') setShowSuggest(false);
          }}
          onBlur={() => setTimeout(() => setShowSuggest(false), 150)}
          placeholder={
            suppliers.length
              ? `Supplier ${suppliers[0].name} is delayed 14 days — what's our exposure?`
              : 'Ask about a supplier delay…'
          }
          disabled={loading}
          id="query-input"
          autoComplete="off"
        />
        <button
          className="query-run-btn"
          onClick={() => submit()}
          disabled={!query.trim() || loading}
        >
          {loading && <span className="query-spinner-sm" />}
          {loading ? 'Analysing…' : 'Run analysis'}
        </button>

        {showSuggest && matches.length > 0 && (
          <div className="query-suggest">
            {matches.map((s) => (
              <button
                key={s.lifnr}
                className="qs-item"
                onMouseDown={() => submit(`${s.name} is delayed by 14 days`)}
              >
                <span className="qs-name">{s.name}</span>
                <span className="qs-meta">
                  {s.lifnr}
                  {s.country ? ` · ${s.country}` : ''}
                  {typeof s.risk_score === 'number'
                    ? ` · risk ${s.risk_score.toFixed(2)}`
                    : ''}
                </span>
              </button>
            ))}
          </div>
        )}
      </div>

      {examples.length > 0 && (
        <div className="recent-chips">
          <span className="recent-label">Example queries</span>
          {examples.map((q, i) => (
            <button
              key={i}
              className="query-chip"
              onClick={() => submit(q)}
              disabled={loading}
              title={q}
            >
              {q.length > 62 ? `${q.slice(0, 62)}…` : q}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
