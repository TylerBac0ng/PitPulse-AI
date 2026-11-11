// Export Service (Architecture Spec §5, UC-11): packages already-computed results for download.
// Runs client-side and never changes analysis state.

const stripPoints = (stints) => stints.map(({ points, ...rest }) => rest); // eslint-disable-line no-unused-vars

export function buildExport(analysis, strategy) {
  const { session, selected, summaries, comparison, stints, stint_insights: insights, pit_stops: pitStops, fallback } = analysis;
  return {
    app: 'PitPulse AI',
    exported_at: new Date().toISOString(),
    note: 'Historical race analysis. Strategy values are model estimates, not race predictions.',
    session: {
      key: session.key,
      season: session.season,
      event: session.event_name,
      session: session.session_name,
      circuit: session.circuit,
      total_laps: session.total_laps,
      data_source: session.source_label,
      demo_data: session.is_demo,
      availability: session.availability,
      fallback: fallback || null,
    },
    drivers: selected,
    summaries,
    comparison: comparison ? { ...comparison, gap_series: undefined } : null,
    stints: Object.fromEntries(Object.entries(stints).map(([code, list]) => [code, stripPoints(list)])),
    stint_insights: insights,
    pit_stops: pitStops,
    strategy_scenario: strategy?.result
      ? {
          driver: strategy.result.driver,
          strategy_type: strategy.result.strategy_type,
          label: strategy.result.label,
          actual: { pit_laps: strategy.result.actual.pit_laps, compounds: strategy.result.actual.compounds, race_time_s: strategy.result.actual.race_time_s },
          alternative: {
            pit_laps: strategy.result.alternative.pit_laps,
            compounds: strategy.result.alternative.compounds,
            estimated_race_time_s: strategy.result.alternative.estimated_race_time_s,
          },
          delta_s: strategy.result.delta_s,
          breakdown: strategy.result.breakdown,
          tyre_risk: strategy.result.tyre_risk,
          warnings: strategy.result.warnings,
          explanation: strategy.result.explanation,
          assumptions: strategy.result.model.assumptions,
        }
      : null,
  };
}

export function exportFilename(analysis) {
  const { driver_a: a, driver_b: b } = analysis.selected;
  return `pitpulse_${analysis.session.key}_${a}${b ? `_vs_${b}` : ''}.json`;
}

export function downloadExport(analysis, strategy) {
  const blob = new Blob([JSON.stringify(buildExport(analysis, strategy), null, 2)], { type: 'application/json' });
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = exportFilename(analysis);
  document.body.appendChild(link);
  link.click();
  link.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
  return link.download;
}
