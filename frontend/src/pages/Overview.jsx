import { useState } from 'react';
import { Link } from 'react-router-dom';
import { useAnalysis } from '../state/AnalysisContext';
import DriverSwitcher from '../components/DriverSwitcher';
import { GapChart, LapTimeChart } from '../components/charts';
import { Banner, Kpi, NextSteps, StintBar } from '../components/ui';
import { SERIES, deltaClass, fmtDelta, fmtLap, fmtPos, fmtRaceTime } from '../lib/format';

function positionNote(s) {
  if (!s.grid || !s.position) return s.status || '';
  const diff = s.grid - s.position;
  const moved = diff > 0 ? `+${diff} from P${s.grid}` : diff < 0 ? `${diff} from P${s.grid}` : `Started P${s.grid}`;
  return s.status && s.status !== 'Finished' && !s.status.startsWith('+') ? `${s.status} · ${moved}` : moved;
}

function Availability({ meta }) {
  const items = [
    ['Lap times', meta.availability.lap_times],
    ['Running positions', meta.availability.positions],
    ['Sector times', meta.availability.sectors],
    ['Tyre compounds', meta.availability.compounds],
    ['Car telemetry', meta.availability.telemetry],
  ];
  return (
    <div className="card">
      <h3>Data in this session</h3>
      <div className="sub" style={{ marginBottom: 6 }}>{meta.source_label}</div>
      {items.map(([label, ok]) => (
        <div className="metric-row" key={label}>
          <span>{label}</span>
          <span className={ok ? 'good' : 'muted'}>{ok ? '✓ Available' : '— Unavailable'}</span>
        </div>
      ))}
      {meta.notes?.length > 0 && (
        <ul className="sub" style={{ paddingLeft: 18, marginBottom: 0 }}>
          {meta.notes.map((n) => <li key={n}>{n}</li>)}
        </ul>
      )}
    </div>
  );
}

