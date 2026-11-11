// Formatting helpers and shared colour tokens.

export const SERIES = { a: '#1592cc', b: '#d77522' }; // validated categorical pair (dark surface)

export const COMPOUND_COLORS = {
  SOFT: '#e8455a',
  MEDIUM: '#e7b416',
  HARD: '#c9ced6',
  INTERMEDIATE: '#3fb950',
  WET: '#2f81f7',
  UNKNOWN: '#5d6878',
};

export function compoundLabel(c) {
  if (!c || c === 'UNKNOWN') return 'Unknown';
  return c.charAt(0) + c.slice(1).toLowerCase();
}

export function fmtLap(s) {
  if (s === null || s === undefined || Number.isNaN(s)) return '—';
  const m = Math.floor(s / 60);
  const rest = s - m * 60;
  return m > 0 ? `${m}:${rest.toFixed(3).padStart(6, '0')}` : rest.toFixed(3);
}

export function fmtRaceTime(s) {
  if (s === null || s === undefined) return '—';
  const h = Math.floor(s / 3600);
  const m = Math.floor((s - h * 3600) / 60);
  const sec = s - h * 3600 - m * 60;
  return `${h}:${String(m).padStart(2, '0')}:${sec.toFixed(1).padStart(4, '0')}`;
}

export function fmtDelta(s, digits = 3, unit = 's') {
  if (s === null || s === undefined || Number.isNaN(s)) return '—';
  const sign = s > 0 ? '+' : s < 0 ? '−' : '±';
  return `${sign}${Math.abs(s).toFixed(digits)}${unit}`;
}

export function fmtPos(p) {
  return p ? `P${p}` : '—';
}

export function deltaClass(s, lowerIsBetter = true) {
  if (s === null || s === undefined || Math.abs(s) < 1e-9) return 'neutral';
  return (s < 0) === lowerIsBetter ? 'good' : 'bad';
}

export function sessionLabel(meta) {
  if (!meta) return '';
  const season = meta.season === 'demo' ? '' : `${meta.season} `;
  return `${season}${meta.event_name} · ${meta.session_name}`;
}
