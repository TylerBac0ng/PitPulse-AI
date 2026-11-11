import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from 'react';
import { api } from '../api/client';

const AnalysisContext = createContext(null);
const STORAGE_KEY = 'pitpulse.selection';

function readStored() {
  try {
    const raw = sessionStorage.getItem(STORAGE_KEY);
    return raw ? JSON.parse(raw) : null;
  } catch {
    return null;
  }
}

function writeStored(sel) {
  try {
    if (sel) sessionStorage.setItem(STORAGE_KEY, JSON.stringify(sel));
    else sessionStorage.removeItem(STORAGE_KEY);
  } catch {
    /* storage unavailable: fine, selection just won't survive a refresh */
  }
}

/**
 * Holds the active session analysis and the latest strategy scenario so every screen
 * shares the same session, drivers and results.
 */
export function AnalysisProvider({ children, initial = null }) {
  const [analysis, setAnalysis] = useState(initial);
  // 'loading' straight away when a previous session will be restored, so guards don't redirect first
  const [status, setStatus] = useState(() => (initial ? 'ready' : readStored() ? 'loading' : 'idle'));
  const [error, setError] = useState(null);
  const [strategy, setStrategy] = useState(null); // { driver, inputs, result }
  const [toast, setToast] = useState(null);
  const toastTimer = useRef(null);

  const notify = useCallback((message, tone = 'info') => {
    setToast({ message, tone, id: Date.now() });
    clearTimeout(toastTimer.current);
    toastTimer.current = setTimeout(() => setToast(null), 3200);
  }, []);

  const loadAnalysis = useCallback(
    async (selection) => {
      setStatus('loading');
      setError(null);
      try {
        const data = await api.load(selection);
        setAnalysis(data);
        setStrategy(null);
        setStatus('ready');
        writeStored({
          ...selection,
          season: data.session.season,
          round: data.session.round,
          session: data.session.session,
          driver_a: data.selected.driver_a,
          driver_b: data.selected.driver_b,
        });
        if (data.fallback) notify('Historical data unavailable — showing the demo session instead.', 'warn');
        else notify(`Loaded ${data.session.event_name} · ${data.session.session_name}${data.cached ? ' (cached)' : ''}.`, 'success');
        return data;
      } catch (err) {
        setError(err);
        setStatus(analysis ? 'ready' : 'error');
        throw err;
      }
    },
    [analysis, notify],
  );

  const changeDrivers = useCallback(
    async (driverA, driverB) => {
      if (!analysis) return;
      const data = await api.overview(analysis.session.key, driverA, driverB || null);
      setAnalysis({ ...data, fallback: analysis.fallback });
      setStrategy(null);
      const stored = readStored();
      if (stored) writeStored({ ...stored, driver_a: driverA, driver_b: driverB || null });
      notify(`Comparing ${driverA}${driverB ? ` vs ${driverB}` : ''}.`, 'success');
    },
    [analysis, notify],
  );

  const clearAnalysis = useCallback(() => {
    setAnalysis(null);
    setStrategy(null);
    setStatus('idle');
    setError(null);
  }, []);

  // Restore the last loaded session after a page refresh.
  useEffect(() => {
    if (analysis) return;
    const stored = readStored();
    if (stored) loadAnalysis(stored).catch(() => writeStored(null));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const value = useMemo(
    () => ({
      analysis,
      status,
      error,
      strategy,
      setStrategy,
      loadAnalysis,
      changeDrivers,
      clearAnalysis,
      lastSelection: readStored(),
      toast,
      notify,
    }),
    [analysis, status, error, strategy, loadAnalysis, changeDrivers, clearAnalysis, toast, notify],
  );
  return <AnalysisContext.Provider value={value}>{children}</AnalysisContext.Provider>;
}

export function useAnalysis() {
  const ctx = useContext(AnalysisContext);
  if (!ctx) throw new Error('useAnalysis must be used inside AnalysisProvider');
  return ctx;
}
