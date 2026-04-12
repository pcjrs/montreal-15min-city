"""FastAPI backend for the 15-Minute City Accessibility Auditor."""

import os
import io
import csv
import time
import asyncio
import logging
from collections import defaultdict
from pathlib import Path
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, StreamingResponse, JSONResponse
from pydantic import BaseModel, Field, model_validator

from lib.db import execute_sql
from lib import queries
from lib.scoring import calculate_fsa_score, score_label, CATEGORIES, THRESHOLDS
from lib.agent import chat_with_agent, chat_with_agent_streaming

logger = logging.getLogger(__name__)


# --- In-memory rate limiter (no external dependencies) ---

_RATE_LIMIT = int(os.getenv("CHAT_RATE_LIMIT", "10"))  # requests per window
_RATE_WINDOW = int(os.getenv("CHAT_RATE_WINDOW", "60"))  # window in seconds
_rate_log: dict[str, list[float]] = defaultdict(list)


def _is_rate_limited(client_ip: str) -> bool:
    """Return True if client_ip has exceeded the rate limit."""
    now = time.monotonic()
    timestamps = _rate_log[client_ip]
    # Prune old entries
    _rate_log[client_ip] = [t for t in timestamps if now - t < _RATE_WINDOW]
    if len(_rate_log[client_ip]) >= _RATE_LIMIT:
        return True
    _rate_log[client_ip].append(now)
    return False


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield


app = FastAPI(title="15-Minute City Accessibility Auditor", lifespan=lifespan)


@app.get("/api/health")
async def health():
    """Health check endpoint."""
    return {"status": "ok"}


# --- Data API Endpoints ---


@app.get("/api/facilities")
async def get_facilities():
    """Return all facilities in the Montreal area for map display."""
    rows = execute_sql(queries.ALL_FACILITIES)
    return {"facilities": rows, "count": len(rows)}


@app.get("/api/transit-stops")
async def get_transit_stops():
    """Return all transit stops with headway data for map display."""
    rows = execute_sql(queries.ALL_STOPS_WITH_HEADWAY)
    return {"stops": rows, "count": len(rows)}


@app.get("/api/population")
async def get_population():
    """Return all FSA population data."""
    rows = execute_sql(queries.ALL_POPULATION)
    return {"fsas": rows, "count": len(rows)}


@app.get("/api/score/{borough}")
async def get_borough_score(borough: str):
    """Calculate accessibility score for a borough (optimized: 4 queries total)."""
    safe_borough = borough.replace("'", "''")
    fsas = execute_sql(queries.BOROUGH_FSAS.format(borough=safe_borough))
    if not fsas:
        raise HTTPException(status_code=404, detail=f"Borough '{borough}' not found")

    total_pop = sum(f["population"] for f in fsas)

    # Build bounding box that covers all FSAs (with buffer for radius search)
    lats = [f["latitude"] for f in fsas]
    lons = [f["longitude"] for f in fsas]
    min_lat, max_lat = min(lats) - 0.015, max(lats) + 0.015
    min_lon, max_lon = min(lons) - 0.02, max(lons) + 0.02

    # Bulk fetch: 3 queries instead of N*3
    all_stops = execute_sql(f"""
        SELECT stop_id, stop_name, stop_lat, stop_lon, wheelchair_boarding, agency
        FROM unified_transit_stops
        WHERE stop_lat BETWEEN {min_lat - 0.008} AND {max_lat + 0.008}
          AND stop_lon BETWEEN {min_lon - 0.012} AND {max_lon + 0.012}
    """)

    all_facilities = execute_sql(f"""
        SELECT facility_name, category, facility_type, lat, lon
        FROM unified_facilities
        WHERE lat BETWEEN {min_lat - 0.02} AND {max_lat + 0.02}
          AND lon BETWEEN {min_lon - 0.03} AND {max_lon + 0.03}
    """)

    # Collect stop_ids for headway lookup
    stop_id_set = set(s["stop_id"] for s in all_stops)
    all_headways = {}
    if stop_id_set:
        sample_ids = list(stop_id_set)[:500]
        stop_ids_str = ",".join(f"'{sid}'" for sid in sample_ids)
        headway_rows = execute_sql(f"""
            SELECT stop_id, agency, avg_headway_min
            FROM stop_headways
            WHERE stop_id IN ({stop_ids_str}) AND time_period = 'midday'
        """)
        for h in headway_rows:
            all_headways[h["stop_id"]] = h["avg_headway_min"]

    import math

    def haversine_m(lat1, lon1, lat2, lon2):
        R = 6371000
        dlat = math.radians(lat2 - lat1)
        dlon = math.radians(lon2 - lon1)
        a = math.sin(dlat / 2) ** 2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2) ** 2
        return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

    scores = []
    for fsa in fsas:
        lat, lon = fsa["latitude"], fsa["longitude"]

        # Filter stops within 800m
        nearby_stops = [s for s in all_stops if haversine_m(lat, lon, s["stop_lat"], s["stop_lon"]) <= 800]

        # Filter facilities within 1500m
        nearby_fac = [f for f in all_facilities if f["lat"] and f["lon"] and haversine_m(lat, lon, f["lat"], f["lon"]) <= 1500]

        category_counts = {c: 0 for c in CATEGORIES}
        for f in nearby_fac:
            if f["category"] in category_counts:
                category_counts[f["category"]] += 1

        scoring = calculate_fsa_score(category_counts, fsa["population"])

        avg_headway = None
        if nearby_stops:
            hw_vals = [all_headways[s["stop_id"]] for s in nearby_stops[:20] if s["stop_id"] in all_headways]
            if hw_vals:
                avg_headway = sum(hw_vals) / len(hw_vals)

        wheelchair_pct = 0
        if nearby_stops:
            accessible = sum(1 for s in nearby_stops if s.get("wheelchair_boarding") == 1)
            wheelchair_pct = round(accessible / len(nearby_stops) * 100)

        categories_found = [c for c in CATEGORIES if category_counts[c] > 0]

        scores.append({
            "postal_code": fsa["postal_code"],
            "fsa_name": fsa["fsa_name"],
            "population": fsa["population"],
            "latitude": lat,
            "longitude": lon,
            "score": scoring["density_score"],
            "legacy_score": scoring["legacy_score"],
            "density_score": scoring["density_score"],
            "category_details": scoring["category_details"],
            "categories": categories_found,
            "missing": [c for c in CATEGORIES if category_counts[c] == 0],
            "stop_count": len(nearby_stops),
            "avg_headway_min": round(avg_headway, 1) if avg_headway else None,
            "wheelchair_pct": wheelchair_pct,
        })

    avg_score = sum(s["density_score"] for s in scores) / len(scores) if scores else 0
    underserved = [s for s in scores if s["density_score"] < 2.5]

    return {
        "borough": borough,
        "total_population": total_pop,
        "fsa_count": len(fsas),
        "average_score": round(avg_score, 2),
        "fsa_scores": scores,
        "underserved_fsas": underserved,
        "underserved_population": sum(s["population"] for s in underserved),
    }


