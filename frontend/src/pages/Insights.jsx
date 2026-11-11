import { Link, useNavigate } from 'react-router-dom';
import { useAnalysis } from '../state/AnalysisContext';
import { BreakdownBars, CumulativeDeltaChart } from '../components/charts';
import { Banner, CompoundPill, EmptyState, StintBar } from '../components/ui';
import { compoundLabel, fmtDelta, fmtRaceTime } from '../lib/format';
import { downloadExport } from '../lib/export';

function PlanCard({ title, plan, raceTime, risk, totalLaps, tone }) {
  return (
    <div className="card" style={tone ? { borderColor: tone } : undefined}>
      <h3>{title}</h3>
      <div style={{ margin: '10px 0' }}><StintBar stints={plan.stints} totalLaps={totalLaps} /></div>
      <div className="metric-row"><span>Pit laps</span><span>{plan.pit_laps.length ? plan.pit_laps.map((l) => `L${l}`).join(' · ') : 'No stops'}</span></div>
      <div className="metric-row"><span>Compounds</span><span style={{ display: 'flex', gap: 4, flexWrap: 'wrap', justifyContent: 'flex-end' }}>{plan.compounds.map((c, i) => <CompoundPill key={i} compound={c} />)}</span></div>
      <div className="metric-row"><span>Stops</span><span>{plan.pit_laps.length}</span></div>
      <div className="metric-row"><span>{title.startsWith('Actual') ? 'Race time (real)' : 'Estimated race time'}</span><span>{fmtRaceTime(raceTime)}</span></div>
      {risk && <div className="metric-row"><span>Tyre risk</span><span className={risk === 'High' ? 'bad' : risk === 'Medium' ? 'neutral' : 'good'}>{risk}</span></div>}
    </div>
  );
}

