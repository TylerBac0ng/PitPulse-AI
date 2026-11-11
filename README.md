# PitPulse AI — F1 Race Strategy & Telemetry Analytics Platform

**CS 4800 · Assignment 2 · Initial Functional Application (MVP)**

PitPulse AI is a customer-facing web app for **historical** Formula 1 race analysis. A user picks a completed
race and two drivers, then moves through one connected workflow:

`select historical session → load race data → Overview dashboard → compare drivers/laps (Telemetry) → inspect tyre stints → test a pit-strategy scenario (Strategy Lab) → Actual vs Alternative comparison`

It is **not** live timing. Strategy results are clearly labelled **estimates**, not race predictions.

## Source documents (`docs/`)

The implementation follows the project artifacts from the in-class exercises and Assignment 1:

| Document | File |
|---|---|
| Business Plan | `docs/Business_Plan_PitPulse_AI.pptx` |
| Software Requirements Specification (FR-01–FR-13, NFR-01–NFR-12) | `docs/Software_Requirements_Specification.docx` |
| Use Case Specification (UC-01–UC-11) | `docs/Use_Case_Specification.docx` |
| Use Case & Activity Diagrams | `docs/Use_Case_and_Activity_Diagrams.png` |
| Software Architecture Specification | `docs/Software_Architecture_Specification.docx` |
| Software Architecture Diagram | `docs/Software_Architecture_Diagram.png` |
| Assignment 1 Prototype (GUI / Presentation Layer) | `docs/Assignment_1_Prototype_GUI.html` |

The architecture diagram, the use case / activity diagram and the two figures inside the Architecture Specification
were redrawn for this submission so they are legible and consistent with the SRS and Use Case Specification
(UC-01–UC-11, End User as the only actor, FastF1 / public dataset files / browser download as external systems).

Where artifacts disagree, the **Requirements Specification is authoritative** (as stated in the SRS and Architecture
Specification). So the Administrator actor and OpenF1/Weather APIs from the earlier in-class use-case sketch, and the authentication
mentioned on the business-plan technology slide, are not part of this MVP.

### Requirements traceability

| Requirement / use case | Where it is implemented |
|---|---|
| FR-01, UC-01 Race & session selection | `frontend/src/pages/SessionSelect.jsx` → `POST /api/analysis/load` |
| FR-02 Historical data retrieval | `backend/app/data/` (FastF1 adapter, seeded dataset adapter, repository + cache) |
| FR-03, UC-02 Dashboard summary | `Overview.jsx` · `analytics/laps.py` |
| FR-04, UC-03 Lap-time analysis | Overview lap-time trend & gap chart · lap pickers on Telemetry |
| FR-05/06, UC-04/05 Telemetry & driver/lap comparison | `Telemetry.jsx` · `analytics/telemetry.py` |
| FR-07, UC-06 Tyre & stint analysis | `Tires.jsx` · `analytics/stints.py` |
| FR-08, UC-07 Pit-stop & strategy analysis | Stint timeline, pit-stop table, actual strategy cards |
| FR-09/10, UC-08/09 Strategy simulation, undercut/overcut | `StrategyLab.jsx` · `strategy/simulator.py` |
| FR-11, UC-10 Strategy recommendation / comparison | `Insights.jsx` (actual vs alternative, insight text) |
| FR-12 Change drivers/laps/stints/parameters in-workflow | Driver switcher, lap pickers, stint filters, strategy controls |
| FR-13 Data availability handling | Availability flags in API responses + readable error/unavailable states in every screen |
| UC-11 Export results | **Export Results** (top bar and Comparison screen) → JSON download of the current analysis (`frontend/src/lib/export.js`) |
| NFR-05 Calculation consistency | deterministic simulator, tested (`tests/test_strategy.py`) |
| NFR-08 Responsive layout 1024–1920 px | `frontend/src/styles.css` breakpoints |
| NFR-09 Error handling | uniform `{message, still_available, next_action}` errors + React error boundary |
| NFR-10/11 Maintainability, testability | layered modules; 61 backend + 14 frontend automated tests |
| NFR-12 Caching | in-memory + `backend/cache/processed/*.json` processed-session cache |

---

## Architecture

