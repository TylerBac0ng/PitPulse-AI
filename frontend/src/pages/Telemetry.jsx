import { useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { api } from '../api/client';
import { useAnalysis } from '../state/AnalysisContext';
import { CHANNEL_META, DeltaTrace, MiniSectorBars, TelemetryOverlay } from '../components/charts';
import { Banner, EmptyState, ErrorPanel, Kpi, LoadingPanel, NextSteps, Spinner } from '../components/ui';
import { SERIES, compoundLabel, deltaClass, fmtDelta, fmtLap } from '../lib/format';

const CHANNELS = ['speed', 'throttle', 'brake', 'rpm', 'gear'];

function bestLap(laps) {
  const clean = (laps || []).filter((l) => l.clean && l.time_s);
  if (!clean.length) return laps?.find((l) => l.time_s)?.lap || 1;
  return clean.reduce((m, l) => (l.time_s < m.time_s ? l : m)).lap;
}

function LapSelect({ id, label, driver, value, onChange, analysis }) {
  const detailed = analysis.laps[driver];
  const count = analysis.lap_counts?.[driver] || 0;
  const options = detailed
    ? detailed.map((l) => ({
        lap: l.lap,
        text: `Lap ${l.lap} · ${fmtLap(l.time_s)}${l.compound ? ` · ${compoundLabel(l.compound)}` : ''}${l.pit_in ? ' · in-lap' : l.pit_out ? ' · out-lap' : ''}${l.lap === bestLap(detailed) ? ' · best' : ''}`,
      }))
    : Array.from({ length: count }, (_, i) => ({ lap: i + 1, text: `Lap ${i + 1}` }));
  return (
    <div className={`field ${!value ? 'invalid' : ''}`}>
      <label htmlFor={id}>{label}</label>
      <select id={id} value={value || ''} onChange={(e) => onChange(Number(e.target.value) || null)}>
        <option value="">— Select lap —</option>
        {options.map((o) => (
          <option key={o.lap} value={o.lap}>{o.text}</option>
        ))}
      </select>
    </div>
  );
}

export default function Telemetry() {
  const { analysis } = useAnalysis();
  const meta = analysis.session;
  const sel = analysis.selected;
  const defaultB = sel.driver_b || sel.driver_a;
  const [driverA, setDriverA] = useState(sel.driver_a);
  const [driverB, setDriverB] = useState(defaultB);
  const [lapA, setLapA] = useState(bestLap(analysis.laps[sel.driver_a]));
  const [lapB, setLapB] = useState(() => {
    if (sel.driver_b) return bestLap(analysis.laps[sel.driver_b]);
    const clean = (analysis.laps[sel.driver_a] || []).filter((l) => l.clean && l.time_s).sort((x, y) => x.time_s - y.time_s);
    return clean[1]?.lap || 2; // single driver: compare best vs second-best lap
  });
  const [channel, setChannel] = useState('speed');
  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [selectedMini, setSelectedMini] = useState(null);
  const [retry, setRetry] = useState(0);

  const ready = driverA && driverB && lapA && lapB;

  useEffect(() => {
    if (!ready) {
      setResult(null);
      return undefined;
    }
    const ctrl = new AbortController();
    setLoading(true);
    setError(null);
    setSelectedMini(null);
    api
      .telemetry(meta.key, { driver_a: driverA, lap_a: lapA, driver_b: driverB, lap_b: lapB }, { signal: ctrl.signal })
      .then((r) => {
        setResult(r);
        if (r.telemetry_available && !r.available_channels.includes(channel)) setChannel(r.available_channels[0]);
      })
      .catch((e) => e.name !== 'AbortError' && setError(e))
      .finally(() => !ctrl.signal.aborted && setLoading(false));
    return () => ctrl.abort();
  }, [meta.key, driverA, driverB, lapA, lapB, ready, retry]); // eslint-disable-line react-hooks/exhaustive-deps

  const nameA = `${driverA} L${lapA ?? '?'}`;
  const nameB = `${driverB} L${lapB ?? '?'}`;
  const m = result?.metrics;
  const sameLap = driverA === driverB && lapA === lapB;

  const onDriverChange = (which, code) => {
    const best = analysis.laps[code] ? bestLap(analysis.laps[code]) : null;
    if (which === 'a') { setDriverA(code); setLapA(best); } else { setDriverB(code); setLapB(best); }
  };
  const swap = () => { setDriverA(driverB); setDriverB(driverA); setLapA(lapB); setLapB(lapA); };
  const bestBoth = () => {
    if (analysis.laps[driverA]) setLapA(bestLap(analysis.laps[driverA]));
    if (analysis.laps[driverB]) setLapB(bestLap(analysis.laps[driverB]));
  };

  const sectorCards = useMemo(() => m?.sectors?.filter((s) => s.delta_s !== null) || [], [m]);

  return (
    <div>
      <div className="hero-row">
        <div>
          <h1>Telemetry comparison</h1>
          <p>Overlay two laps to see where performance differs. Positive deltas mean Driver A ({driverA}) is slower.</p>
        </div>
        <NextSteps items={[{ to: '/overview', label: 'Back to Overview' }, { to: '/tires', label: 'View Tire Context', primary: true }]} />
      </div>

      <div className="card" style={{ marginBottom: 16 }}>
        <div className="grid" style={{ gridTemplateColumns: 'repeat(4, minmax(0, 1fr)) auto', alignItems: 'end' }}>
          <div className="field">
            <label htmlFor="tdA"><i className="swatch" style={{ background: SERIES.a, marginRight: 6 }} />Driver A</label>
            <select id="tdA" value={driverA} onChange={(e) => onDriverChange('a', e.target.value)}>
              {analysis.drivers.map((d) => <option key={d.code} value={d.code}>{d.code} — {d.name}</option>)}
            </select>
          </div>
          <LapSelect id="tlA" label="Lap A" driver={driverA} value={lapA} onChange={setLapA} analysis={analysis} />
          <div className="field">
            <label htmlFor="tdB"><i className="swatch" style={{ background: SERIES.b, marginRight: 6 }} />Driver B</label>
            <select id="tdB" value={driverB} onChange={(e) => onDriverChange('b', e.target.value)}>
              {analysis.drivers.map((d) => <option key={d.code} value={d.code}>{d.code} — {d.name}</option>)}
            </select>
          </div>
          <LapSelect id="tlB" label="Lap B" driver={driverB} value={lapB} onChange={setLapB} analysis={analysis} />
          <div className="btn-row">
            <button className="btn small" onClick={bestBoth} title="Select each driver's fastest representative lap">Best laps</button>
            <button className="btn small" onClick={swap}>Swap</button>
          </div>
        </div>
        {result?.telemetry_available && (
          <div className="tabs" style={{ marginTop: 14 }} role="tablist" aria-label="Telemetry channel">
            {CHANNELS.map((c) => {
              const ok = result.available_channels.includes(c);
              return (
                <button key={c} role="tab" aria-selected={channel === c} className={`tab ${channel === c ? 'active' : ''} ${ok ? '' : 'unavailable'}`}
                  disabled={!ok} title={ok ? '' : `${CHANNEL_META[c].label} is not available for these laps`} onClick={() => setChannel(c)}>
                  {CHANNEL_META[c].label}
                </button>
              );
            })}
            <span className="tab" style={{ cursor: 'default' }} title="All channels are plotted against lap distance">Distance (x-axis)</span>
          </div>
        )}
      </div>

      {!ready && (
        <EmptyState title="Select two laps to compare">
          Choose a lap for both Driver A and Driver B. Tip: “Best laps” picks each driver's fastest representative lap.
          <div className="btn-row"><button className="btn small primary" onClick={bestBoth}>Use best laps</button></div>
        </EmptyState>
      )}
      {sameLap && ready && <Banner tone="info" title="Both selections are the same lap">The traces will overlap exactly. Pick a different lap or driver to see a comparison.</Banner>}
      {error && <ErrorPanel error={error} onRetry={() => setRetry((r) => r + 1)} />}
      {result?.notes?.length > 0 && (
        <Banner tone="warn" title="Non-representative lap selected">
          <ul>{result.notes.map((n) => <li key={n}>{n}</li>)}</ul>
        </Banner>
      )}

      {ready && loading && !result && <LoadingPanel label="Loading telemetry…" detail="Aligning both laps on a common distance grid." />}

      {ready && result && !result.telemetry_available && (
        <>
          <Banner tone="warn" title={result.unavailable.message}>
            <ul>
              <li><b>Still available:</b> {result.unavailable.still_available}</li>
              <li><b>Next step:</b> {result.unavailable.next_action}</li>
            </ul>
          </Banner>
          <div className="grid four">
            <Kpi label={`${nameA} lap time`} value={fmtLap(m.lap_time_a)} />
            <Kpi label={`${nameB} lap time`} value={fmtLap(m.lap_time_b)} />
            <Kpi label="Lap-time delta (A − B)" value={fmtDelta(m.lap_time_delta_s)} tone={deltaClass(m.lap_time_delta_s)}
              delta={m.lap_time_delta_s == null ? '' : m.lap_time_delta_s < 0 ? `${driverA} faster` : `${driverB} faster`} />
            <Kpi label="Sector deltas" value={m.sectors.some((s) => s.delta_s != null) ? 'See below' : 'Unavailable'} delta={m.sectors.some((s) => s.delta_s != null) ? '' : 'No sector times in this source'} />
          </div>
          {m.sectors.some((s) => s.delta_s != null) && (
            <div className="grid three mt">
              {m.sectors.map((s) => (
                <Kpi key={s.sector} label={`Sector ${s.sector}`} value={fmtDelta(s.delta_s)} tone={deltaClass(s.delta_s)} delta={`${fmtLap(s.a_s)} vs ${fmtLap(s.b_s)}`} />
              ))}
            </div>
          )}
          <div className="btn-row mt">
            <Link to="/tires" className="btn primary">View Tire Context →</Link>
          </div>
        </>
      )}

      {ready && result?.telemetry_available && (
        <div style={{ opacity: loading ? 0.55 : 1, transition: 'opacity .15s' }}>
          <div className="card" style={{ marginBottom: 16 }}>
            <div className="card-head">
              <div>
                <h3>{CHANNEL_META[channel].label} — {nameA} vs {nameB}</h3>
                <div className="sub">Lap distance (km) · {CHANNEL_META[channel].unit}{selectedMini ? ` · highlighted: mini-sector ${selectedMini.index} (${selectedMini.start_m}–${selectedMini.end_m} m)` : ''}</div>
              </div>
              <div className="legend">
                {loading && <span><Spinner /> Updating…</span>}
                <span><i className="line-key" style={{ background: SERIES.a }} />{nameA}</span>
                <span><i className="line-key" style={{ background: SERIES.b }} />{nameB}</span>
              </div>
            </div>
            <TelemetryOverlay distance={result.distance} channel={channel} data={result.channels[channel]} nameA={nameA} nameB={nameB} highlight={selectedMini} />
          </div>

          <div className="grid halves" style={{ marginBottom: 16 }}>
            <div className="card">
              <h3>Running time delta</h3>
              <div className="sub">Elapsed time {driverA} minus {driverB} at the same distance. Rising = {driverA} losing time.</div>
              {result.delta ? <DeltaTrace distance={result.distance} delta={result.delta} nameA={driverA} nameB={driverB} /> : <div className="sub">Time channel unavailable.</div>}
            </div>
            <div className="card">
              <h3>Where time is gained or lost</h3>
              <div className="sub">20 equal mini-sectors. Red = {driverA} loses time, green = {driverA} gains. Click a bar to highlight it on the trace.</div>
              <MiniSectorBars sectors={result.mini_sectors} nameA={driverA} selected={selectedMini} onSelect={setSelectedMini} />
            </div>
          </div>

          <div className="insight" style={{ marginBottom: 16 }}>{result.insight}</div>

          <div className="grid four">
            <Kpi label="Lap-time delta (A − B)" value={fmtDelta(m.lap_time_delta_s)} tone={deltaClass(m.lap_time_delta_s)}
              delta={`${fmtLap(m.lap_time_a)} vs ${fmtLap(m.lap_time_b)}`} />
            {sectorCards.length ? (
              sectorCards.map((s) => (
                <Kpi key={s.sector} label={`Sector ${s.sector} delta`} value={fmtDelta(s.delta_s)} tone={deltaClass(s.delta_s)}
                  delta={`${fmtLap(s.a_s)} vs ${fmtLap(s.b_s)}`} />
              ))
            ) : (
              <Kpi label="Sector deltas" value="Unavailable" delta="No sector times for these laps" />
            )}
          </div>
          <div className="grid four mt">
            <Kpi label="Top speed (A / B)" value={`${m.a.top_speed?.toFixed(0) ?? '—'} / ${m.b.top_speed?.toFixed(0) ?? '—'}`} delta={`${fmtDelta(m.top_speed_delta, 1, ' km/h')}`} tone={deltaClass(m.top_speed_delta, false)} />
            <Kpi label="Min speed (A / B)" value={`${m.a.min_speed?.toFixed(0) ?? '—'} / ${m.b.min_speed?.toFixed(0) ?? '—'}`} delta={`${fmtDelta(m.min_speed_delta, 1, ' km/h')}`} tone={deltaClass(m.min_speed_delta, false)} />
            <Kpi label="Full throttle (A / B)" value={m.a.full_throttle_pct != null ? `${m.a.full_throttle_pct.toFixed(0)}% / ${m.b.full_throttle_pct.toFixed(0)}%` : '—'} delta="Share of lap distance ≥ 98%" />
            <Kpi label="Braking zones (A / B)" value={m.a.brake_zones != null ? `${m.a.brake_zones} / ${m.b.brake_zones}` : '—'} delta="Distinct brake applications" />
          </div>
          {result.missing_channels.length > 0 && (
            <div className="sub mt">Unavailable channels for these laps: {result.missing_channels.map((c) => CHANNEL_META[c].label).join(', ')}.</div>
          )}
          {meta.is_demo && <div className="sub mt">Demo telemetry is synthesised from a simple kinematic model of a fictional circuit — it is not real car data.</div>}
          <div className="btn-row mt">
            <Link to="/tires" className="btn primary">View Tire Context →</Link>
          </div>
        </div>
      )}
    </div>
  );
}
