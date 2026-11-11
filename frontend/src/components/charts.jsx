import {
  Area,
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  ComposedChart,
  Line,
  LineChart,
  ReferenceArea,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import { COMPOUND_COLORS, SERIES, compoundLabel, fmtDelta, fmtLap } from '../lib/format';
import { ChartTooltip } from './ui';

const GRID = '#232d3c';
const AXIS = '#3a4659';
const axisProps = { stroke: AXIS, tickLine: false, axisLine: { stroke: AXIS }, minTickGap: 18 };
const shortLap = (v) => {
  const m = Math.floor(v / 60);
  const s = (v - m * 60).toFixed(1).padStart(4, '0');
  return m ? `${m}:${s}` : s;
};

function lapDomain(rows, keys) {
  const vals = [];
  rows.forEach((r) => keys.forEach((k) => r[`${k}_clean`] && r[k] != null && vals.push(r[k])));
  if (!vals.length) return ['auto', 'auto'];
  vals.sort((a, b) => a - b);
  const lo = vals[0];
  const hi = vals[Math.floor(vals.length * 0.97)] ?? vals[vals.length - 1];
  return [Math.floor((lo - 0.4) * 2) / 2, Math.ceil((hi + 0.8) * 2) / 2];
}

/** Lap-time trend for one or two drivers, with pit laps marked. */
export function LapTimeChart({ rows, a, b, height = 300, colorA = SERIES.a }) {
  const keys = [a, b].filter(Boolean);
  const domain = lapDomain(rows, keys);
  const pitsA = rows.filter((r) => r[`${a}_pit`]).map((r) => r.lap);
  const pitsB = b ? rows.filter((r) => r[`${b}_pit`]).map((r) => r.lap) : [];
  return (
    <div className="chart" style={{ height }}>
      <ResponsiveContainer>
        <LineChart data={rows} margin={{ top: 18, right: 16, bottom: 18, left: 4 }}>
          <CartesianGrid stroke={GRID} vertical={false} />
          <XAxis dataKey="lap" {...axisProps} label={{ value: 'Lap', position: 'insideBottom', offset: -8 }} />
          <YAxis {...axisProps} domain={domain} allowDataOverflow width={52} tickFormatter={shortLap} />
          <Tooltip
            content={<ChartTooltip labelFormatter={(l) => `Lap ${l}`} valueFormatter={(v) => fmtLap(v)} />}
            cursor={{ stroke: '#5d6878', strokeDasharray: '3 3' }}
          />
          {pitsA.map((l) => (
            <ReferenceLine key={`pa${l}`} x={l} stroke={colorA} strokeDasharray="4 4" strokeOpacity={0.7}
              label={{ value: `${a} pit`, position: 'top', fill: '#9aa6b7', fontSize: 10 }} />
          ))}
          {pitsB.map((l) => (
            <ReferenceLine key={`pb${l}`} x={l} stroke={SERIES.b} strokeDasharray="4 4" strokeOpacity={0.7}
              label={{ value: `${b} pit`, position: 'insideTopRight', fill: '#9aa6b7', fontSize: 10 }} />
          ))}
          <Line type="linear" dataKey={a} name={a} stroke={colorA} strokeWidth={2} dot={false} connectNulls={false} isAnimationActive={false} />
          {b && <Line type="linear" dataKey={b} name={b} stroke={SERIES.b} strokeWidth={2} dot={false} connectNulls={false} isAnimationActive={false} />}
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}

/** Cumulative race gap: positive = Driver A behind Driver B. */
export function GapChart({ series, a, b, height = 300 }) {
  const data = series.map((g) => ({ lap: g.lap, gap: g.gap_s }));
  return (
    <div className="chart" style={{ height }}>
      <ResponsiveContainer>
        <ComposedChart data={data} margin={{ top: 12, right: 16, bottom: 18, left: 4 }}>
          <CartesianGrid stroke={GRID} vertical={false} />
          <XAxis dataKey="lap" {...axisProps} label={{ value: 'Lap', position: 'insideBottom', offset: -8 }} />
          <YAxis {...axisProps} width={58} tickFormatter={(v) => `${v > 0 ? '+' : ''}${v.toFixed(0)}s`} />
          <ReferenceLine y={0} stroke="#7f8da0" />
          <Tooltip
            content={<ChartTooltip labelFormatter={(l) => `After lap ${l}`} valueFormatter={(v) => `${a} ${v > 0 ? 'behind' : 'ahead'} by ${Math.abs(v).toFixed(2)}s`} />}
          />
          <Area type="linear" dataKey="gap" name={`Gap ${a} vs ${b}`} stroke={SERIES.a} fill={SERIES.a} fillOpacity={0.12} strokeWidth={2} isAnimationActive={false} />
        </ComposedChart>
      </ResponsiveContainer>
    </div>
  );
}

const CHANNEL_META = {
  speed: { label: 'Speed', unit: 'km/h', fmt: (v) => `${v.toFixed(0)} km/h` },
  throttle: { label: 'Throttle', unit: '%', fmt: (v) => `${v.toFixed(0)}%`, domain: [0, 100] },
  brake: { label: 'Brake', unit: 'on/off', fmt: (v) => (v > 50 ? 'On' : 'Off'), domain: [0, 100] },
  rpm: { label: 'RPM', unit: 'rpm', fmt: (v) => `${v.toFixed(0)} rpm` },
  gear: { label: 'Gear', unit: 'gear', fmt: (v) => `Gear ${v.toFixed(0)}`, domain: [0, 8] },
};
export { CHANNEL_META };

/** Overlay of one telemetry channel for two laps along lap distance. */
export function TelemetryOverlay({ distance, channel, data, nameA, nameB, highlight, height = 300 }) {
  const meta = CHANNEL_META[channel];
  const rows = distance.map((d, i) => ({ d, a: data.a[i], b: data.b[i] }));
  const step = channel === 'gear' || channel === 'brake';
  return (
    <div className="chart" style={{ height }}>
      <ResponsiveContainer>
        <LineChart data={rows} margin={{ top: 10, right: 16, bottom: 18, left: 4 }}>
          <CartesianGrid stroke={GRID} vertical={false} />
          <XAxis dataKey="d" type="number" domain={[0, 'dataMax']} {...axisProps} tickFormatter={(v) => `${(v / 1000).toFixed(1)}`}
            label={{ value: 'Distance (km)', position: 'insideBottom', offset: -8 }} />
          <YAxis {...axisProps} width={52} domain={meta.domain || ['auto', 'auto']} />
          {highlight && <ReferenceArea x1={highlight.start_m} x2={highlight.end_m} fill="#ff7d8c" fillOpacity={0.08} />}
          <Tooltip content={<ChartTooltip labelFormatter={(l) => `${Math.round(l)} m`} valueFormatter={(v) => meta.fmt(v)} />}
            cursor={{ stroke: '#5d6878', strokeDasharray: '3 3' }} />
          <Line type={step ? 'stepAfter' : 'linear'} dataKey="a" name={nameA} stroke={SERIES.a} strokeWidth={2} dot={false} isAnimationActive={false} />
          <Line type={step ? 'stepAfter' : 'linear'} dataKey="b" name={nameB} stroke={SERIES.b} strokeWidth={2} dot={false} isAnimationActive={false} />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}

/** Running time delta along the lap (A minus B). Above zero = A behind. */
export function DeltaTrace({ distance, delta, nameA, nameB, height = 170 }) {
  const rows = distance.map((d, i) => ({ d, delta: delta[i] }));
  return (
    <div className="chart" style={{ height }}>
      <ResponsiveContainer>
        <ComposedChart data={rows} margin={{ top: 8, right: 16, bottom: 18, left: 4 }}>
          <CartesianGrid stroke={GRID} vertical={false} />
          <XAxis dataKey="d" type="number" domain={[0, 'dataMax']} {...axisProps} tickFormatter={(v) => `${(v / 1000).toFixed(1)}`}
            label={{ value: 'Distance (km)', position: 'insideBottom', offset: -8 }} />
          <YAxis {...axisProps} width={52} tickFormatter={(v) => `${v > 0 ? '+' : ''}${v.toFixed(2)}`} />
          <ReferenceLine y={0} stroke="#7f8da0" />
          <Tooltip content={<ChartTooltip labelFormatter={(l) => `${Math.round(l)} m`}
            valueFormatter={(v) => (v > 0 ? `${nameA} ${v.toFixed(3)}s behind` : `${nameA} ${Math.abs(v).toFixed(3)}s ahead`)} />} />
          <Area type="linear" dataKey="delta" name={`${nameA} vs ${nameB}`} stroke="#cbd4e2" fill="#cbd4e2" fillOpacity={0.08} strokeWidth={2} isAnimationActive={false} />
        </ComposedChart>
      </ResponsiveContainer>
    </div>
  );
}

/** Mini-sector gains (negative) and losses (positive) for Driver A. */
export function MiniSectorBars({ sectors, nameA, onSelect, selected, height = 190 }) {
  const rows = sectors.map((m) => ({ ...m, label: `${m.index}` }));
  return (
    <div className="chart" style={{ height }}>
      <ResponsiveContainer>
        <BarChart data={rows} margin={{ top: 8, right: 16, bottom: 18, left: 4 }} onClick={(e) => e?.activePayload && onSelect?.(e.activePayload[0].payload)}>
          <CartesianGrid stroke={GRID} vertical={false} />
          <XAxis dataKey="label" {...axisProps} label={{ value: 'Mini-sector', position: 'insideBottom', offset: -8 }} />
          <YAxis {...axisProps} width={52} tickFormatter={(v) => v.toFixed(2)} />
          <ReferenceLine y={0} stroke="#7f8da0" />
          <Tooltip cursor={{ fill: 'rgba(255,255,255,0.04)' }}
            content={<ChartTooltip labelFormatter={(l) => { const m = rows.find((r) => r.label === l); return m ? `Mini-sector ${l} · ${m.start_m}–${m.end_m} m` : l; }}
              valueFormatter={(v) => `${nameA} ${v > 0 ? 'loses' : 'gains'} ${Math.abs(v).toFixed(3)}s`} />} />
          <Bar dataKey="delta_s" name={nameA} radius={[4, 4, 0, 0]} isAnimationActive={false} style={{ cursor: 'pointer' }}>
            {rows.map((r) => (
              <Cell key={r.index} fill={r.delta_s > 0 ? '#ff7d8c' : '#4fd1a1'} fillOpacity={selected && selected.index !== r.index ? 0.45 : 1} />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}

/** Fuel-corrected lap-time change vs tyre age for each stint. */
export function DegradationChart({ stints, height = 300, highlight }) {
  const series = stints.filter((s) => s.points?.length);
  const maxAge = Math.max(1, ...series.flatMap((s) => s.points.map((p) => p.age)));
  return (
    <div className="chart" style={{ height }}>
      <ResponsiveContainer>
        <ComposedChart margin={{ top: 10, right: 16, bottom: 18, left: 4 }}>
          <CartesianGrid stroke={GRID} vertical={false} />
          <XAxis dataKey="age" type="number" domain={[1, maxAge]} allowDuplicatedCategory={false} {...axisProps}
            label={{ value: 'Tyre age (laps)', position: 'insideBottom', offset: -8 }} />
          <YAxis {...axisProps} width={52} tickFormatter={(v) => `${v > 0 ? '+' : ''}${v.toFixed(1)}s`} />
          <ReferenceLine y={0} stroke="#7f8da0" />
          <Tooltip content={<ChartTooltip labelFormatter={(l) => `Tyre age ${l}`} valueFormatter={(v) => fmtDelta(v)} />} />
          {series.map((s) => {
            const color = COMPOUND_COLORS[s.compound || 'UNKNOWN'];
            const dim = highlight && highlight !== s.stint;
            return (
              <Line key={s.stint} data={s.points} dataKey="delta_s" name={`Stint ${s.stint} · ${compoundLabel(s.compound)}`}
                stroke={color} strokeWidth={dim ? 1.5 : 2.5} strokeOpacity={dim ? 0.3 : 1}
                strokeDasharray={s.compound ? undefined : '5 4'} dot={{ r: 2.5, fill: color, strokeWidth: 0 }}
                isAnimationActive={false} />
            );
          })}
        </ComposedChart>
      </ResponsiveContainer>
    </div>
  );
}

/** Cumulative modelled time difference, alternative minus actual (below zero = alternative ahead). */
export function CumulativeDeltaChart({ data, actualPits, altPits, height = 260 }) {
  return (
    <div className="chart" style={{ height }}>
      <ResponsiveContainer>
        <ComposedChart data={data} margin={{ top: 18, right: 16, bottom: 18, left: 4 }}>
          <CartesianGrid stroke={GRID} vertical={false} />
          <XAxis dataKey="lap" {...axisProps} label={{ value: 'Lap', position: 'insideBottom', offset: -8 }} />
          <YAxis {...axisProps} width={56} tickFormatter={(v) => `${v > 0 ? '+' : ''}${v.toFixed(0)}s`} />
          <ReferenceLine y={0} stroke="#7f8da0" />
          {actualPits.map((l) => (
            <ReferenceLine key={`a${l}`} x={l} stroke="#9aa6b7" strokeDasharray="4 4" label={{ value: `Actual pit L${l}`, position: 'top', fill: '#9aa6b7', fontSize: 10 }} />
          ))}
          {altPits.map((l) => (
            <ReferenceLine key={`b${l}`} x={l} stroke="#34c8ff" strokeDasharray="2 3" label={{ value: `Alt pit L${l}`, position: 'insideTopLeft', fill: '#34c8ff', fontSize: 10 }} />
          ))}
          <Tooltip content={<ChartTooltip labelFormatter={(l) => `After lap ${l}`}
            valueFormatter={(v) => (v < 0 ? `Alternative ahead by ${Math.abs(v).toFixed(2)}s` : v > 0 ? `Alternative behind by ${v.toFixed(2)}s` : 'Level')} />} />
          <Area type="linear" dataKey="delta_s" name="Alternative vs actual" stroke="#34c8ff" fill="#34c8ff" fillOpacity={0.1} strokeWidth={2} isAnimationActive={false} />
        </ComposedChart>
      </ResponsiveContainer>
    </div>
  );
}

/** Horizontal breakdown of the estimated delta. Negative values = time saved. */
export function BreakdownBars({ items, height = 150 }) {
  const span = Math.max(...items.map((i) => Math.abs(i.value)), 0.01);
  const digits = span < 1 ? 2 : span < 10 ? 1 : 0;
  const rows = items.map((i) => ({ ...i, name: `${i.label} (${fmtDelta(i.value, digits)})` }));
  return (
    <div className="chart" style={{ height }}>
      <ResponsiveContainer>
        <BarChart data={rows} layout="vertical" margin={{ top: 6, right: 16, bottom: 6, left: 8 }}>
          <CartesianGrid stroke={GRID} horizontal={false} />
          <XAxis type="number" {...axisProps} domain={[-span * 1.1, span * 1.1]} tickCount={5}
            tickFormatter={(v) => `${v > 0 ? '+' : ''}${v.toFixed(digits)}s`} />
          <YAxis type="category" dataKey="name" {...axisProps} width={170} />
          <ReferenceLine x={0} stroke="#7f8da0" />
          <Tooltip cursor={{ fill: 'rgba(255,255,255,0.04)' }} content={<ChartTooltip valueFormatter={(v) => `${fmtDelta(v, 2)} (${v < 0 ? 'time saved' : v > 0 ? 'time lost' : 'no change'})`} />} />
          <Bar dataKey="value" name="Estimated effect" radius={4} isAnimationActive={false}>
            {rows.map((it) => (
              <Cell key={it.label} fill={it.value < 0 ? '#4fd1a1' : it.value > 0 ? '#ff7d8c' : '#5d6878'} />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
