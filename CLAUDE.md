# 15-Minute City Accessibility Auditor

AI-powered urban planning tool that audits how equitably essential services (healthcare, education, cultural, recreation) are distributed relative to multimodal transit access across Montreal's boroughs.

## Tech Stack

- **Backend**: FastAPI (Python) with Databricks SQL + Foundation Models
- **Frontend**: React + TypeScript + Vite + Leaflet maps
- **Data**: Databricks Unity Catalog (`montreal_hackathon.quebec_data`)
- **LLM**: Databricks-hosted Llama 4 Maverick via Foundation Model API
- **Deployment**: Databricks Apps (via Asset Bundles)

## Databricks Setup

Full trial setup instructions: **https://github.com/vragovvolo/montreal-hackathon-2026**

Quick summary:
1. Go to https://www.databricks.com/try-databricks and select **"FOR WORK -- Databricks Trial"** (not Free Edition)
2. Sign up with a **work/school email** (not personal Gmail/Yahoo) -- type it manually, don't use SSO buttons
3. Select **United States** as country (more compute resources available)
4. Verify trial credits (~$400 for 14 days) via "Manage trial" button
5. Confirm **Agent Bricks** access: sidebar > AI/ML > Agents -- both Knowledge Assistant and Supervisor Agent should be available

### Load the hackathon data

1. In your Databricks workspace, create a Git folder pointing to `https://github.com/vragovvolo/montreal-hackathon-2026`
2. Open `01_setup_data` notebook and run on serverless compute
3. All tables land in `montreal_hackathon.quebec_data`

## Additional Data Needed

The app currently relies on a `population_fsa` table that is **not** part of the hackathon base data. This table requires:

- **FSA (Forward Sortation Area) boundaries** -- postal code zones mapped to boroughs with centroid lat/lon
- **Population by FSA** -- from Statistics Canada Census 2021
- **Total dwellings by FSA** -- housing density data
- **Borough mapping** -- which FSAs belong to which Montreal borough

Future enhancements also need:
- **Income/salary demographics by FSA** -- median household income for equity-weighted scoring
- **Sociodemographic profiles** -- age distribution, commute mode share, language

These can be sourced from StatCan Census open data and loaded into the `montreal_hackathon.quebec_data` schema.

## Development Setup

### Prerequisites
- Python 3.12+
- Node.js 20+
- Databricks CLI configured (`databricks configure`)

### Backend
```bash
cd montreal-15min
pip install -r requirements.txt
uvicorn app:app --host 0.0.0.0 --port 8000
```

### Frontend
```bash
cd client
npm install
npm run build    # outputs to ../build/
npm run dev      # dev server on :5173 (proxies API to :8000)
```

### Environment
The app reads Databricks credentials from the Databricks SDK default config (`~/.databrickscfg` or environment variables). Key settings:

| Variable | Default | Description |
|----------|---------|-------------|
| `DATABRICKS_WAREHOUSE_ID` | `6cba794911e5618c` | SQL warehouse for queries |
| `LLM_ENDPOINT` | `databricks-llama-4-maverick` | Foundation Model serving endpoint |
| `CHAT_RATE_LIMIT` | `10` | Max chat requests per window |
| `CHAT_RATE_WINDOW` | `60` | Rate limit window in seconds |

### Deploy to Databricks
```bash
databricks bundle deploy
databricks bundle run montreal_15min
```

## Architecture

```
FastAPI (app.py)
  /api/facilities      -- all facilities for map
  /api/transit-stops   -- all stops with headway
  /api/population      -- FSA population data
  /api/score/{borough} -- accessibility scoring
  /api/deserts         -- service desert detection
  /api/chat            -- LLM agent (tool-calling)
  /api/chat/stream     -- SSE streaming version
  /api/export/{borough} -- CSV export
  /*                   -- serves React SPA from build/

lib/
  db.py       -- Databricks SQL connection (SDK Config auth)
  queries.py  -- SQL query templates (haversine distance, joins)
  scoring.py  -- Density-aware 0-4 scoring system
  agent.py    -- LLM agent with 11 tools (score, compare, simulate, etc.)
  costs.py    -- Infrastructure gap cost estimation

client/src/
  App.tsx              -- main layout (map + panels)
  components/
    MapView.tsx        -- Leaflet map with facility/stop markers
    BoroughSelector.tsx -- borough dropdown
    ScoreCard.tsx      -- accessibility score display
    ChatPanel.tsx      -- AI assistant chat interface
    KPIBar.tsx         -- key performance indicators
    StatsView.tsx      -- statistics dashboard
```

## Database Tables

All in `montreal_hackathon.quebec_data`:

| Table | Description |
|-------|-------------|
| `unified_facilities` | Combined healthcare, education, cultural, recreation facilities |
| `unified_transit_stops` | Combined STM + STL stops |
| `stop_headways` | Average headway (frequency) by stop and time period |
| `population_fsa` | FSA population, dwellings, borough mapping, centroids |
| `transit_stm_routes/stops/trips/stop_times` | STM GTFS data |
| `transit_stl_routes/stops/stop_times/trips` | STL GTFS data |