@app.get("/api/deserts")
async def get_service_deserts():
    """Detect service deserts across all FSAs with density-aware scoring."""
    rows = execute_sql(queries.DESERT_DETECTION)

    # Enrich each row with density scoring
    for r in rows:
        counts = {
            "healthcare": r.get("healthcare", 0),
            "education": r.get("education", 0),
            "cultural": r.get("cultural", 0),
            "recreation": r.get("recreation", 0),
        }
        scoring = calculate_fsa_score(counts, r["population"])
        r["density_score"] = scoring["density_score"]
        r["legacy_score"] = r["score"]
        r["category_details"] = scoring["category_details"]

    deserts = [r for r in rows if r["density_score"] < 2.5]
    return {
        "all_fsas": rows,
        "deserts": deserts,
        "desert_count": len(deserts),
        "total_affected_population": sum(d["population"] for d in deserts),
    }


class ChatMessage(BaseModel):
    message: str = Field(..., min_length=1, max_length=2000)
    history: list[dict] | None = None
    summarize: bool = False

    @model_validator(mode="after")
    def cap_history(self):
        if self.history:
            self.history = self.history[-20:]  # keep last 10 turns max
        return self


@app.post("/api/chat")
async def chat(request: Request, msg: ChatMessage):
    """LLM-powered planning assistant with tool calling against Databricks data."""
    client_ip = request.client.host if request.client else "unknown"
    if _is_rate_limited(client_ip):
        return JSONResponse(
            status_code=429,
            content={"type": "error", "message": "Too many requests. Please wait a minute before trying again."},
            headers={"Retry-After": str(_RATE_WINDOW)},
        )
    try:
        response = await asyncio.to_thread(
            chat_with_agent, msg.message, msg.history, msg.summarize
        )
        return {"type": "analysis", "message": response}
    except Exception as e:
        logger.exception("Chat endpoint error: %s", e)
        return {"type": "error", "message": "An unexpected error occurred. Please try again."}


_STREAM_DONE = object()


def _next_or_done(gen):
    """Wrapper to avoid StopIteration propagation issues with asyncio."""
    try:
        return next(gen)
    except StopIteration:
        return _STREAM_DONE


@app.post("/api/chat/stream")
async def chat_stream(request: Request, msg: ChatMessage):
    """Streaming version of chat — returns SSE events with tool call progress."""
    client_ip = request.client.host if request.client else "unknown"
    if _is_rate_limited(client_ip):
        return JSONResponse(
            status_code=429,
            content={"type": "error", "message": "Too many requests. Please wait a minute before trying again."},
            headers={"Retry-After": str(_RATE_WINDOW)},
        )

    async def event_generator():
        gen = chat_with_agent_streaming(msg.message, msg.history, msg.summarize)
        loop = asyncio.get_event_loop()
        while True:
            try:
                chunk = await loop.run_in_executor(None, _next_or_done, gen)
                if chunk is _STREAM_DONE:
                    break
                yield f"data: {chunk}\n\n"
            except Exception as e:
                logger.exception("Stream error: %s", e)
                import json as _json
                yield f"data: {_json.dumps({'type': 'error', 'content': 'An unexpected error occurred.'})}\n\n"
                break

    return StreamingResponse(event_generator(), media_type="text/event-stream")


