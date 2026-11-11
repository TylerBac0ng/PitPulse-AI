import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import App from '../App';
import { AnalysisProvider } from '../state/AnalysisContext';
import { validatePlan } from '../pages/StrategyLab';
import { fmtDelta, fmtLap, fmtRaceTime, sessionLabel } from '../lib/format';
import { buildExport, exportFilename } from '../lib/export';

const analysis = {
  session: {
    key: 'demo-1-R', season: 'demo', round: 1, event_name: 'PitPulse Demo Grand Prix', session: 'R', session_name: 'Race',
    circuit: 'Harbor Park', total_laps: 3, source: 'demo', source_label: 'Seeded demo data', is_demo: true,
    availability: { lap_times: true, sectors: true, compounds: true, telemetry: true, positions: true }, notes: [],
  },
  drivers: [{ code: 'MOR', name: 'Alex Morgan' }, { code: 'COS', name: 'Luca Costa' }],
  selected: { driver_a: 'MOR', driver_b: null },
  summaries: { MOR: { code: 'MOR', name: 'Alex Morgan', grid: 6, position: 5, status: 'Finished', laps_completed: 3, best_lap: { lap: 2, time_s: 92.7 }, avg_clean_pace_s: 93, clean_lap_count: 1, pit_count: 1, pit_laps: [2], total_time_s: 280, points: 10 } },
  comparison: null,
  lap_series: [{ lap: 1, MOR: 98, MOR_clean: false }, { lap: 2, MOR: 92.7, MOR_clean: true }, { lap: 3, MOR: 110, MOR_clean: false }],
  stints: { MOR: [{ stint: 1, compound: 'SOFT', compound_known: true, start_lap: 1, end_lap: 2, length: 2, pit_lap: 2, ended_with_pit: true, trend: 'Stable', points: [] }, { stint: 2, compound: 'HARD', compound_known: true, start_lap: 3, end_lap: 3, length: 1, pit_lap: null, trend: 'Insufficient data', points: [] }] },
  stint_insights: { MOR: 'Not enough clean laps.' },
  laps: { MOR: [] },
  lap_counts: { MOR: 3, COS: 3 },
  pit_stops: { MOR: [] },
  fallback: null,
};

function renderAt(path, initial = null) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <AnalysisProvider initial={initial}>
        <App />
      </AnalysisProvider>
    </MemoryRouter>,
  );
}

describe('navigation', () => {
  beforeEach(() => {
    sessionStorage.clear();
    globalThis.fetch = vi.fn(async (url) => ({
      ok: true,
      json: async () => (String(url).includes('/seasons/demo/events/') ? { drivers: analysis.drivers } : String(url).includes('/events') ? { events: [{ round: 1, name: 'PitPulse Demo Grand Prix' }] } : { seasons: [{ season: 'demo', label: 'Demo (offline)' }] }),
    }));
  });
  afterEach(() => vi.restoreAllMocks());

  it('redirects analysis screens to session selection when nothing is loaded', async () => {
    renderAt('/telemetry');
    expect(await screen.findByRole('heading', { name: /select a historical session/i })).toBeInTheDocument();
    expect(screen.getByText(/load a session to open the analysis screens/i)).toBeInTheDocument();
  });

  it('disables analysis navigation before a session is loaded', async () => {
    renderAt('/');
    const nav = screen.getByRole('complementary', { name: /main navigation/i });
    expect(within(nav).getByText('Telemetry').closest('[aria-disabled]')).toHaveAttribute('aria-disabled', 'true');
    expect(await screen.findByRole('button', { name: 'Load Analysis' })).toBeInTheDocument();
  });

  it('shows the active session, drivers and current screen once loaded', async () => {
    renderAt('/overview', analysis);
    expect(screen.getByRole('heading', { name: /PitPulse Demo Grand Prix — Race/ })).toBeInTheDocument();
    expect(screen.getByText('Demo data')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Change Session' })).toBeInTheDocument();
    const nav = screen.getByRole('complementary', { name: /main navigation/i });
    expect(within(nav).getByRole('link', { name: /Overview/ })).toHaveClass('active');
  });

  it('navigates between analysis screens from the sidebar', async () => {
    const user = userEvent.setup();
    renderAt('/overview', analysis);
    const nav = screen.getByRole('complementary', { name: /main navigation/i });
    await user.click(within(nav).getByRole('link', { name: /Comparison/ }));
    expect(await screen.findByText(/no strategy scenario yet/i)).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Open Strategy Lab' })).toBeInTheDocument();
  });
});

describe('strategy validation (client mirror of API rules)', () => {
  const base = { totalLaps: 52, minStint: 3, type: 'baseline', actualFirst: 17 };
  it('accepts a valid plan', () => expect(validatePlan({ ...base, pits: [14, 36] })).toEqual({}));
  it('requires pit 2 after pit 1', () => expect(validatePlan({ ...base, pits: [30, 20] }).pit2).toBe('Pit Stop 2 must occur after Pit Stop 1.'));
  it('enforces the minimum stint length', () => expect(validatePlan({ ...base, pits: [20, 21] }).pit2).toMatch(/at least 3 laps/));
  it('checks undercut direction', () => expect(validatePlan({ ...base, type: 'undercut', pits: [18, 39] }).pit1).toMatch(/before the actual first stop/));
  it('checks overcut direction', () => expect(validatePlan({ ...base, type: 'overcut', pits: [15, 39] }).pit1).toMatch(/after the actual first stop/));
  it('rejects undercut when the driver never pitted', () => expect(validatePlan({ ...base, actualFirst: undefined, type: 'undercut', pits: [20] }).type).toBeTruthy());
});

describe('formatting', () => {
  it('formats lap and race times', () => {
    expect(fmtLap(92.713)).toBe('1:32.713');
    expect(fmtLap(null)).toBe('—');
    expect(fmtRaceTime(4910.5)).toBe('1:21:50.5');
  });
  it('formats deltas with explicit sign', () => {
    expect(fmtDelta(0.159)).toBe('+0.159s');
    expect(fmtDelta(-0.2, 1)).toBe('−0.2s');
  });
  it('omits the season prefix for demo sessions', () => {
    expect(sessionLabel(analysis.session)).toBe('PitPulse Demo Grand Prix · Race');
    expect(sessionLabel({ ...analysis.session, season: '2023', event_name: 'Bahrain Grand Prix' })).toBe('2023 Bahrain Grand Prix · Race');
  });
});

describe('export (UC-11)', () => {
  it('packages the visible analysis without chart-only series', () => {
    const out = buildExport(analysis, null);
    expect(out.session.demo_data).toBe(true);
    expect(out.drivers.driver_a).toBe('MOR');
    expect(out.stints.MOR[0]).not.toHaveProperty('points');
    expect(out.strategy_scenario).toBeNull();
    expect(out.note).toMatch(/estimates/);
    expect(exportFilename(analysis)).toBe('pitpulse_demo-1-R_MOR.json');
  });
});