```
┌────────────────────────── Presentation Layer (React + Vite) ──────────────────────────┐
│  SessionSelect · Overview · Telemetry · Tires & Stints · Strategy Lab · Insights      │
│  AnalysisContext (shared session state) · api/client.js (REST/JSON) · Recharts charts │
└──────────────────────────────────────────┬────────────────────────────────────────────┘
                                           │  /api  (JSON)
┌──────────────────────── Application Layer (FastAPI, app/api) ─────────────────────────┐
│  Request validation (Pydantic) · orchestration · response formatting                   │
│  Uniform readable errors: { message, still_available, next_action, field }             │
└───────────────┬──────────────────────────────┬───────────────────────┬────────────────┘
                │                              │                       │
┌───────────────▼─────────────┐  ┌─────────────▼────────────┐  ┌───────▼──────────────────┐
│ Data Access (app/data)      │  │ Analytics (app/analytics)│  │ Strategy (app/strategy)  │
│ repository.py  source       │  │ laps.py      summaries,  │  │ simulator.py             │
│   choice, fallback, cache   │  │   clean laps, gaps       │  │   deterministic pit-     │
│ fastf1_adapter.py  (ONLY    │  │ stints.py    stints,     │  │   strategy model,        │
│   module importing fastf1)  │  │   degradation fit        │  │   validation, insight    │
│ seed_adapter.py  demo data  │  │ telemetry.py lap overlay,│  │                          │
│ models.py  normalized types │  │   delta, mini-sectors    │  │                          │
└─────────────────────────────┘  └──────────────────────────┘  └──────────────────────────┘
```

* React components never call FastF1 — they only call the REST API.
* Strategy maths lives in `backend/app/strategy/simulator.py`, not in UI event handlers.
* Every adapter returns the same normalized `SessionData` model, so analytics/strategy code is source-agnostic.
* **Processed-session cache:** normalized sessions are kept in memory (LRU) and written to
  `backend/cache/processed/<season>-<round>-<session>.json`; FastF1's own HTTP cache lives in `backend/cache/fastf1/`.
  The Architecture Specification lists PostgreSQL as optional ("may persist cached derived data"); this MVP uses the
  file cache, which satisfies NFR-12, and leaves PostgreSQL for a later phase.

### Data sources (tried in this order for a real race)

| Source | What it provides | When it is used |
|---|---|---|
| **FastF1 – F1 live-timing archive** | lap & sector times, tyre compounds, stints, car telemetry | Only when `F1_USERNAME` / `F1_PASSWORD` are set (the archive returns HTTP 401 without an F1 account since 2026) |
| **FastF1 – Ergast interface (Jolpica)** | real results, lap times, running positions, pit stops | Default for real races (2018 → current season, Race sessions) |
| **Seeded demo dataset** | fictional race with full laps, sectors, compounds and synthesised telemetry | "Demo" season, and as a **visibly labelled fallback** when the sources above fail |

Data that a source lacks is never invented: on Ergast-backed races the UI states that telemetry, sector times
and compounds are unavailable, and explains what still works.

---

## Prerequisites

* **Python 3.11+** (developed with 3.12)
* **Node.js 18+** (developed with 22.11 LTS) and npm
* Internet access for real historical races (the Demo season works fully offline)

## Installation

```bash
# Backend
cd backend
python3 -m venv .venv
source .venv/bin/activate            # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt  # or requirements.txt for runtime only

# Frontend
cd ../frontend
npm install
```

## Start the backend

```bash
cd backend
source .venv/bin/activate
uvicorn app.main:app --port 8010
# health check: http://127.0.0.1:8010/api/health   ·   API docs: http://127.0.0.1:8010/docs
```

Optional settings are documented in `backend/.env.example` (e.g. `PITPULSE_OFFLINE=1` for a demo-only,
no-network run; `F1_USERNAME`/`F1_PASSWORD` to enable full FastF1 telemetry).

> Port 8010 is used because 8000 is commonly taken by other local projects. To use another port, start uvicorn
> on it and run the frontend with `VITE_API_TARGET=http://127.0.0.1:<port> npm run dev`.

## Start the frontend

```bash
cd frontend
npm run dev
# open http://localhost:5173
```

The Vite dev server proxies `/api` to the backend, so no CORS setup is needed.
Production build: `npm run build` (output in `frontend/dist/`).

---

## Demo workflow (≈3 minutes, works offline)

1. Open **http://localhost:5173**. The selector defaults to **Demo (offline) → PitPulse Demo Grand Prix → Race →
   Driver A: MOR (Alex Morgan), Driver B: COS (Luca Costa)**.
2. Click **Load Analysis** (or "Load demo: Morgan vs Costa").
3. **Overview** — KPIs (finish, best laps, finish gap, pit stops), the lap-time trend with pit markers, and the
   *Gap* toggle for the cumulative race gap. Point out "MOR faster on 32 of 45 comparable laps".
4. Click **Compare Telemetry**. Best laps are pre-selected; switch channels (Speed/Throttle/Brake/RPM/Gear).
5. Show the **running time delta** and the **mini-sector bars** — click the tallest red bar to highlight
   where MOR loses time on the speed trace; read the generated insight and sector deltas.
6. Click **View Tire Context**. Stint 1 (Soft) is labelled **Degrading** (+0.12 s/lap, +0.94 s late-stint drop) —
   the steepest line on the *Pace change vs tyre age* chart.