export default function Overview() {
  const { analysis } = useAnalysis();
  const [view, setView] = useState('laps');
  const meta = analysis.session;
  const { driver_a: a, driver_b: b } = analysis.selected;
  const sa = analysis.summaries[a];
  const sb = b ? analysis.summaries[b] : null;
  const cmp = analysis.comparison;
  const missing = !meta.availability.telemetry || !meta.availability.compounds;

  return (
    <div>
      <div className="hero-row">
        <div>
          <h1>{meta.event_name} — {meta.session_name}</h1>
          <p>
            {meta.season === 'demo' ? 'Demo season' : meta.season} · {meta.circuit || 'Circuit n/a'}{meta.date && meta.season !== 'demo' ? ` · ${meta.date}` : ''} · {meta.total_laps} laps ·{' '}
            <b style={{ color: '#fff' }}>{sa.name}</b>{sb && <> vs <b style={{ color: '#fff' }}>{sb.name}</b></>}
          </p>
        </div>
        <NextSteps items={[{ to: '/telemetry', label: 'Compare Telemetry' }, { to: '/tires', label: 'Tires & Stints' }, { to: '/strategy', label: 'Strategy Lab', primary: true }]} />
      </div>

      <DriverSwitcher />

      {missing && !analysis.fallback && (
        <Banner tone="info" title="Some data is not available for this session">
          {!meta.availability.telemetry && 'Car telemetry is unavailable, so the Telemetry screen compares lap times only. '}
          {!meta.availability.compounds && 'Tyre compounds are unknown for some or all stints; stints are still derived from pit stops. '}
          Lap-time trends, gaps, stints and the Strategy Lab all still work.
        </Banner>
      )}

      <div className="grid kpis">
        <Kpi label={`${a} finish`} value={fmtPos(sa.position)} delta={positionNote(sa)} tone={sa.grid && sa.position && sa.grid > sa.position ? 'good' : 'neutral'} />
        {sb ? <Kpi label={`${b} finish`} value={fmtPos(sb.position)} delta={positionNote(sb)} tone={sb.grid && sb.position && sb.grid > sb.position ? 'good' : 'neutral'} />
          : <Kpi label="Race time" value={fmtRaceTime(sa.total_time_s)} delta={sa.status || ''} />}
        <Kpi label={`${a} best lap`} value={fmtLap(sa.best_lap?.time_s)}
          delta={cmp ? `${fmtDelta(cmp.best_lap_delta_s)} vs ${b}` : sa.best_lap ? `Lap ${sa.best_lap.lap}` : ''} tone={cmp ? deltaClass(cmp.best_lap_delta_s) : 'neutral'} />
        {sb ? <Kpi label={`${b} best lap`} value={fmtLap(sb.best_lap?.time_s)} delta={sb.best_lap ? `Lap ${sb.best_lap.lap}` : ''} />
          : <Kpi label="Avg clean pace" value={fmtLap(sa.avg_clean_pace_s)} delta={`${sa.clean_lap_count} clean laps`} />}
        {cmp ? (
          <Kpi label="Finish gap" value={cmp.finish_gap_s != null ? fmtDelta(cmp.finish_gap_s, 1) : '—'}
            delta={cmp.finish_gap_s != null ? (cmp.finish_gap_s > 0 ? `${a} behind ${b}` : `${a} ahead of ${b}`) : 'Not both classified on time'}
            tone={deltaClass(cmp.finish_gap_s)} />
        ) : (
          <Kpi label="Laps completed" value={sa.laps_completed} delta={sa.status || ''} />
        )}
        <Kpi label={`Pit stops`} value={sb ? `${sa.pit_count} / ${sb.pit_count}` : sa.pit_count}
          delta={sb ? `${a}: L${sa.pit_laps.join(', L') || '—'} · ${b}: L${sb.pit_laps.join(', L') || '—'}` : `L${sa.pit_laps.join(', L') || '—'}`} />
      </div>

      <div className="grid two">
        <div className="card">
          <div className="card-head">
            <div>
              <h3>{view === 'laps' ? 'Lap-time trend' : `Race gap: ${a} vs ${b}`}</h3>
              <div className="sub">
                {view === 'laps'
                  ? 'Every lap; dashed lines mark pit stops. Lap 1, pit laps and slow outliers can sit off the chart.'
                  : `Cumulative race time difference. Above zero = ${a} behind ${b}.`}
              </div>
            </div>
            <div className="btn-row">
              <div className="legend">
                <span><i className="line-key" style={{ background: SERIES.a }} />{a}</span>
                {b && <span><i className="line-key" style={{ background: SERIES.b }} />{b}</span>}
              </div>
              {b && (
                <div className="segmented" role="tablist">
                  <button className={view === 'laps' ? 'active' : ''} onClick={() => setView('laps')}>Lap times</button>
                  <button className={view === 'gap' ? 'active' : ''} onClick={() => setView('gap')}>Gap</button>
                </div>
              )}
            </div>
          </div>
          {view === 'laps' || !cmp ? <LapTimeChart rows={analysis.lap_series} a={a} b={b} /> : <GapChart series={cmp.gap_series} a={a} b={b} />}
          {cmp && (
            <div className="insight" style={{ marginTop: 10 }}>
              On the {cmp.common_clean_laps} laps where both drivers set a representative time, <b>{a}</b> was faster on {cmp.laps_a_faster} and <b>{b}</b> on {cmp.laps_b_faster}.
              Average clean-lap pace difference: <b>{fmtDelta(cmp.avg_pace_delta_s)}</b> ({cmp.avg_pace_delta_s < 0 ? `${a} quicker` : `${b} quicker`}).
              {cmp.max_gap && <> Largest gap: {Math.abs(cmp.max_gap.gap_s).toFixed(1)}s after lap {cmp.max_gap.lap}.</>}
            </div>
          )}
        </div>

        <div className="stack">
          <div className="card">
            <h3>Actual strategy</h3>
            <div className="sub">Tyre stints and pit laps</div>
            <div style={{ marginTop: 10 }}>
              <StintBar stints={analysis.stints[a]} totalLaps={sa.laps_completed} label={`${a} · ${sa.name}`} />
            </div>
            {b && (
              <div style={{ marginTop: 12 }}>
                <StintBar stints={analysis.stints[b]} totalLaps={sb.laps_completed} label={`${b} · ${sb.name}`} />
              </div>
            )}
            <div className="insight" style={{ marginTop: 14 }}>{analysis.stint_insights[a]}</div>
            <div className="btn-row" style={{ marginTop: 12 }}>
              <Link to="/tires" className="btn small">Analyze Tires</Link>
              <Link to="/strategy" className="btn small primary">Test Strategy</Link>
            </div>
          </div>
        </div>
      </div>

      <div className="grid two mt">
        <div className="card">
          <h3>Driver comparison</h3>
          <div className="table-wrap">
            <table className="table">
              <thead>
                <tr>
                  <th>Metric</th>
                  <th className="r"><i className="swatch" style={{ background: SERIES.a }} /> {a}</th>
                  {sb && <th className="r"><i className="swatch" style={{ background: SERIES.b }} /> {b}</th>}
                  {sb && <th className="r">{a} − {b}</th>}
                </tr>
              </thead>
              <tbody>
                <tr><td>Team</td><td className="r">{sa.team || '—'}</td>{sb && <td className="r">{sb.team || '—'}</td>}{sb && <td />}</tr>
                <tr><td>Grid → finish</td><td className="r">{fmtPos(sa.grid)} → {fmtPos(sa.position)}</td>{sb && <td className="r">{fmtPos(sb.grid)} → {fmtPos(sb.position)}</td>}{sb && <td className="r">{cmp.position_delta == null ? '—' : cmp.position_delta === 0 ? 'Same position' : `${a} ${Math.abs(cmp.position_delta)} place${Math.abs(cmp.position_delta) === 1 ? '' : 's'} ${cmp.position_delta > 0 ? 'behind' : 'ahead'}`}</td>}</tr>
                <tr><td>Best lap</td><td className="r">{fmtLap(sa.best_lap?.time_s)}</td>{sb && <td className="r">{fmtLap(sb.best_lap?.time_s)}</td>}{sb && <td className={`r ${deltaClass(cmp.best_lap_delta_s)}`}>{fmtDelta(cmp.best_lap_delta_s)}</td>}</tr>
                <tr><td>Avg clean-lap pace</td><td className="r">{fmtLap(sa.avg_clean_pace_s)}</td>{sb && <td className="r">{fmtLap(sb.avg_clean_pace_s)}</td>}{sb && <td className={`r ${deltaClass(cmp.avg_pace_delta_s)}`}>{fmtDelta(cmp.avg_pace_delta_s)}</td>}</tr>
                <tr><td>Race time</td><td className="r">{fmtRaceTime(sa.total_time_s)}</td>{sb && <td className="r">{fmtRaceTime(sb.total_time_s)}</td>}{sb && <td className={`r ${deltaClass(cmp.finish_gap_s)}`}>{fmtDelta(cmp.finish_gap_s, 1)}</td>}</tr>
                <tr><td>Pit stops</td><td className="r">{sa.pit_count}</td>{sb && <td className="r">{sb.pit_count}</td>}{sb && <td />}</tr>
                <tr><td>Laps completed</td><td className="r">{sa.laps_completed}</td>{sb && <td className="r">{sb.laps_completed}</td>}{sb && <td />}</tr>
                <tr><td>Points</td><td className="r">{sa.points ?? '—'}</td>{sb && <td className="r">{sb.points ?? '—'}</td>}{sb && <td />}</tr>
              </tbody>
            </table>
          </div>
          {!sb && <div className="sub" style={{ marginTop: 10 }}>Add a Driver B above to see side-by-side deltas and the race gap chart.</div>}
        </div>
        <Availability meta={meta} />
      </div>
    </div>
  );
}
