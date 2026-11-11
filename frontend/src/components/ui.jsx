import { Link } from 'react-router-dom';
import { COMPOUND_COLORS, compoundLabel } from '../lib/format';

export function Spinner() {
  return <span className="spinner" aria-hidden="true" />;
}

export function Banner({ tone = 'info', title, children, icon, actions }) {
  const icons = { info: 'ℹ', warn: '⚠', error: '✕', success: '✓' };
  return (
    <div className={`banner ${tone}`} role={tone === 'error' ? 'alert' : 'status'}>
      <span className="icon" aria-hidden="true">{icon || icons[tone]}</span>
      <div className="body">
        {title && <strong>{title}</strong>}
        {children}
      </div>
      {actions && <div className="btn-row">{actions}</div>}
    </div>
  );
}

/** Readable error: what is unavailable, what still works, what to do next. */
export function ErrorPanel({ error, onRetry, actions, title }) {
  if (!error) return null;
  return (
    <Banner
      tone="error"
      title={title || error.message}
      actions={
        <>
          {onRetry && (
            <button className="btn small" onClick={onRetry}>
              Retry
            </button>
          )}
          {actions}
        </>
      }
    >
      <ul>
        {title && <li>{error.message}</li>}
        {error.stillAvailable && <li><b>Still available:</b> {error.stillAvailable}</li>}
        {error.nextAction && <li><b>Next step:</b> {error.nextAction}</li>}
      </ul>
    </Banner>
  );
}

export function EmptyState({ title, children, actions }) {
  return (
    <div className="empty">
      <strong>{title}</strong>
      <div>{children}</div>
      {actions && <div className="btn-row">{actions}</div>}
    </div>
  );
}

export function LoadingPanel({ label = 'Loading…', detail }) {
  return (
    <div className="loading-panel" role="status" aria-live="polite">
      <Spinner />
      <div style={{ color: '#fff', fontWeight: 700 }}>{label}</div>
      {detail && <div className="sub">{detail}</div>}
    </div>
  );
}

export function Kpi({ label, value, delta, tone = 'neutral', title }) {
  return (
    <div className="card kpi" title={title}>
      <div className="label">{label}</div>
      <div className="value">{value}</div>
      {delta !== undefined && <div className={`sub ${tone}`}>{delta}</div>}
    </div>
  );
}

export function CompoundPill({ compound }) {
  const unknown = !compound || compound === 'UNKNOWN';
  return (
    <span
      className={`compound-pill ${unknown ? 'unknown' : ''}`}
      style={unknown ? undefined : { background: COMPOUND_COLORS[compound] }}
    >
      {compoundLabel(compound).toUpperCase()}
    </span>
  );
}

/** Horizontal stint timeline. stints: [{stint, compound, start_lap, end_lap, length}] */
export function StintBar({ stints, totalLaps, label }) {
  if (!stints?.length) return <div className="sub">No stint data.</div>;
  const total = totalLaps || stints[stints.length - 1].end_lap;
  return (
    <div>
      {label && <div className="sub" style={{ marginBottom: 2 }}>{label}</div>}
      <div className="stint-bar" role="img" aria-label={stints.map((s) => `${compoundLabel(s.compound)} laps ${s.start_lap}-${s.end_lap}`).join(', ')}>
        {stints.map((s) => {
          const unknown = !s.compound || s.compound === 'UNKNOWN';
          const short = unknown ? '?' : s.compound[0];
          return (
            <div
              key={s.stint}
              className={`stint-seg ${unknown ? 'unknown' : ''}`}
              style={{ flex: s.length, background: unknown ? undefined : COMPOUND_COLORS[s.compound] }}
              title={`Stint ${s.stint}: ${compoundLabel(s.compound)} · laps ${s.start_lap}–${s.end_lap} (${s.length} laps)`}
            >
              {s.length >= 4 ? `${short} · ${s.length}` : short}
            </div>
          );
        })}
      </div>
      <div className="stint-axis">
        <span>Lap 1</span>
        {stints.slice(0, -1).map((s) => (
          <span key={s.stint}>Pit L{s.end_lap}</span>
        ))}
        <span>Lap {total}</span>
      </div>
    </div>
  );
}

export function DriverPill({ code, color }) {
  return (
    <span className="driver-pill">
      <i className="swatch" style={{ background: color }} />
      {code}
    </span>
  );
}

export function SourceBadge({ meta }) {
  if (!meta) return null;
  if (meta.is_demo) return <span className="badge demo" title={meta.source_label}><span className="status-dot" />Demo data</span>;
  return <span className="badge real" title={meta.source_label}><span className="status-dot" />Historical data</span>;
}

export function ChartTooltip({ active, payload, label, labelFormatter, valueFormatter }) {
  if (!active || !payload?.length) return null;
  return (
    <div className="tooltip">
      <div className="t-title">{labelFormatter ? labelFormatter(label) : label}</div>
      {payload
        .filter((p) => p.value !== null && p.value !== undefined)
        .map((p) => (
          <div className="t-row" key={p.dataKey}>
            <i className="swatch" style={{ background: p.color || p.stroke }} />
            <span>{p.name}</span>
            <b style={{ marginLeft: 'auto', paddingLeft: 12 }}>{valueFormatter ? valueFormatter(p.value, p) : p.value}</b>
          </div>
        ))}
    </div>
  );
}

export function NextSteps({ items }) {
  return (
    <div className="btn-row">
      {items.map((it) => (
        <Link key={it.to} to={it.to} className={`btn small ${it.primary ? 'primary' : ''}`}>
          {it.label} →
        </Link>
      ))}
    </div>
  );
}

export function Toast({ toast }) {
  if (!toast) return null;
  return (
    <div className={`toast ${toast.tone}`} role="status" aria-live="polite" key={toast.id}>
      {toast.message}
    </div>
  );
}