@app.get("/api/export/{borough}")
async def export_borough_csv(borough: str):
    """Export borough accessibility scores as a CSV file."""
    fsas = execute_sql(queries.BOROUGH_FSAS.format(borough=borough.replace("'", "''")))
    if not fsas:
        raise HTTPException(status_code=404, detail=f"Borough '{borough}' not found")

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "postal_code", "fsa_name", "population", "density_score", "label",
        "healthcare_count", "healthcare_expected", "healthcare_adequacy",
        "education_count", "education_expected", "education_adequacy",
        "cultural_count", "cultural_expected", "cultural_adequacy",
        "recreation_count", "recreation_expected", "recreation_adequacy",
        "stop_count", "avg_headway_min", "wheelchair_pct", "missing_categories",
    ])

    for fsa in fsas:
        lat, lon = fsa["latitude"], fsa["longitude"]
        stops = execute_sql(queries.NEARBY_STOPS.format(lat=lat, lon=lon, radius=800))
        facilities = execute_sql(queries.NEARBY_FACILITIES.format(lat=lat, lon=lon, radius=1500))

        category_counts = {c: 0 for c in CATEGORIES}
        for f in facilities:
            if f["category"] in category_counts:
                category_counts[f["category"]] += 1

        scoring = calculate_fsa_score(category_counts, fsa["population"])

        avg_headway = None
        if stops:
            stop_ids = ",".join(f"'{s['stop_id']}'" for s in stops[:20])
            headways = execute_sql(queries.STOP_HEADWAYS.format(stop_ids=stop_ids, period="midday"))
            if headways:
                avg_headway = round(sum(h["avg_headway_min"] for h in headways) / len(headways), 1)

        wheelchair_pct = 0
        if stops:
            accessible = sum(1 for s in stops if s.get("wheelchair_boarding") == 1)
            wheelchair_pct = round(accessible / len(stops) * 100)

        missing = [c for c in CATEGORIES if category_counts[c] == 0]
        details = {d["category"]: d for d in scoring["category_details"]}

        row = [
            fsa["postal_code"], fsa["fsa_name"], fsa["population"],
            scoring["density_score"], score_label(scoring["density_score"]),
        ]
        for cat in CATEGORIES:
            d = details[cat]
            row.extend([d["actual"], d["expected"], round(d["adequacy_ratio"] * 100)])
        row.extend([len(stops), avg_headway, wheelchair_pct, "; ".join(missing)])
        writer.writerow(row)

    output.seek(0)
    filename = f"{borough.lower().replace(' ', '-')}_accessibility.csv"
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


_BOROUGHS = [
    "AHUNTSIC-CARTIERVILLE", "ANJOU", "COTE-DES-NEIGES-NOTRE-DAME-DE-GRACE",
    "COTE-SAINT-LUC", "DOLLARD-DES-ORMEAUX", "ILE-BIZARD-SAINTE-GENEVIEVE",
    "LACHINE", "LASALLE", "LE PLATEAU-MONT-ROYAL", "LE SUD-OUEST",
    "MERCIER-HOCHELAGA-MAISONNEUVE", "MONTREAL-EST", "MONTREAL-NORD",
    "MONTREAL-OUEST", "MONT-ROYAL", "OUTREMONT", "PIERREFONDS-ROXBORO",
    "POINTE-CLAIRE", "RIVIERE-DES-PRAIRIES-POINTE-AUX-TREMBLES",
    "ROSEMONT-LA PETITE-PATRIE", "SAINTE-ANNE-DE-BELLEVUE", "SAINT-LAURENT",
    "SAINT-LEONARD", "VERDUN", "VILLE-MARIE",
    "VILLERAY-SAINT-MICHEL-PARC-EXTENSION", "WESTMOUNT",
]


# --- Serve React Frontend ---

BUILD_DIR = Path(__file__).parent / "build"

if BUILD_DIR.exists():
    assets_dir = BUILD_DIR / "assets"
    if assets_dir.exists():
        app.mount("/assets", StaticFiles(directory=assets_dir), name="assets")

    @app.get("/{full_path:path}")
    async def serve_react(full_path: str):
        if full_path.startswith("api/"):
            raise HTTPException(status_code=404)
        file_path = BUILD_DIR / full_path
        if file_path.exists() and file_path.is_file():
            return FileResponse(file_path)
        return FileResponse(BUILD_DIR / "index.html")
