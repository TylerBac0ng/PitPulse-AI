import { useEffect } from 'react';
import { Link, NavLink, Navigate, Outlet, useLocation, useNavigate } from 'react-router-dom';
import { useAnalysis } from '../state/AnalysisContext';
import { SERIES, sessionLabel } from '../lib/format';
import { downloadExport } from '../lib/export';
import { Banner, DriverPill, LoadingPanel, SourceBadge, Toast } from './ui';
import ErrorBoundary from './ErrorBoundary';

export const NAV_ITEMS = [
  { to: '/overview', label: 'Overview' },
  { to: '/telemetry', label: 'Telemetry' },
  { to: '/tires', label: 'Tires & Stints' },
  { to: '/strategy', label: 'Strategy Lab' },
  { to: '/insights', label: 'Comparison / Insights' },
];

const TITLES = {
  '/': 'Select Session',
  '/overview': 'Overview',
  '/telemetry': 'Telemetry',
  '/tires': 'Tires & Stints',
  '/strategy': 'Strategy Lab',
  '/insights': 'Comparison / Insights',
};

function Sidebar() {
  const { analysis } = useAnalysis();
  return (
    <aside className="sidebar-col" aria-label="Main navigation">
     <div className="sidebar">
      <Link to="/" className="brand">
        <div className="brand-mark" />
        <div>
          <strong>PitPulse AI</strong>
          <small>Historical F1 Analytics</small>
        </div>
      </Link>
      <nav className="nav">
        <NavLink to="/" end title="Select Session">
          <span className="dot" />
          <span className="label-text">Select Session</span>
        </NavLink>
        <div className="nav-label">Analysis</div>
        {NAV_ITEMS.map((item, i) =>
          analysis ? (
            <NavLink key={item.to} to={item.to} title={item.label}>
              <span className="dot" />
              <span className="label-text">{item.label}</span>
              <span className="step">{i + 1}</span>
            </NavLink>
          ) : (
            <span key={item.to} className="nav-disabled" title="Load a session first" aria-disabled="true">
              <span className="dot" />
              <span className="label-text">{item.label}</span>
            </span>
          ),
        )}
      </nav>
      <div className="side-note">
        <b>Historical analysis only.</b>
        <br />
        PitPulse AI analyses completed sessions. It is not live timing, and strategy results are estimates.
      </div>
     </div>
    </aside>
  );
}

function Topbar() {
  const { analysis, strategy, notify } = useAnalysis();
  const onExport = () => {
    try {
      const name = downloadExport(analysis, strategy);
      notify(`Exported ${name}${strategy?.result ? ' (includes strategy scenario)' : ''}.`, 'success');
    } catch {
      notify('Export failed — your analysis is unchanged. Please try again.', 'error');
    }
  };
  const { pathname } = useLocation();
  const navigate = useNavigate();
  const meta = analysis?.session;
  const sel = analysis?.selected;
  return (
    <header className="topbar">
      <div className="crumbs">
        PitPulse AI / <b>{TITLES[pathname] || 'PitPulse AI'}</b>
      </div>
      {meta ? (
        <div className="session-chip">
          <SourceBadge meta={meta} />
          <span className="title" title={sessionLabel(meta)}>{sessionLabel(meta)}</span>
          <DriverPill code={sel.driver_a} color={SERIES.a} />
          {sel.driver_b && <DriverPill code={sel.driver_b} color={SERIES.b} />}
          <button className="btn ghost small" onClick={() => navigate('/')}>
            Change Session
          </button>
          <button className="btn small" onClick={onExport} title="Download the current analysis and strategy result as JSON">
            Export Results
          </button>
        </div>
      ) : (
        <div className="session-chip">
          <span className="badge"><span className="status-dot" style={{ color: 'var(--muted)' }} />No session loaded</span>
        </div>
      )}
    </header>
  );
}

export function AppLayout() {
  const { toast } = useAnalysis();
  const { pathname } = useLocation();
  useEffect(() => {
    window.scrollTo(0, 0);
  }, [pathname]);
  return (
    <div className="app">
      <Sidebar />
      <main className="main">
        <Topbar />
        <div className="content">
          <ErrorBoundary resetKey={pathname}>
            <Outlet />
          </ErrorBoundary>
        </div>
      </main>
      <Toast toast={toast} />
    </div>
  );
}

/** Guards analysis screens: they need a loaded session. */
export function RequireAnalysis({ children }) {
  const { analysis, status } = useAnalysis();
  if (analysis) {
    return (
      <>
        {analysis.fallback && (
          <Banner tone="warn" title="Showing demo data — the requested historical session could not be loaded">
            <ul>
              <li><b>Requested:</b> {analysis.fallback.requested}. {analysis.fallback.reason}</li>
              <li><b>Still available:</b> every screen works with the fictional PitPulse Demo Grand Prix shown here.</li>
              <li><b>Next step:</b> <Link to="/">Change Session</Link> to try again later or choose another event.</li>
            </ul>
          </Banner>
        )}
        {children}
      </>
    );
  }
  if (status === 'loading') return <LoadingPanel label="Restoring your session…" detail="Fetching and processing historical race data." />;
  return <Navigate to="/" replace state={{ reason: 'no-session' }} />;
}
