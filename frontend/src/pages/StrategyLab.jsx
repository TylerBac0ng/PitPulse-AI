import { useEffect, useMemo, useRef, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { api } from '../api/client';
import { useAnalysis } from '../state/AnalysisContext';
import { Banner, CompoundPill, ErrorPanel, LoadingPanel, NextSteps, Spinner, StintBar } from '../components/ui';
import { SERIES, compoundLabel, fmtDelta, fmtLap, fmtRaceTime } from '../lib/format';

const TYPES = [
  { id: 'baseline', label: 'Baseline', help: 'Any pit laps — compare a custom plan against the actual race.' },
  { id: 'undercut', label: 'Undercut', help: 'Pit earlier than the actual first stop to get onto fresh tyres sooner.' },
  { id: 'overcut', label: 'Overcut', help: 'Stay out longer than the actual first stop, then pit.' },
];

/** Client-side mirror of the backend rules for instant feedback (the API re-validates). */
export function validatePlan({ pits, totalLaps, minStint, type, actualFirst }) {
  const errors = {};
  pits.forEach((p, i) => {
    if (!Number.isInteger(p) || p < 2 || p > totalLaps - 1) errors[`pit${i + 1}`] = `Pit Stop ${i + 1} must be between lap 2 and lap ${totalLaps - 1}.`;
  });
  for (let i = 1; i < pits.length; i += 1) {
    if (pits[i] <= pits[i - 1]) errors[`pit${i + 1}`] = `Pit Stop ${i + 1} must occur after Pit Stop ${i}.`;
    else if (pits[i] - pits[i - 1] < minStint) errors[`pit${i + 1}`] = `Stints must be at least ${minStint} laps long (Pit Stop ${i} → ${i + 1}).`;
  }
  const last = pits[pits.length - 1];
  if (!errors[`pit${pits.length}`] && totalLaps - last < minStint) errors[`pit${pits.length}`] = `The final stint must be at least ${minStint} laps long.`;
  if (type !== 'baseline' && !actualFirst) errors.type = 'This driver did not pit, so undercut/overcut does not apply. Use Baseline.';
  else if (type === 'undercut' && pits[0] >= actualFirst) errors.pit1 = errors.pit1 || `An undercut means pitting before the actual first stop (lap ${actualFirst}).`;
  else if (type === 'overcut' && pits[0] <= actualFirst) errors.pit1 = errors.pit1 || `An overcut means pitting after the actual first stop (lap ${actualFirst}).`;
  return errors;
}

function defaultInputs(base) {
  const nStops = Math.min(Math.max(base.actual_pit_laps.length, 1), 3);
  const pits = base.actual_pit_laps.length
    ? base.actual_pit_laps.slice(0, 3)
    : [Math.round(base.total_laps / 2)];
  const compounds = Array.from({ length: nStops + 1 }, (_, i) => base.actual_compounds[Math.min(i, base.actual_compounds.length - 1)]);
  return { pits, compounds, type: 'baseline' };
}

export default function StrategyLab() {
  const { analysis, strategy, setStrategy, notify } = useAnalysis();
  const navigate = useNavigate();
  const { driver_a: a, driver_b: b } = analysis.selected;
  const [driver, setDriver] = useState(strategy?.driver || a);
  const [base, setBase] = useState(null);
  const [baseError, setBaseError] = useState(null);
  const [inputs, setInputs] = useState(null);
  const [running, setRunning] = useState(false);
  const [runError, setRunError] = useState(null);
  const [result, setResult] = useState(strategy?.driver === driver ? strategy.result : null);
  const [ranWith, setRanWith] = useState(strategy?.driver === driver ? JSON.stringify(strategy.inputs) : null);
  const [reloadKey, setReloadKey] = useState(0);
  const builderRef = useRef(null);
  const key = analysis.session.key;

  useEffect(() => {
    const ctrl = new AbortController();
    setBase(null);
    setBaseError(null);
    api
      .strategyBaseline(key, driver, { signal: ctrl.signal })
      .then((data) => {
        setBase(data);
        if (strategy?.driver === driver && strategy.inputs) {
          setInputs(strategy.inputs);
          setResult(strategy.result);
          setRanWith(JSON.stringify(strategy.inputs));
        } else {
          setInputs(defaultInputs(data));
          setResult(null);
        }
      })
      .catch((e) => e.name !== 'AbortError' && setBaseError(e));
    return () => ctrl.abort();
  }, [key, driver, reloadKey]); // eslint-disable-line react-hooks/exhaustive-deps

  const errors = useMemo(() => {
    if (!base || !inputs) return {};
    return validatePlan({ pits: inputs.pits, totalLaps: base.total_laps, minStint: base.min_stint_laps, type: inputs.type, actualFirst: base.actual_pit_laps[0] });
  }, [base, inputs]);
  const hasErrors = Object.keys(errors).length > 0;

  if (baseError) return <ErrorPanel error={baseError} onRetry={() => setReloadKey((k) => k + 1)} actions={<Link to="/overview" className="btn small">Back to Overview</Link>} />;
  if (!base || !inputs) return <LoadingPanel label="Preparing Strategy Lab…" detail="Fitting pace, degradation and pit-loss assumptions for this driver." />;

  const setStops = (n) => {
    setInputs((cur) => {
      const pits = [...cur.pits];
      while (pits.length < n) pits.push(Math.min((pits[pits.length - 1] || 1) + Math.max(base.min_stint_laps, Math.floor(base.total_laps / (n + 1))), base.total_laps - base.min_stint_laps));
      pits.length = n;
      const compounds = [...cur.compounds];
      while (compounds.length < n + 1) compounds.push(compounds[compounds.length - 1]);
      compounds.length = n + 1;
      return { ...cur, pits, compounds };
    });
    setRunError(null);
  };
  const setPit = (i, v) => { setInputs((cur) => ({ ...cur, pits: cur.pits.map((p, j) => (j === i ? v : p)) })); setRunError(null); };
  const setCompound = (i, v) => setInputs((cur) => ({ ...cur, compounds: cur.compounds.map((c, j) => (j === i ? v : c)) }));
  const setType = (t) => {
    const first = base.actual_pit_laps[0];
    setInputs((cur) => {
      const pits = [...cur.pits];
      if (first && t === 'undercut' && pits[0] >= first) pits[0] = Math.max(2, first - 3);
      if (first && t === 'overcut' && pits[0] <= first) pits[0] = Math.min(base.total_laps - base.min_stint_laps, first + 3);
      return { ...cur, type: t, pits };
    });
    setRunError(null);
  };
  const reset = () => { setInputs(defaultInputs(base)); setResult(null); setRunError(null); setStrategy(null); notify('Strategy reset to the actual race plan.'); };

  async function run() {
    if (hasErrors) return;
    setRunning(true);
    setRunError(null);
    try {
      const body = { driver, pit_laps: inputs.pits, strategy_type: inputs.type, compounds: base.compounds_known ? inputs.compounds : null };
      const [res] = await Promise.all([api.simulate(key, body), new Promise((r) => setTimeout(r, 450))]); // brief, visible progress
      setResult(res);
      setRanWith(JSON.stringify(inputs));
      setStrategy({ driver, inputs, result: res });
      notify(`Simulation complete: ${Math.abs(res.delta_s).toFixed(1)}s ${res.faster ? 'faster' : 'slower'} (estimate).`, 'success');
    } catch (e) {
      setRunError(e);
    } finally {
      setRunning(false);
    }
  }

  const fieldErr = (f) => errors[f] || (runError?.field === f ? runError.message : null);
  const typeHelp = TYPES.find((t) => t.id === inputs.type)?.help;
  const actualStints = base.actual_stints;

  return (
    <div>
      <div className="hero-row">
        <div>
          <h1>Strategy Lab</h1>
          <p>Change pit timing and tyre choices to compare a hypothetical strategy against what actually happened.</p>
        </div>
        <div className="btn-row">
          <span className="badge estimate">Estimates only — not a race prediction</span>
          {b && (
            <div className="segmented" role="tablist" aria-label="Driver">
              {[a, b].map((c, i) => (
                <button key={c} className={driver === c ? 'active' : ''} onClick={() => setDriver(c)}>
                  <i className="swatch" style={{ background: i === 0 ? SERIES.a : SERIES.b, marginRight: 6 }} />{c}
                </button>
              ))}
            </div>
          )}
        </div>
      </div>

      <div className="strategy-layout">
        <div className="stack">
          <div className="card">
            <h3>Actual strategy · {driver}</h3>
            <div className="sub">{analysis.session.event_name} · {base.total_laps} laps completed</div>
            <div style={{ marginTop: 10 }}><StintBar stints={actualStints} totalLaps={base.total_laps} /></div>
            {actualStints.map((s) => (
              <div className="metric-row" key={s.stint}>
                <span><CompoundPill compound={s.compound} /> &nbsp;Stint {s.stint}</span>
                <span>Laps {s.start_lap}–{s.end_lap} ({s.length})</span>
              </div>
            ))}
            <div className="metric-row"><span>Pit laps</span><span>{base.actual_pit_laps.length ? base.actual_pit_laps.map((l) => `L${l}`).join(' · ') : 'No stops'}</span></div>
            <div className="metric-row"><span>Race time</span><span>{fmtRaceTime(base.race_time_s)}</span></div>
            <div className="metric-row"><span>Measured pit loss</span><span>{base.pit_loss_s.toFixed(1)}s / stop{base.pit_loss_source === 'default' ? ' (default)' : ''}</span></div>
          </div>
          <div className="card">
            <h3>Model inputs</h3>
            <div className="sub">Fitted from this session's lap times. Same inputs always give the same result. ↗ = wear accelerates with tyre age.</div>
            <div className="table-wrap">
              <table className="table" style={{ marginTop: 8 }}>
                <thead><tr><th>Tyre</th><th className="r">Base pace</th><th className="r">Deg / lap</th><th className="r">Life</th><th>Source</th></tr></thead>
                <tbody>
                  {Object.values(base.compound_models).map((c) => (
                    <tr key={c.compound}>
                      <td>{c.compound === 'UNKNOWN' ? 'Generic tyre' : compoundLabel(c.compound)}</td>
                      <td className="r">{fmtLap(c.base_s)}</td>
                      <td className="r" title={c.curve_s_per_lap2 > 0 ? `Accelerating wear: +${c.curve_s_per_lap2.toFixed(4)}s × age²` : 'Linear degradation'}>
                        +{c.deg_s_per_lap.toFixed(3)}s{c.curve_s_per_lap2 > 0 && <span className="neutral"> ↗</span>}
                      </td>
                      <td className="r">{c.life_laps} laps</td>
                      <td className="muted">{c.source === 'driver' ? 'This driver' : c.source === 'field' ? 'Other drivers' : 'Default'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <details style={{ marginTop: 10 }}>
              <summary className="sub" style={{ cursor: 'pointer' }}>Assumptions &amp; limitations</summary>
              <ul className="sub" style={{ paddingLeft: 18 }}>{base.assumptions.map((x) => <li key={x}>{x}</li>)}</ul>
            </details>
          </div>
        </div>

        <div className="stack" ref={builderRef}>
          <div className="card">
            <h3>Alternative strategy builder</h3>
            <div className="sub" style={{ marginBottom: 14 }}>{base.compounds_known ? 'Set pit laps and the tyre for each stint.' : 'Tyre compounds are unavailable for this session, so only pit timing can be changed.'}</div>

            <div className="grid halves" style={{ marginBottom: 14 }}>
              <div>
                <label>Strategy type</label>
                <div className="segmented" role="radiogroup" aria-label="Strategy type">
                  {TYPES.map((t) => (
                    <button key={t.id} role="radio" aria-checked={inputs.type === t.id} className={inputs.type === t.id ? 'active' : ''} onClick={() => setType(t.id)}>{t.label}</button>
                  ))}
                </div>
                <div className={`hint sub ${errors.type ? 'bad' : ''}`} style={{ marginTop: 6 }}>{errors.type || typeHelp}</div>
              </div>
              <div>
                <label>Number of stops</label>
                <div className="segmented" role="radiogroup" aria-label="Number of stops">
                  {[1, 2, 3].map((n) => (
                    <button key={n} role="radio" aria-checked={inputs.pits.length === n} className={inputs.pits.length === n ? 'active' : ''} onClick={() => setStops(n)}>{n}-stop</button>
                  ))}
                </div>
                <div className="sub" style={{ marginTop: 6 }}>Actual: {base.actual_pit_laps.length}-stop</div>
              </div>
            </div>

            {base.compounds_known && (
              <div className="field" style={{ marginBottom: 12, maxWidth: 260 }}>
                <label htmlFor="c0">Starting tyre</label>
                <select id="c0" value={inputs.compounds[0]} onChange={(e) => setCompound(0, e.target.value)}>
                  {base.available_compounds.map((c) => <option key={c} value={c}>{compoundLabel(c)}</option>)}
                </select>
              </div>
            )}

            {inputs.pits.map((p, i) => {
              const err = fieldErr(`pit${i + 1}`);
              const actual = base.actual_pit_laps[i];
              return (
                <div key={i} className="grid" style={{ gridTemplateColumns: base.compounds_known ? 'minmax(0, 1.6fr) minmax(0, 1fr)' : '1fr', marginBottom: 12, alignItems: 'start' }}>
                  <div className={`field ${err ? 'invalid' : ''}`}>
                    <label htmlFor={`pit${i + 1}`}>Pit Stop {i + 1}{actual ? <span className="muted" style={{ textTransform: 'none', letterSpacing: 0 }}> · actual lap {actual}</span> : ''}</label>
                    <div className="range-line">
                      <input id={`pit${i + 1}`} type="range" min={2} max={base.total_laps - 1} value={p} onChange={(e) => setPit(i, Number(e.target.value))} aria-describedby={`pit${i + 1}-err`} />
                      <div className="range-value">Lap {p}</div>
                      <button className="btn small" aria-label={`Pit Stop ${i + 1} one lap earlier`} onClick={() => setPit(i, Math.max(2, p - 1))}>−</button>
                      <button className="btn small" aria-label={`Pit Stop ${i + 1} one lap later`} onClick={() => setPit(i, Math.min(base.total_laps - 1, p + 1))}>+</button>
                    </div>
                    {err && <div className="hint err" id={`pit${i + 1}-err`} role="alert">{err}</div>}
                  </div>
                  {base.compounds_known && (
                    <div className="field">
                      <label htmlFor={`c${i + 1}`}>Tyre after Pit {i + 1}</label>
                      <select id={`c${i + 1}`} value={inputs.compounds[i + 1]} onChange={(e) => setCompound(i + 1, e.target.value)}>
                        {base.available_compounds.map((c) => <option key={c} value={c}>{compoundLabel(c)}</option>)}
                      </select>
                    </div>
                  )}
                </div>
              );
            })}

            {runError && !runError.field?.startsWith('pit') && <ErrorPanel error={runError} />}
            <button className="btn primary" style={{ width: '100%', marginTop: 4 }} disabled={hasErrors || running} onClick={run}>
              {running ? (<><Spinner />Simulating…</>) : 'Run Simulation'}
            </button>
            <div className={`progress ${running ? 'running' : ''}`}><div /></div>
            {hasErrors && <div className="sub bad" style={{ marginTop: 8 }}>Fix the highlighted input{Object.keys(errors).length > 1 ? 's' : ''} to run the simulation.</div>}
          </div>

          {result && ranWith !== JSON.stringify(inputs) && (
            <Banner tone="warn" title="Inputs changed since the last simulation">
              The result below is for the previous scenario. Click <b>Run Simulation</b> to update it.
            </Banner>
          )}
          {result && (
            <div className={`card result-card ${result.faster ? '' : 'slower'}`} aria-live="polite"
              style={ranWith !== JSON.stringify(inputs) ? { opacity: 0.5 } : undefined}>
              <div className="card-head">
                <div>
                  <span className="badge estimate">Estimate</span>
                  <div className={`headline ${result.faster ? 'good' : result.delta_s > 0 ? 'bad' : 'neutral'}`} style={{ marginTop: 8 }}>
                    {Math.abs(result.delta_s) < 0.05 ? 'No meaningful change' : `${Math.abs(result.delta_s).toFixed(1)}s ${result.faster ? 'faster' : 'slower'}`}
                  </div>
                  <div className="sub">than the actual strategy, using the same model for both</div>
                </div>
                <div className="sub" style={{ textAlign: 'right' }}>
                  Alternative: {result.alternative.compounds.map((c) => compoundLabel(c)).join(' → ')}<br />
                  Pit {result.alternative.pit_laps.map((l) => `L${l}`).join(' · ')}
                </div>
              </div>
              <div className="grid four">
                <div><div className="sub">Est. race time</div><b className="num">{fmtRaceTime(result.alternative.estimated_race_time_s)}</b></div>
                <div><div className="sub">Actual race time</div><b className="num">{fmtRaceTime(result.actual.race_time_s)}</b></div>
                <div><div className="sub">Delta vs actual</div><b className={`num ${result.faster ? 'good' : 'bad'}`}>{fmtDelta(result.delta_s, 1)}</b></div>
                <div><div className="sub">Tyre risk</div><b className={result.tyre_risk === 'High' ? 'bad' : result.tyre_risk === 'Medium' ? 'neutral' : 'good'}>{result.tyre_risk}</b></div>
              </div>
              {result.warnings.length > 0 && (
                <div className="insight warn" style={{ marginTop: 12 }}>
                  {result.warnings.map((w) => <div key={w}>⚠ {w}</div>)}
                </div>
              )}
              <div className="insight" style={{ marginTop: 12 }}>{result.explanation}</div>
              <div className="btn-row" style={{ marginTop: 14 }}>
                <button className="btn primary small" onClick={() => navigate('/insights')}>Compare Actual vs Alternative →</button>
                <button className="btn small" onClick={() => builderRef.current?.scrollIntoView({ behavior: 'smooth' })}>Modify scenario</button>
                <button className="btn small ghost" onClick={reset}>Reset</button>
              </div>
            </div>
          )}
          {!result && (
            <Banner tone="info" title="Try this">
              {base.actual_pit_laps.length
                ? <>Move Pit Stop 1 a few laps earlier than lap {base.actual_pit_laps[0]} (Undercut) or later (Overcut), then click <b>Run Simulation</b>.</>
                : <>{driver} did not stop. Add a stop with the Baseline type and click <b>Run Simulation</b>.</>}
            </Banner>
          )}
        </div>
      </div>
      <div className="mt"><NextSteps items={[{ to: '/telemetry', label: 'Telemetry' }, { to: '/tires', label: 'Tires & Stints' }]} /></div>
    </div>
  );
}
