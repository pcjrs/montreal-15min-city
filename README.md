# 15-Minute City Accessibility Auditor

An AI-powered tool for urban planners to audit how equitably essential services are distributed relative to multimodal transit access across Montreal's boroughs. Built on the *ville du quart d'heure* framework that Montreal is actively pursuing in its Plan d'urbanisme et de mobilite (PUM 2050).

## What It Does

- **Scores** any borough or FSA on 15-minute city readiness (0-4 scale) across healthcare, education, cultural, and recreation facilities
- **Detects service deserts** — areas where essential facility categories are missing within transit reach
- **Compares boroughs** side-by-side with structured equity metrics
- **Simulates scenarios** — project how population growth/decline would impact accessibility scores
- **Estimates costs** — infrastructure gap analysis with Quebec construction benchmarks
- **Generates planning briefs** — AI-produced reports suitable for borough council presentation

All analysis is backed by real data queried live from Databricks.

## Screenshots

| Map View | AI Chat Assistant |
|----------|-------------------|
| Interactive Leaflet map with facility markers, transit stops, and FSA overlays | Natural language queries with tool-calling agent that runs SQL against live data |

## Tech Stack

| Layer | Technology |
|-------|------------|
| Backend | FastAPI (Python 3.12+) |
| Frontend | React 19 + TypeScript + Vite + Leaflet |
| Data | Databricks Unity Catalog |
| LLM | Llama 4 Maverick via Databricks Foundation Models |
| Deployment | Databricks Apps (Asset Bundles) |

## Quick Start

### 1. Set up Databricks

Follow the trial setup guide at **[vragovvolo/montreal-hackathon-2026](https://github.com/vragovvolo/montreal-hackathon-2026)** to create your workspace and load the data.

### 2. Configure credentials

```bash
pip install databricks-cli
databricks configure
# Enter your workspace host and token
```

### 3. Run locally

```bash
# Backend
pip install -r requirements.txt
uvicorn app:app --host 0.0.0.0 --port 8000

# Frontend (in a second terminal)
cd client
npm install
npm run build   # production build -> ../build/
# or
npm run dev     # dev server on :5173
```

### 4. Deploy to Databricks

```bash
databricks bundle deploy
databricks bundle run montreal_15min
```

## AI Agent Tools

The chat assistant has 11 tools it can call against live data:

| Tool | Description |
|------|-------------|
| `score_borough` | Calculate 15-minute city score for a borough |
| `find_service_deserts` | Detect underserved FSAs across the city |
| `query_facilities_near` | Find facilities near a lat/lon |
| `query_transit_stops_near` | Find transit stops with headway data |
| `get_borough_population` | Population data by FSA |
| `run_custom_sql` | Ad-hoc read-only SQL queries |
| `compare_boroughs` | Side-by-side borough comparison |
| `get_routes_at_stop` | Bus/metro routes serving a stop |
| `simulate_population_change` | Re-score with projected population |
| `estimate_project_cost` | Infrastructure gap cost estimation |
| `flag_infrastructure_needs` | Prioritized infrastructure flags per FSA |

## Scoring System

Each FSA is scored 0.0-4.0 (one point per category):

- **Presence** (0.3 pts): Is there at least 1 facility within 1.5km?
- **Adequacy** (0.0-0.7 pts): Is the facility count sufficient for the population?

Per-capita thresholds:
- Healthcare: 1 per 5,000 (WHO + Quebec CLSC density)
- Education: 1 per 4,000 (school placement + library targets)
- Cultural: 1 per 15,000 (destination-based)
- Recreation: 1 per 3,000 (Canadian Parks & Rec Assoc)

| Score | Label |
|-------|-------|
| 3.5-4.0 | Well-Served |
| 2.5-3.4 | Adequate |
| 1.5-2.4 | Underserved |
| 0.5-1.4 | Poorly Served |
| 0.0-0.4 | Service Desert |

## Data Sources

All data lives in `montreal_hackathon.quebec_data` on Databricks:

- **Transit**: STM + STL GTFS feeds (routes, stops, trips, stop times)
- **Facilities**: Statistics Canada open databases — healthcare, education, cultural/art, recreation/sport
- **Population**: Census 2021 FSA-level population and dwelling counts
- **Reference**: Montreal PUM 2050, STM annual report, Quebec infrastructure plan, cycling/pedestrian plans

See the [hackathon data repo](https://github.com/vragovvolo/montreal-hackathon-2026) for full dataset documentation.

## Project Structure

```
montreal-15min/
├── app.py              # FastAPI backend (API + serves React SPA)
├── app.yaml            # Databricks App config
├── databricks.yml      # Databricks Asset Bundle definition
├── requirements.txt    # Python dependencies
├── lib/
│   ├── agent.py        # LLM agent with 11 tool functions
│   ├── costs.py        # Infrastructure cost estimation
│   ├── db.py           # Databricks SQL connection
│   ├── queries.py      # SQL query templates
│   └── scoring.py      # Density-aware accessibility scoring
└── client/
    ├── src/
    │   ├── App.tsx
    │   └── components/
    │       ├── MapView.tsx          # Leaflet map
    │       ├── ChatPanel.tsx        # AI chat interface
    │       ├── BoroughSelector.tsx  # Borough picker
    │       ├── ScoreCard.tsx        # Score display
    │       ├── KPIBar.tsx           # Key metrics
    │       └── StatsView.tsx        # Statistics dashboard
    ├── package.json
    └── vite.config.ts
```

## License

Built for the Montreal Databricks Hackathon 2026.
