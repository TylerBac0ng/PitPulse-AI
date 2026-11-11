// Thin REST client for the PitPulse FastAPI backend. All requests go through /api (proxied in dev).

const BASE = import.meta.env.VITE_API_BASE || '/api';

export class ApiError extends Error {
  constructor({ message, code, still_available, next_action, field, status }) {
    super(message);
    this.code = code;
    this.stillAvailable = still_available;
    this.nextAction = next_action;
    this.field = field;
    this.status = status;
  }
}

async function request(path, { method = 'GET', body, signal } = {}) {
  let res;
  try {
    res = await fetch(`${BASE}${path}`, {
      method,
      headers: body ? { 'Content-Type': 'application/json' } : undefined,
      body: body ? JSON.stringify(body) : undefined,
      signal,
    });
  } catch (err) {
    if (err.name === 'AbortError') throw err;
    throw new ApiError({
      code: 'network',
      message: 'Cannot reach the PitPulse AI server.',
      still_available: 'Nothing is lost — your selections are kept.',
      next_action: 'Make sure the backend is running (uvicorn on port 8010), then retry.',
      status: 0,
    });
  }
  let data = null;
  try {
    data = await res.json();
  } catch {
    /* non-JSON response */
  }
  if (!res.ok) {
    const e = data?.error || {};
    throw new ApiError({
      message: e.message || `Request failed (${res.status}).`,
      code: e.code,
      still_available: e.still_available,
      next_action: e.next_action,
      field: e.field,
      status: res.status,
    });
  }
  return data;
}

export const api = {
  seasons: (o) => request('/seasons', o),
  events: (season, o) => request(`/seasons/${encodeURIComponent(season)}/events`, o),
  drivers: (season, round, o) => request(`/seasons/${encodeURIComponent(season)}/events/${round}/drivers`, o),
  load: (body, o) => request('/analysis/load', { method: 'POST', body, ...o }),
  overview: (key, a, b, o) =>
    request(`/analysis/${key}/overview?driver_a=${a}${b ? `&driver_b=${b}` : ''}`, o),
  telemetry: (key, body, o) => request(`/analysis/${key}/telemetry`, { method: 'POST', body, ...o }),
  strategyBaseline: (key, driver, o) => request(`/analysis/${key}/strategy/baseline?driver=${driver}`, o),
  simulate: (key, body, o) => request(`/analysis/${key}/strategy/simulate`, { method: 'POST', body, ...o }),
};