7. Click **Open Strategy Lab**. Choose **Undercut** (moves Pit Stop 1 from lap 17 to lap 14) → **Run Simulation**.
   Result: *≈0.7 s faster (estimate)*. Try **Overcut** to lap 20 to show a ≈3 s loss.
8. Click **Compare Actual vs Alternative** — side-by-side plans, cumulative-delta chart (the alternative drops
   ~23 s behind at its earlier stop, then recovers on fresher tyres), breakdown and the plain-language explanation. Click **Export results** to download the analysis (UC-11).
9. Error handling to show: drag Pit Stop 2 before Pit Stop 1 ("Pit Stop 2 must occur after Pit Stop 1.");
   choose *Session: Qualifying* on the selector; load **Demo Grand Prix — Limited Data** and open Telemetry
   (telemetry unavailable, lap/sector comparison still works; unknown compounds shown striped).
10. Real data: choose **2023 → Bahrain Grand Prix → VER vs ALO** (or "Try real race: 2023 Bahrain").
    First load ≈5–15 s, then cached.

## Tests

```bash
# Backend (61 tests; offline — real seasons are faked or fall back to demo data)
cd backend && source .venv/bin/activate && python -m pytest -q

# Frontend (14 tests: navigation/route guard, strategy validation rules, export, formatting)
cd frontend && npm test
```

Covered: API request validation, adapter normalization (incl. Ergast pagination), seeded fallback,
processed-session cache, telemetry comparison (valid + missing telemetry + invalid driver/lap + empty selection),
stint/degradation consistency, strategy validation and determinism, critical frontend navigation.

---

## Strategy model (documented, deterministic)

For each lap of a plan: `lap = base[c] + deg[c]·age + curve[c]·age² + cliff − 0.035·(lap−1) + pit_loss (on in-laps)`.

* `base`, `deg` — straight-line fit of the driver's fuel-corrected clean laps on that compound.
* `curve` — accelerating wear, only used when a quadratic fit clearly beats the line (≥8 laps, ≥15 % less error).
* Compounds the driver didn't run borrow field-median pace/degradation from the same session, else documented defaults.
* `pit_loss` — driver's median measured (in-lap + out-lap − 2 × typical lap); default 22 s.
* `cliff` — +0.04 s × (laps beyond recommended life)²; also drives the tyre-risk warning.
* Actual and alternative run through the **same** model; the difference is applied to the real race time.

Not modelled: traffic/track position, safety cars, tyre warm-up, used tyre sets, weather.

## Known limitations

* Without F1 account credentials, real races have **no car telemetry, sector times or tyre compounds**
  (the official archive requires authentication). The UI says so and the Strategy Lab falls back to a single
  generic-tyre model (pit timing only). The full-FastF1 code path is implemented but could not be exercised
  without credentials.
* Real-data lap-by-lap analysis covers **Race** sessions; Qualifying returns a clear "unavailable" message.
* Demo telemetry is **synthesised** from a kinematic model of a fictional circuit — labelled as demo data.
* The strategy model is intentionally simple (see above); small deltas (< 0.5 s) are reported as "roughly equal".
* Desktop-first: tuned for 1024–1920 px; phone layouts are not a goal for this assignment.
* Manually tested in Chrome; Firefox and Edge (NFR-07) have not been tested yet.
* Processed-session cache is file-based; no database or saved scenarios yet. Export is JSON only.

## Out of scope for Assignment 2 (planned for later phases)

Saved scenarios, chart-image/PDF reports (beyond the current JSON export), PostgreSQL persistence, authenticated users, richer strategy modelling
(traffic, safety-car windows, used sets), multi-driver/field-wide strategy comparison, corner-level track maps,
CI pipeline and hosted deployment. Live timing, chatbots, social features and other racing series remain out of scope.

## Data-source note

Historical data is accessed through the open-source **FastF1** library (and its Ergast/Jolpica interface).
PitPulse AI is an unofficial educational project and is not associated with Formula 1 companies.
F1, FORMULA 1 and related marks are trademarks of Formula One Licensing B.V. The demo drivers, teams and circuit
are fictional.

## Project layout

```
PitPulse_AI/
├── backend/
│   ├── app/
│   │   ├── main.py              FastAPI app, error handlers, CORS
│   │   ├── config.py            environment settings
│   │   ├── errors.py            domain errors (what / still available / next action)
│   │   ├── api/routes.py        Application layer
│   │   ├── data/                Data Access layer (+ seed/demo_sessions.json)
│   │   ├── analytics/           laps, stints, telemetry
│   │   └── strategy/            simulator
│   ├── scripts/generate_seed.py deterministic demo-data generator
│   ├── tests/                   pytest suite
│   └── requirements*.txt, .env.example
├── frontend/
│   ├── src/{pages,components,state,api,lib}
│   └── package.json, vite.config.js, .env.example
├── docs/                        Business Plan, SRS, Use Case & Architecture specs, Assignment 1 prototype
└── README.md
```
