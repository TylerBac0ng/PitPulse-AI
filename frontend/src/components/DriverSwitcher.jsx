import { useEffect, useState } from 'react';
import { useAnalysis } from '../state/AnalysisContext';
import { SERIES } from '../lib/format';
import { ErrorPanel, Spinner } from './ui';

/** Compact Driver A / Driver B selector for the loaded session (no full reload needed). */
export default function DriverSwitcher() {
  const { analysis, changeDrivers } = useAnalysis();
  const [a, setA] = useState(analysis.selected.driver_a);
  const [b, setB] = useState(analysis.selected.driver_b || '');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);

  useEffect(() => {
    setA(analysis.selected.driver_a);
    setB(analysis.selected.driver_b || '');
  }, [analysis.selected.driver_a, analysis.selected.driver_b]);

  const dirty = a !== analysis.selected.driver_a || (b || null) !== (analysis.selected.driver_b || null);
  const same = b && a === b;

  async function apply() {
    setBusy(true);
    setError(null);
    try {
      await changeDrivers(a, b || null);
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <div className="control-strip" style={{ gridTemplateColumns: 'minmax(180px, 260px) minmax(180px, 260px) auto auto', justifyContent: 'start' }}>
        <div className="field">
          <label htmlFor="sw-a"><i className="swatch" style={{ background: SERIES.a, marginRight: 6 }} />Driver A</label>
          <select id="sw-a" value={a} onChange={(e) => setA(e.target.value)}>
            {analysis.drivers.map((d) => (
              <option key={d.code} value={d.code}>{d.code} — {d.name}</option>
            ))}
          </select>
        </div>
        <div className={`field ${same ? 'invalid' : ''}`}>
          <label htmlFor="sw-b"><i className="swatch" style={{ background: SERIES.b, marginRight: 6 }} />Driver B</label>
          <select id="sw-b" value={b} onChange={(e) => setB(e.target.value)}>
            <option value="">— None —</option>
            {analysis.drivers.map((d) => (
              <option key={d.code} value={d.code}>{d.code} — {d.name}</option>
            ))}
          </select>
        </div>
        <button className="btn" disabled={!dirty || same || busy} onClick={apply} style={{ minHeight: 40 }}>
          {busy ? (<><Spinner />Updating…</>) : 'Apply drivers'}
        </button>
        <div className="sub" style={{ alignSelf: 'center' }}>
          {same ? <span className="bad">Choose two different drivers.</span> : dirty ? 'Apply to update every screen.' : 'Same session — switch drivers instantly.'}
        </div>
      </div>
      {error && <ErrorPanel error={error} />}
    </>
  );
}
