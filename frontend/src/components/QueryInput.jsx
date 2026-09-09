import { useState, useRef } from 'react';
import { EXAMPLE_QUERIES } from '../utils/api';

export default function QueryInput({ onSubmit, loading }) {
  const [query, setQuery] = useState('');
  const inputRef = useRef(null);

  const submit = (q) => {
    const val = (q || query).trim();
    if (!val || loading) return;
    setQuery(val);
    onSubmit(val);
  };

  const handleKey = (e) => {
    if (e.key === 'Enter') submit();
  };

  const recentQueries = [
    'Apex Microelectronics delayed 14 days',
    'What if Plant 1010 loses power for 7 days?',
    'Nova Components lead time increases to 30 days',
  ];

  return (
    <div className="query-zone">
      <div className="query-row">
        <input
          ref={inputRef}
          className="query-field"
          type="text"
          value={query}
          onChange={e => setQuery(e.target.value)}
          onKeyDown={handleKey}
          placeholder="Supplier Apex is delayed 14 days — what's our exposure?"
          disabled={loading}
          id="query-input"
        />
        <button
          className="query-run-btn"
          onClick={() => submit()}
          disabled={!query.trim() || loading}
        >
          {loading && <span className="query-spinner-sm" />}
          {loading ? 'Analysing…' : 'Run analysis'}
        </button>
      </div>
      <div className="recent-chips">
        <span className="recent-label">Recent queries</span>
        {recentQueries.map((q, i) => (
          <button
            key={i}
            className="query-chip"
            onClick={() => { setQuery(EXAMPLE_QUERIES[i] || q); submit(EXAMPLE_QUERIES[i] || q); }}
            disabled={loading}
          >
            {q}
          </button>
        ))}
      </div>
    </div>
  );
}
