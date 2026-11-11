import { useEffect, useState } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import { api } from '../api/client';
import { useAnalysis } from '../state/AnalysisContext';
import { Banner, ErrorPanel, Spinner } from '../components/ui';
import { SERIES } from '../lib/format';

const DEMO_DEFAULT = { season: 'demo', round: 1, session: 'R', driver_a: 'MOR', driver_b: 'COS' };

function useAsync(fn, deps) {
  const [state, setState] = useState({ data: null, loading: true, error: null });
  useEffect(() => {
    const ctrl = new AbortController();
    setState((s) => ({ ...s, loading: true, error: null }));
    fn(ctrl.signal)
      .then((data) => setState({ data, loading: false, error: null }))
      .catch((error) => {
        if (error.name !== 'AbortError') setState({ data: null, loading: false, error });
      });
    return () => ctrl.abort();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);
  return state;
}

export default function SessionSelect() {
  const { loadAnalysis, status, error: loadError, analysis, lastSelection } = useAnalysis();
  const navigate = useNavigate();
  const location = useLocation();
  const init = analysis
    ? {
        season: analysis.session.season,
        round: analysis.session.round,
        session: analysis.session.session,
        driver_a: analysis.selected.driver_a,
        driver_b: analysis.selected.driver_b || '',
      }
    : lastSelection || DEMO_DEFAULT;

  const [season, setSeason] = useState(init.season);
  const [round, setRound] = useState(init.round);
  const [session, setSession] = useState(init.session || 'R');
  const [driverA, setDriverA] = useState(init.driver_a || '');
  const [driverB, setDriverB] = useState(init.driver_b || '');
  const [reloadKey, setReloadKey] = useState(0);
  const [touched, setTouched] = useState(false);

  const seasons = useAsync((signal) => api.seasons({ signal }), [reloadKey]);
  const events = useAsync((signal) => api.events(season, { signal }), [season, reloadKey]);
  const drivers = useAsync(
    (signal) => (round ? api.drivers(season, round, { signal }) : Promise.resolve({ drivers: [] })),
    [season, round, reloadKey],
  );

  // keep event / driver selections valid when the parent selection changes
  useEffect(() => {
    const list = events.data?.events;
    if (list?.length && !list.some((e) => e.round === Number(round))) setRound(list[list.length - 1].round);
  }, [events.data]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => {
    const list = drivers.data?.drivers;
    if (!list?.length) return;
    const codes = list.map((d) => d.code);
    if (!codes.includes(driverA)) setDriverA(codes[0]);
    if (driverB && !codes.includes(driverB)) setDriverB(codes[1] || '');
  }, [drivers.data]); // eslint-disable-line react-hooks/exhaustive-deps

  const sameDriver = driverB && driverA === driverB;
  const loading = status === 'loading';
  const canLoad = !loading && driverA && round && !sameDriver && !drivers.loading && !drivers.error;
  const selectedEvent = events.data?.events?.find((e) => e.round === Number(round));

  async function onLoad(sel) {
    setTouched(true);
    try {
      await loadAnalysis(sel);
      navigate('/overview');
    } catch {
      /* error shown via loadError */
    }
  }

  const submit = (e) => {
    e.preventDefault();
    if (!canLoad) return;
    onLoad({ season, round: Number(round), session, driver_a: driverA, driver_b: driverB || null });
  };

  const fmtDriver = (d) => `${d.code} — ${d.name}${d.position ? ` (P${d.position})` : ''}`;

  return (
    <div>
      <div className="hero-row">
        <div>
          <h1>Select a historical session</h1>
          <p>Choose a completed race and up to two drivers. PitPulse AI analyses historical data — it is not live timing.</p>
        </div>
        <span className="badge"><span className="status-dot" style={{ color: 'var(--green)' }} />Historical race analysis</span>
      </div>

      {location.state?.reason === 'no-session' && !analysis && (
        <Banner tone="info" title="Load a session to open the analysis screens">
          Overview, Telemetry, Tires & Stints and Strategy Lab all use the session you select here.
        </Banner>
      )}

      <form className="control-strip" style={{ gridTemplateColumns: 'repeat(5, minmax(140px, 1fr)) auto' }} onSubmit={submit} aria-label="Session selection">
        <div className="field">
          <label htmlFor="season">Season</label>
          <select id="season" value={season} onChange={(e) => setSeason(e.target.value)} disabled={seasons.loading}>
            {(seasons.data?.seasons || [{ season: 'demo', label: 'Demo (offline)' }]).map((s) => (
              <option key={s.season} value={s.season}>{s.label}</option>
            ))}
          </select>
        </div>
        <div className={`field ${events.error ? 'invalid' : ''}`}>
          <label htmlFor="event">Event</label>
          <select id="event" value={round} onChange={(e) => setRound(Number(e.target.value))} disabled={events.loading || !!events.error}>
            {events.loading && <option>Loading events…</option>}
            {events.error && <option>Unavailable</option>}
            {events.data?.events?.map((e) => (
              <option key={e.round} value={e.round}>
                {season === 'demo' ? e.name : `R${e.round} · ${e.name}`}
              </option>
            ))}
          </select>
        </div>
        <div className="field">
          <label htmlFor="session">Session</label>
          <select id="session" value={session} onChange={(e) => setSession(e.target.value)}>
            <option value="R">Race</option>
            <option value="Q">Qualifying</option>
          </select>
        </div>
        <div className={`field ${drivers.error ? 'invalid' : ''}`}>
          <label htmlFor="driverA"><i className="swatch" style={{ background: SERIES.a, marginRight: 6 }} />Driver A</label>
          <select id="driverA" value={driverA} onChange={(e) => setDriverA(e.target.value)} disabled={drivers.loading || !!drivers.error}>
            {drivers.loading && <option>Loading drivers…</option>}
            {drivers.data?.drivers?.map((d) => (
              <option key={d.code} value={d.code}>{fmtDriver(d)}</option>
            ))}
          </select>
        </div>
        <div className={`field ${sameDriver ? 'invalid' : ''}`}>
          <label htmlFor="driverB"><i className="swatch" style={{ background: SERIES.b, marginRight: 6 }} />Driver B (optional)</label>
          <select id="driverB" value={driverB} onChange={(e) => setDriverB(e.target.value)} disabled={drivers.loading || !!drivers.error}>
            <option value="">— None —</option>
            {drivers.data?.drivers?.map((d) => (
              <option key={d.code} value={d.code}>{fmtDriver(d)}</option>
            ))}
          </select>
        </div>
        <button type="submit" className="btn primary" disabled={!canLoad} style={{ minHeight: 40 }}>
          {loading ? (<><Spinner />Loading session data…</>) : 'Load Analysis'}
        </button>
      </form>
      {sameDriver && <div className="field"><div className="hint err" style={{ marginTop: -8, marginBottom: 12 }}>Driver B must be different from Driver A (or choose “None”).</div></div>}

      {loading && (
        <div className="card" style={{ marginBottom: 16 }}>
          <div className="btn-row"><Spinner /><b>Preparing analysis…</b></div>
          <div className="sub" style={{ marginTop: 6 }}>
            {season === 'demo'
              ? 'Loading the seeded demo session.'
              : 'Fetching lap timing from the historical data service and processing stints. The first load of a real race can take 10–30 seconds; repeat loads come from the cache.'}
          </div>
          <div className="progress running"><div /></div>
        </div>
      )}

      {touched && loadError && !loading && (
        <ErrorPanel
          error={loadError}
          onRetry={() => onLoad({ season, round: Number(round), session, driver_a: driverA, driver_b: driverB || null })}
          actions={
            <button className="btn small" onClick={() => { setSeason('demo'); setRound(1); setSession('R'); }}>
              Use Demo season
            </button>
          }
        />
      )}
      {seasons.error && <ErrorPanel error={seasons.error} onRetry={() => setReloadKey((k) => k + 1)} />}
      {events.error && <ErrorPanel error={events.error} onRetry={() => setReloadKey((k) => k + 1)} actions={<button className="btn small" onClick={() => setSeason('demo')}>Use Demo season</button>} />}
      {drivers.error && !events.error && <ErrorPanel error={drivers.error} onRetry={() => setReloadKey((k) => k + 1)} />}

      <div className="grid halves">
        <div className="card">
          <h3>{season === 'demo' ? 'About the demo season' : 'About historical data'}</h3>
          {season === 'demo' ? (
            <p className="sub">
              The <b>PitPulse Demo Grand Prix</b> is a fictional, seeded race with full lap, sector, tyre and telemetry data. It always works offline
              and is labelled <span className="badge demo" style={{ padding: '1px 8px' }}>Demo data</span> on every screen. The
              <b> Limited Data</b> demo event deliberately hides telemetry and some tyre compounds so you can see how PitPulse handles missing data.
            </p>
          ) : (
            <p className="sub">
              Real race results, lap times, running positions and pit stops are retrieved through FastF1's historical (Ergast/Jolpica) interface.
              Car telemetry, sector times and tyre compounds need the official F1 timing archive, which requires F1 account credentials on the server — without them those
              views clearly show as unavailable. Lap-by-lap data is available for <b>Race</b> sessions.
            </p>
          )}
          {selectedEvent && (
            <div className="metric-row"><span>Selected event</span><span>{selectedEvent.name}{selectedEvent.date ? ` · ${selectedEvent.date}` : ''}</span></div>
          )}
          {selectedEvent?.circuit && <div className="metric-row"><span>Circuit</span><span>{selectedEvent.circuit}</span></div>}
        </div>
        <div className="card">
          <h3>Recommended walkthrough</h3>
          <p className="sub" style={{ marginBottom: 10 }}>A predictable path through every feature:</p>
          <div className="flow">
            <b>Overview</b> → <b>Telemetry</b> → <b>Tires & Stints</b> → <b>Strategy Lab</b> → <b>Comparison</b>
          </div>
          <div className="btn-row" style={{ marginTop: 14 }}>
            <button className="btn primary small" disabled={loading} onClick={() => onLoad(DEMO_DEFAULT)}>
              Load demo: Morgan vs Costa
            </button>
            <button
              className="btn small"
              disabled={loading}
              onClick={() => { setSeason('2023'); setRound(1); setSession('R'); setDriverA('VER'); setDriverB('ALO'); }}
            >
              Try real race: 2023 Bahrain
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