export default function Insights() {
  const { analysis, strategy, setStrategy, notify } = useAnalysis();
  const navigate = useNavigate();
  const r = strategy?.result;

  if (!r) {
    return (
      <div>
        <div className="hero-row"><div><h1>Actual vs alternative strategy</h1><p>Run a scenario in the Strategy Lab to compare it with the actual race.</p></div></div>
        <EmptyState
          title="No strategy scenario yet"
          actions={<><Link to="/strategy" className="btn primary">Open Strategy Lab</Link><Link to="/tires" className="btn">Review Tires &amp; Stints</Link></>}
        >
          The comparison appears after you click <b>Run Simulation</b> in the Strategy Lab. Telemetry, tyre and overview screens are still available.
        </EmptyState>
      </div>
    );
  }

  const driver = analysis.summaries[r.driver] || { name: r.driver };
  const same = Math.abs(r.delta_s) < 0.05;
  const breakdown = [
    { label: 'Pit stops', value: r.breakdown.pit_stops_s },
    { label: 'Tyres & pace', value: r.breakdown.tyre_and_pace_s },
    { label: 'Total estimate', value: r.delta_s },
  ];
  const firstShift = r.actual.pit_laps.length && r.alternative.pit_laps.length ? r.alternative.pit_laps[0] - r.actual.pit_laps[0] : null;
  const stint1 = analysis.stints[r.driver]?.[0];

  const reset = () => { setStrategy(null); notify('Scenario cleared.'); navigate('/strategy'); };

  return (
    <div>
      <div className="hero-row">
        <div>
          <h1>Actual vs alternative strategy</h1>
          <p>{driver.name} · {analysis.session.event_name} · {r.strategy_type.charAt(0).toUpperCase() + r.strategy_type.slice(1)} scenario</p>
        </div>
        <div className="btn-row">
          <Link to="/strategy" className="btn primary small">Modify scenario</Link>
          <button className="btn small" onClick={() => notify(`Exported ${downloadExport(analysis, strategy)}.`, 'success')}>Export results</button>
          <button className="btn small ghost" onClick={reset}>Reset</button>
        </div>
      </div>

      <Banner tone={same ? 'info' : r.faster ? 'success' : 'warn'} icon={same ? '≈' : r.faster ? '▲' : '▼'}
        title={same ? 'Alternative strategy: no meaningful change (estimate)' : `Alternative strategy: estimated ${Math.abs(r.delta_s).toFixed(1)}s ${r.faster ? 'faster' : 'slower'}`}>
        <span className="sub">{r.label}. Both plans are run through the same deterministic model ({r.model_version}); the gap is applied to the real race time.</span>
      </Banner>

      <div className="grid halves" style={{ marginBottom: 16 }}>
        <PlanCard title="Actual strategy" plan={r.actual} raceTime={r.actual.race_time_s} totalLaps={r.total_laps} />
        <PlanCard title="Alternative strategy" plan={r.alternative} raceTime={r.alternative.estimated_race_time_s} risk={r.tyre_risk} totalLaps={r.total_laps}
          tone={same ? undefined : r.faster ? 'rgba(79,209,161,.45)' : 'rgba(255,125,140,.45)'} />
      </div>

      <div className="grid two" style={{ marginBottom: 16 }}>
        <div className="card">
          <h3>Where the time changes</h3>
          <div className="sub">Cumulative modelled difference, alternative minus actual. Below zero = alternative ahead.</div>
          <CumulativeDeltaChart data={r.cumulative_delta} actualPits={r.actual.pit_laps} altPits={r.alternative.pit_laps} />
        </div>
        <div className="card">
          <h3>Estimated delta breakdown</h3>
          <div className="sub">Negative = time saved by the alternative.</div>
          <BreakdownBars items={breakdown} />
          <table className="table">
            <tbody>
              <tr><td>Modelled actual total</td><td className="r">{fmtRaceTime(r.actual.modelled_time_s)}</td></tr>
              <tr><td>Modelled alternative total</td><td className="r">{fmtRaceTime(r.alternative.modelled_time_s)}</td></tr>
              <tr><td>Pit loss used</td><td className="r">{r.model.pit_loss_s.toFixed(1)}s / stop</td></tr>
            </tbody>
          </table>
        </div>
      </div>

      <div className="grid two">
        <div className="card">
          <h3>Strategy insight</h3>
          <div className="insight">{r.explanation}</div>
          {r.warnings.length > 0 && <div className="insight warn" style={{ marginTop: 10 }}>{r.warnings.map((w) => <div key={w}>⚠ {w}</div>)}</div>}
          <h3 style={{ marginTop: 18 }}>Evidence</h3>
          <div className="grid">
            <Link to="/tires" className="card" style={{ textDecoration: 'none', color: 'inherit' }}>
              <b>Tires &amp; Stints →</b>
              <div className="sub">
                {stint1 ? `Stint 1 (${compoundLabel(stint1.compound)}) ran laps ${stint1.start_lap}–${stint1.end_lap} with a ${stint1.trend.toLowerCase()} trend${stint1.deg_s_per_lap != null ? ` (+${stint1.deg_s_per_lap.toFixed(3)} s/lap)` : ''}.` : 'Review stint lengths and degradation.'}
              </div>
            </Link>
            <Link to="/telemetry" className="card" style={{ textDecoration: 'none', color: 'inherit' }}>
              <b>Telemetry →</b>
              <div className="sub">Check where {r.driver} gained or lost time on individual laps.</div>
            </Link>
            <Link to="/strategy" className="card" style={{ textDecoration: 'none', color: 'inherit' }}>
              <b>Strategy Lab →</b>
              <div className="sub">
                {firstShift ? `Pit Stop 1 moved ${Math.abs(firstShift)} lap${Math.abs(firstShift) === 1 ? '' : 's'} ${firstShift < 0 ? 'earlier' : 'later'} (lap ${r.actual.pit_laps[0]} → ${r.alternative.pit_laps[0]}).` : 'Adjust pit laps and compounds.'}
              </div>
            </Link>
          </div>
        </div>
        <div className="card">
          <h3>What this estimate does and does not include</h3>
          <ul className="sub" style={{ paddingLeft: 18, lineHeight: 1.7 }}>
            {r.model.assumptions.map((x) => <li key={x}>{x}</li>)}
          </ul>
          <div className="sub">Pit timing in real races also depends on traffic, rivals' reactions and safety cars, which this MVP does not simulate.</div>
          <div className="btn-row" style={{ marginTop: 12 }}>
            <Link to="/strategy" className="btn small primary">Modify scenario</Link>
            <Link to="/telemetry" className="btn small">Return to Telemetry</Link>
            <Link to="/tires" className="btn small">Return to Tires &amp; Stints</Link>
          </div>
        </div>
      </div>
      <div className="sub mt">Delta shown as {fmtDelta(r.delta_s, 2)} (alternative − actual).</div>
    </div>
  );
}
