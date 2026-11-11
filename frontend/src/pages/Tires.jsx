import { useState } from 'react';
import { Link } from 'react-router-dom';
import { useAnalysis } from '../state/AnalysisContext';
import { DegradationChart, LapTimeChart } from '../components/charts';
import { Banner, CompoundPill, NextSteps, StintBar } from '../components/ui';
import { COMPOUND_COLORS, SERIES, compoundLabel, fmtLap } from '../lib/format';

const TREND_CLASS = { Degrading: 'bad', Moderate: 'neutral', Stable: 'good', 'Insufficient data': 'muted' };

export default function Tires() {
  const { analysis } = useAnalysis();
  const { driver_a: a, driver_b: b } = analysis.selected;
  const [driver, setDriver] = useState(a);
  const [focus, setFocus] = useState(null); // stint number or null = all
  const stints = analysis.stints[driver] || [];
  const summary = analysis.summaries[driver];
  const pits = analysis.pit_stops?.[driver] || [];
  const missingCompound = stints.some((s) => !s.compound_known);
  const fitted = stints.filter((s) => s.deg_s_per_lap != null);
  const worst = fitted.length ? fitted.reduce((m, s) => (s.deg_s_per_lap > m.deg_s_per_lap ? s : m)) : null;
  const visible = focus ? stints.filter((s) => s.stint === focus) : stints;

  return (
    <div>
      <div className="hero-row">
        <div>
          <h1>Tire &amp; stint analysis</h1>
          <p>Stint lengths, pit-stop locations and a simple, fuel-corrected pace trend for each stint.</p>
        </div>
        <NextSteps items={[{ to: '/telemetry', label: 'Telemetry' }, { to: '/strategy', label: 'Open Strategy Lab', primary: true }]} />
      </div>

      <div className="control-strip" style={{ gridTemplateColumns: 'auto 1fr', alignItems: 'center' }}>
        <div className="segmented" role="tablist" aria-label="Driver">
          {[a, b].filter(Boolean).map((c, i) => (
            <button key={c} className={driver === c ? 'active' : ''} onClick={() => { setDriver(c); setFocus(null); }}>
              <i className="swatch" style={{ background: i === 0 ? SERIES.a : SERIES.b, marginRight: 6 }} />{c}
            </button>
          ))}
        </div>
        <div className="tabs" role="tablist" aria-label="Stint filter">
          <button className={`tab ${focus === null ? 'active' : ''}`} onClick={() => setFocus(null)}>All stints</button>
          {stints.map((s) => (
            <button key={s.stint} className={`tab ${focus === s.stint ? 'active' : ''}`} onClick={() => setFocus(s.stint)}>
              Stint {s.stint} · {compoundLabel(s.compound)}
            </button>
          ))}
        </div>
      </div>

      {missingCompound && (
        <Banner tone="info" title="Tyre compound is unknown for some stints">
          Stints are still derived from pit stops, and pace trends still use lap times. Unknown stints are drawn with a striped pattern and a dashed line.
          {analysis.session.availability.compounds ? '' : ' This data source does not include tyre compounds.'}
        </Banner>
      )}

      <div className="card" style={{ marginBottom: 16 }}>
        <div className="card-head">
          <div>
            <h3>Stint timeline</h3>
            <div className="sub">Compound per stint and the lap each pit stop happened</div>
          </div>
          <div className="legend">
            {['SOFT', 'MEDIUM', 'HARD'].map((c) => <span key={c}><i className="swatch" style={{ background: COMPOUND_COLORS[c] }} />{compoundLabel(c)}</span>)}
            {missingCompound && <span><i className="swatch" style={{ background: '#3a4556' }} />Unknown</span>}
          </div>
        </div>
        {[a, b].filter(Boolean).map((c) => (
          <div key={c} style={{ marginBottom: 10, opacity: c === driver ? 1 : 0.6 }}>
            <StintBar stints={analysis.stints[c]} totalLaps={analysis.summaries[c].laps_completed} label={`${c} · ${analysis.summaries[c].name} · ${analysis.summaries[c].pit_count} stop(s)`} />
          </div>
        ))}
      </div>

      <div className="grid" style={{ gridTemplateColumns: `repeat(${Math.min(Math.max(stints.length, 1), 4)}, minmax(0, 1fr))`, marginBottom: 16 }}>
        {stints.map((s) => (
          <button key={s.stint} className={`card stint-card ${focus === s.stint ? 'selected' : ''}`} style={{ textAlign: 'left', color: 'inherit', cursor: 'pointer' }}
            onClick={() => setFocus(focus === s.stint ? null : s.stint)} aria-pressed={focus === s.stint}>
            <div className="card-head" style={{ marginBottom: 6 }}>
              <CompoundPill compound={s.compound} />
              <span className={`sub ${TREND_CLASS[s.trend]}`} style={{ fontWeight: 700 }}>{s.trend}</span>
            </div>
            <h3>Stint {s.stint}</h3>
            <div className="metric-row"><span>Laps</span><span>{s.start_lap}–{s.end_lap}</span></div>
            <div className="metric-row"><span>Length</span><span>{s.length} laps</span></div>
            <div className="metric-row"><span>Avg clean pace</span><span>{fmtLap(s.avg_pace_s)}</span></div>
            <div className="metric-row"><span>Degradation</span><span>{s.deg_s_per_lap != null ? `+${s.deg_s_per_lap.toFixed(3)} s/lap` : '—'}</span></div>
            <div className="metric-row"><span>Late-stint drop</span><span>{s.late_stint_drop_s != null ? `${s.late_stint_drop_s > 0 ? '+' : ''}${s.late_stint_drop_s.toFixed(2)}s` : '—'}</span></div>
            <div className="metric-row"><span>Ended with</span><span>{s.pit_lap ? `Pit · lap ${s.pit_lap}` : s.end_lap === summary.laps_completed ? 'Chequered flag' : 'Retirement'}</span></div>
          </button>
        ))}
      </div>

      <div className="grid two">
        <div className="card">
          <div className="card-head">
            <div>
              <h3>Pace change vs tyre age</h3>
              <div className="sub">Fuel-corrected clean laps, relative to the first clean lap of each stint. Steeper = more degradation.</div>
            </div>
            <div className="legend">
              {visible.filter((s) => s.points?.length).map((s) => (
                <span key={s.stint}><i className="line-key" style={{ background: COMPOUND_COLORS[s.compound || 'UNKNOWN'] }} />Stint {s.stint}</span>
              ))}
            </div>
          </div>
          {fitted.length || stints.some((s) => s.points?.length > 1)
            ? <DegradationChart stints={stints} highlight={focus} />
            : <div className="empty"><strong>Not enough clean laps</strong>Degradation needs at least four representative laps in a stint.</div>}
        </div>
        <div className="card">
          <h3>Stint insight</h3>
          <div className="insight" style={{ marginBottom: 12 }}>{analysis.stint_insights[driver]}</div>
          <div className="table-wrap">
            <table className="table">
              <thead><tr><th>Stop</th><th>Lap</th><th>Change</th><th className="r" title="Time spent in the pit lane, as reported by the data source">Pit-lane time</th></tr></thead>
              <tbody>
                {stints.slice(0, -1).map((s, i) => {
                  const p = pits.find((x) => x.lap === s.pit_lap);
                  const next = stints[i + 1];
                  return (
                    <tr key={s.stint} className={worst && worst.stint === s.stint ? 'hl' : ''}>
                      <td>#{i + 1}</td>
                      <td>Lap {s.pit_lap ?? s.end_lap}</td>
                      <td>{compoundLabel(s.compound)} → {compoundLabel(next.compound)}</td>
                      <td className="r">{p?.duration_s != null ? `${p.duration_s.toFixed(1)}s` : '—'}</td>
                    </tr>
                  );
                })}
                {stints.length <= 1 && <tr><td colSpan={4} className="muted">No pit stops recorded for {driver}.</td></tr>}
              </tbody>
            </table>
          </div>
          <div className="sub" style={{ marginTop: 10 }}>
            <b>Method:</b> lap 1, in/out laps and laps slower than 107% of the driver's median are excluded. Each lap is corrected by +0.035s per lap
            for fuel burn, then a straight line is fitted against tyre age. This is a trend estimate from lap times, not a tyre-physics model.
          </div>
          <Link to="/strategy" className="btn primary" style={{ marginTop: 14 }}>Open Strategy Lab →</Link>
        </div>
      </div>

      <div className="card mt">
        <div className="card-head">
          <div>
            <h3>Lap progression · {driver}</h3>
            <div className="sub">Lap times across the race; dashed lines mark pit stops.</div>
          </div>
        </div>
        <LapTimeChart rows={analysis.lap_series} a={driver} height={240} colorA={driver === a ? SERIES.a : SERIES.b} />
      </div>
    </div>
  );
}
