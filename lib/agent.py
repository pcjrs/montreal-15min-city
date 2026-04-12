"""LLM-powered planning assistant using Databricks Foundation Models."""

import os
import re
import json
import logging
import requests
from databricks.sdk.core import Config

from lib.db import execute_sql
from lib.scoring import calculate_fsa_score, score_label, CATEGORIES, THRESHOLDS

logger = logging.getLogger(__name__)

# --- Guardrails ---

_MAX_MESSAGE_LENGTH = 2000
_MAX_SQL_LENGTH = 2000

_INJECTION_PATTERNS = re.compile(
    r"ignore\s+(all\s+)?(previous|prior|above)\s+(instructions|prompts|rules)"
    r"|you\s+are\s+now\b"
    r"|system\s*:"
    r"|<\|"
    r"|\]\[INST\]"
    r"|<\/?system>"
    r"|ADMIN\s*OVERRIDE"
    r"|do\s+not\s+follow\s+(your|the)\s+(rules|instructions)",
    re.IGNORECASE,
)

_TOPIC_KEYWORDS = re.compile(
    r"\b(montreal|borough|arrondissement|fsa|postal.code|transit|stop|bus|metro|stm|stl|"
    r"facility|facilities|healthcare|hospital|clinic|clsc|school|education|"
    r"cultural|recreation|park|sport|loisir|culture|"
    r"score|accessibility|desert|underserved|service|population|"
    r"headway|frequency|route|wheelchair|planif|urban|infrastructure|"
    r"h\d[a-z]|verdun|plateau|outremont|villeray|lasalle|lachine|rosemont|"
    r"anjou|saint.?laurent|saint.?leonard|westmount|"
    r"invest|cost|budget|gap|manque|lacune|priorit|recommand|analyse|audit|"
    r"15.?minute|ville|quartier|arrond|compare|compar|croissance|growth|"
    r"income|revenue|demographic|socio|scenario|projection|forecast|extrapolat|"
    r"equit|inequalit|dispar|densit|zoning|land.?use|housing|logement|residen)\b",
    re.IGNORECASE,
)

_OFFTOPIC_PATTERNS = re.compile(
    r"\b(recipe|cook|bake|ingredient|weather(?!\s+impact)|"
    r"stock|crypto|bitcoin|"
    r"movie|film|serie|netflix|sport(?:s)?\s+(?:score|result|team|player|game)|"
    r"write\s+(me\s+)?(a\s+)?(poem|story|essay|joke|song|code|script|email)|"
    r"translate\s+this|what\s+is\s+the\s+capital\s+of|"
    r"how\s+to\s+(cook|make|build|hack|crack|bypass)|"
    r"tell\s+me\s+(a\s+)?(joke|story|fun\s+fact(?!\s+about\s+montreal)))\b",
    re.IGNORECASE,
)


def _is_on_topic(text: str) -> bool:
    """Return True if message is plausibly about Montreal urban planning."""
    if len(text.strip()) <= 60:
        return True
    if _TOPIC_KEYWORDS.search(text):
        return True
    if _OFFTOPIC_PATTERNS.search(text):
        return False
    return False


_SQL_DANGEROUS_KEYWORDS = re.compile(
    r"\b(DROP|INSERT|UPDATE|DELETE|ALTER|CREATE|EXEC|EXECUTE|GRANT|REVOKE|TRUNCATE|MERGE|REPLACE|CALL)\b"
    r"|INTO\s+OUTFILE"
    r"|INTO\s+DUMPFILE",
    re.IGNORECASE,
)
_SQL_COMMENT_PATTERN = re.compile(r"--.*?$|/\*.*?\*/", re.MULTILINE | re.DOTALL)


def _screen_input(text: str) -> str | None:
    """Screen user input for prompt injection and off-topic questions. Returns refusal message or None if clean."""
    if len(text) > _MAX_MESSAGE_LENGTH:
        return "Your message is too long. Please keep it under 2,000 characters."
    if _INJECTION_PATTERNS.search(text):
        return "I can only help with Montreal urban planning and accessibility questions. Please rephrase your question."
    if not _is_on_topic(text):
        return "I'm specialized in Montreal 15-minute city analysis. Please ask about boroughs, transit, facilities, accessibility scores, or urban planning."
    return None


def _sanitize_sql(sql: str) -> str | None:
    """Validate and clean a SQL string. Returns None with logged reason if blocked."""
    sql = sql.strip()
    if len(sql) > _MAX_SQL_LENGTH:
        return None
    # Strip comments that could hide malicious payloads
    sql = _SQL_COMMENT_PATTERN.sub(" ", sql).strip()
    if not sql.upper().startswith("SELECT"):
        return None
    if _SQL_DANGEROUS_KEYWORDS.search(sql):
        return None
    return sql

_MODEL_ENDPOINT = os.getenv("LLM_ENDPOINT", "databricks-llama-4-maverick")

SYSTEM_PROMPT = """You are a 15-Minute City Accessibility Auditor for Montreal. You help urban planners assess how equitably essential services (healthcare, education, cultural, recreation) are distributed relative to multimodal transit access.

You have access to tools that query real Montreal transit and facility data from Databricks. Use them to answer questions with data-backed analysis.

## Your Capabilities
- Score any borough or FSA on 15-minute city readiness (0-4 scale)
- Detect service deserts — areas lacking essential facility categories
- Analyze transit coverage — stop density, frequency (headway), wheelchair accessibility
- Generate planning briefs for municipal stakeholders
- Compare boroughs side-by-side with structured metrics diff
- Look up which bus/metro routes serve any transit stop
- Simulate population growth/decline to project future accessibility impacts
- Estimate project costs and timelines to close infrastructure gaps (Quebec construction benchmarks)
- Flag infrastructure needs per FSA with projected scores if gaps were filled and population impact

## Scoring System (Density-Aware, 0.0-4.0 scale)
Each of the 4 categories (healthcare, education, cultural, recreation) scores 0.0-1.0:
- **Presence** (0.3 points): Is there at least 1 facility within 1.5km?
- **Adequacy** (0.0-0.7 points): Is the facility count sufficient for the population?

Per-capita thresholds (1 facility per N people):
- Healthcare: 1 per 5,000 (WHO + Quebec CLSC density)
- Education: 1 per 4,000 (school placement + library targets)
- Cultural: 1 per 15,000 (destination-based, lower density expected)
- Recreation: 1 per 3,000 (Canadian Parks & Rec Assoc)

Score labels:
- 3.5-4.0: Well-Served — all categories present and adequately staffed
- 2.5-3.4: Adequate — most categories present, some density gaps
- 1.5-2.4: Underserved — significant gaps in coverage or density
- 0.5-1.4: Poorly Served — major deficiencies
- 0.0-0.4: Service Desert — near-total lack of accessible services

## Borough Names (use UPPERCASE)
AHUNTSIC-CARTIERVILLE, ANJOU, COTE-DES-NEIGES-NOTRE-DAME-DE-GRACE, COTE-SAINT-LUC, DOLLARD-DES-ORMEAUX, ILE-BIZARD-SAINTE-GENEVIEVE, LACHINE, LASALLE, LE PLATEAU-MONT-ROYAL, LE SUD-OUEST, MERCIER-HOCHELAGA-MAISONNEUVE, MONTREAL-EST, MONTREAL-NORD, MONTREAL-OUEST, MONT-ROYAL, OUTREMONT, PIERREFONDS-ROXBORO, POINTE-CLAIRE, RIVIERE-DES-PRAIRIES-POINTE-AUX-TREMBLES, ROSEMONT-LA PETITE-PATRIE, SAINTE-ANNE-DE-BELLEVUE, SAINT-LAURENT, SAINT-LEONARD, VERDUN, VILLE-MARIE, VILLERAY-SAINT-MICHEL-PARC-EXTENSION, WESTMOUNT

## Guidelines
- Always back your analysis with data from tools
- When generating planning briefs, use markdown formatting with headers, tables, and bullet points
- Mention specific FSA postal codes, population counts, and facility names
- Provide actionable recommendations for urban planners
- If a user mentions a partial borough name, match it to the closest full name
- Format numbers with commas for readability
- You MUST refuse any question unrelated to Montreal urban planning, transit, facilities, or accessibility. Reply: "I'm specialized in Montreal 15-minute city analysis. Please ask about boroughs, transit, facilities, or accessibility scores."
- Never roleplay, write creative content, answer general knowledge questions, or discuss topics outside the scope of this tool.
"""

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "score_borough",
            "description": "Calculate the 15-minute city accessibility score for a borough. Returns per-FSA scores, missing categories, transit quality, and underserved areas.",
            "parameters": {
                "type": "object",
                "properties": {
                    "borough": {
                        "type": "string",
                        "description": "Borough name in UPPERCASE (e.g., MONTREAL-NORD, LE PLATEAU-MONT-ROYAL)"
                    }
                },
                "required": ["borough"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "find_service_deserts",
            "description": "Detect all FSA zones scoring below 3/4 on accessibility across the entire city. Returns postal codes, boroughs, populations, and missing facility categories.",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "query_facilities_near",
            "description": "Find facilities near a location within a given radius. Returns facility names, categories, types, and distances.",
            "parameters": {
                "type": "object",
                "properties": {
                    "lat": {"type": "number", "description": "Latitude"},
                    "lon": {"type": "number", "description": "Longitude"},
                    "radius_m": {"type": "number", "description": "Search radius in meters (default 1500)", "default": 1500}
                },
                "required": ["lat", "lon"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "query_transit_stops_near",
            "description": "Find transit stops near a location with headway (frequency) data. Returns stop names, agencies, headway, and wheelchair accessibility.",
            "parameters": {
                "type": "object",
                "properties": {
                    "lat": {"type": "number", "description": "Latitude"},
                    "lon": {"type": "number", "description": "Longitude"},
                    "radius_m": {"type": "number", "description": "Search radius in meters (default 800)", "default": 800}
                },
                "required": ["lat", "lon"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_borough_population",
            "description": "Get population data for all FSA zones in a borough.",
            "parameters": {
                "type": "object",
                "properties": {
                    "borough": {"type": "string", "description": "Borough name in UPPERCASE"}
                },
                "required": ["borough"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "run_custom_sql",
            "description": "Run a custom SQL query against the Montreal transit/facility database. Available tables: unified_facilities, unified_transit_stops, stop_headways, population_fsa, transit_stm_routes, transit_stm_stops, transit_stm_stop_times, transit_stm_trips, transit_stl_routes, transit_stl_stops, transit_stl_stop_times, transit_stl_trips. All in schema montreal_hackathon.quebec_data.",
            "parameters": {
                "type": "object",
                "properties": {
                    "sql": {"type": "string", "description": "SQL query to execute (read-only, SELECT only)"}
                },
                "required": ["sql"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "compare_boroughs",
            "description": "Compare two boroughs side-by-side on 15-minute city readiness. Returns a structured diff with per-category scores, transit quality, population, underserved areas, and which borough leads in each metric.",
            "parameters": {
                "type": "object",
                "properties": {
                    "borough_a": {"type": "string", "description": "First borough name in UPPERCASE"},
                    "borough_b": {"type": "string", "description": "Second borough name in UPPERCASE"}
                },
                "required": ["borough_a", "borough_b"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_routes_at_stop",
            "description": "Get all transit routes serving a specific stop. Returns route numbers, names, and types (bus, metro, etc.).",
            "parameters": {
                "type": "object",
                "properties": {
                    "stop_id": {"type": "string", "description": "The stop ID to look up"},
                    "agency": {"type": "string", "description": "Transit agency: 'STM' or 'STL'", "enum": ["STM", "STL"]}
                },
                "required": ["stop_id", "agency"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "simulate_population_change",
            "description": "Re-score a borough with an adjusted population to project how accessibility scores would change. Useful for planning around population growth or decline scenarios.",
            "parameters": {
                "type": "object",
                "properties": {
                    "borough": {"type": "string", "description": "Borough name in UPPERCASE"},
                    "growth_percent": {"type": "number", "description": "Population change as a percentage (e.g., 10 for +10%, -15 for -15%)"}
                },
                "required": ["borough", "growth_percent"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "estimate_project_cost",
            "description": "Estimate the total project cost, timeline, and phased plan to close all infrastructure gaps in a borough. Returns per-FSA gap analysis, facility deficit counts, cost ranges in CAD millions (Quebec benchmarks), and a prioritized phasing plan.",
            "parameters": {
                "type": "object",
                "properties": {
                    "borough": {
                        "type": "string",
                        "description": "Borough name in UPPERCASE (e.g., MONTREAL-NORD)"
                    }
                },
                "required": ["borough"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "flag_infrastructure_needs",
            "description": "Flag infrastructure needs for a borough: lists exactly what facilities are missing per FSA, simulates the new score if gaps were filled, calculates population benefited, and produces prioritized infrastructure flags with current score, projected score, and priority level (CRITICAL/HIGH/MEDIUM/LOW).",
            "parameters": {
                "type": "object",
                "properties": {
                    "borough": {
                        "type": "string",
                        "description": "Borough name in UPPERCASE (e.g., MONTREAL-NORD)"
                    }
                },
                "required": ["borough"]
            }
        }
    }
]


def _call_llm(messages: list[dict], tools: list[dict] | None = None) -> dict:
    """Call Databricks Foundation Model API."""
    cfg = Config()
    headers = {**cfg.authenticate(), "Content-Type": "application/json"}

    payload = {
        "messages": messages,
        "max_tokens": 4096,
        "temperature": 0.3,
    }
    if tools:
        payload["tools"] = tools
        payload["tool_choice"] = "auto"

    resp = requests.post(
        f"{cfg.host}/serving-endpoints/{_MODEL_ENDPOINT}/invocations",
        headers=headers,
        json=payload,
        timeout=120,
    )
    resp.raise_for_status()
    return resp.json()


def _execute_tool(name: str, args: dict) -> str:
    """Execute a tool call and return the result as a string."""
    from lib import queries

    try:
        if name == "score_borough":
            borough = args["borough"].upper().replace("'", "''")
            fsas = execute_sql(queries.BOROUGH_FSAS.format(borough=borough))
            if not fsas:
                return json.dumps({"error": f"Borough '{borough}' not found"})

            results = []
            for fsa in fsas:
                lat, lon = fsa["latitude"], fsa["longitude"]
                stops = execute_sql(queries.NEARBY_STOPS.format(lat=lat, lon=lon, radius=800))
                facilities = execute_sql(queries.NEARBY_FACILITIES.format(lat=lat, lon=lon, radius=1500))

                category_counts = {c: 0 for c in CATEGORIES}
                for f in facilities:
                    if f["category"] in category_counts:
                        category_counts[f["category"]] += 1

                scoring = calculate_fsa_score(category_counts, fsa["population"])

                avg_hw = None
                if stops:
                    sids = ",".join(f"'{s['stop_id']}'" for s in stops[:20])
                    hws = execute_sql(queries.STOP_HEADWAYS.format(stop_ids=sids, period="midday"))
                    if hws:
                        avg_hw = round(sum(h["avg_headway_min"] for h in hws) / len(hws), 1)
                results.append({
                    "postal_code": fsa["postal_code"],
                    "fsa_name": fsa["fsa_name"],
                    "population": fsa["population"],
                    "density_score": scoring["density_score"],
                    "legacy_score": scoring["legacy_score"],
                    "label": score_label(scoring["density_score"]),
                    "category_details": scoring["category_details"],
                    "categories_present": [c for c in CATEGORIES if category_counts[c] > 0],
                    "missing": [c for c in CATEGORIES if category_counts[c] == 0],
                    "stop_count": len(stops),
                    "avg_headway_min": avg_hw,
                })
            total_pop = sum(r["population"] for r in results)
            avg_density = round(sum(r["density_score"] for r in results) / len(results), 2) if results else 0
            underserved = [r for r in results if r["density_score"] < 2.5]
            return json.dumps({
                "borough": borough,
                "total_population": total_pop,
                "average_density_score": avg_density,
                "label": score_label(avg_density),
                "fsa_scores": results,
                "underserved_count": len(underserved),
                "underserved_population": sum(r["population"] for r in underserved),
            })

        elif name == "find_service_deserts":
            rows = execute_sql(queries.DESERT_DETECTION)
            for r in rows:
                counts = {
                    "healthcare": r.get("healthcare", 0),
                    "education": r.get("education", 0),
                    "cultural": r.get("cultural", 0),
                    "recreation": r.get("recreation", 0),
                }
                scoring = calculate_fsa_score(counts, r["population"])
                r["density_score"] = scoring["density_score"]
                r["label"] = score_label(scoring["density_score"])
                r["category_details"] = scoring["category_details"]
            deserts = [r for r in rows if r["density_score"] < 2.5]
            return json.dumps({
                "desert_count": len(deserts),
                "total_affected_population": sum(d["population"] for d in deserts),
                "deserts": deserts[:20],
            })

        elif name == "query_facilities_near":
            radius = args.get("radius_m", 1500)
            rows = execute_sql(queries.NEARBY_FACILITIES.format(lat=args["lat"], lon=args["lon"], radius=radius))
            return json.dumps({"facilities": rows[:30], "total": len(rows)})

        elif name == "query_transit_stops_near":
            radius = args.get("radius_m", 800)
            rows = execute_sql(queries.NEARBY_STOPS.format(lat=args["lat"], lon=args["lon"], radius=radius))
            return json.dumps({"stops": rows[:30], "total": len(rows)})

        elif name == "get_borough_population":
            borough = args["borough"].upper().replace("'", "''")
            rows = execute_sql(queries.BOROUGH_FSAS.format(borough=borough))
            return json.dumps({"borough": borough, "fsas": rows, "total_population": sum(r["population"] for r in rows)})

        elif name == "run_custom_sql":
            sql = _sanitize_sql(args["sql"])
            if sql is None:
                return json.dumps({"error": "Only read-only SELECT queries are allowed (no comments, no DDL/DML)."})
            rows = execute_sql(sql)
            return json.dumps({"rows": rows[:50], "total": len(rows)})

        elif name == "compare_boroughs":
            results = {}
            for key, borough_name in [("a", args["borough_a"]), ("b", args["borough_b"])]:
                borough = borough_name.upper().replace("'", "''")
                fsas = execute_sql(queries.BOROUGH_FSAS.format(borough=borough))
                if not fsas:
                    return json.dumps({"error": f"Borough '{borough}' not found"})

                fsa_scores = []
                cat_totals = {c: 0 for c in CATEGORIES}
                total_stops = 0
                headway_vals = []
                for fsa in fsas:
                    lat, lon = fsa["latitude"], fsa["longitude"]
                    stops = execute_sql(queries.NEARBY_STOPS.format(lat=lat, lon=lon, radius=800))
                    facilities = execute_sql(queries.NEARBY_FACILITIES.format(lat=lat, lon=lon, radius=1500))

                    counts = {c: 0 for c in CATEGORIES}
                    for f in facilities:
                        if f["category"] in counts:
                            counts[f["category"]] += 1
                    for c in CATEGORIES:
                        cat_totals[c] += counts[c]

                    scoring = calculate_fsa_score(counts, fsa["population"])
                    total_stops += len(stops)

                    if stops:
                        sids = ",".join(f"'{s['stop_id']}'" for s in stops[:20])
                        hws = execute_sql(queries.STOP_HEADWAYS.format(stop_ids=sids, period="midday"))
                        if hws:
                            headway_vals.extend(h["avg_headway_min"] for h in hws)

                    fsa_scores.append(scoring["density_score"])

                total_pop = sum(f["population"] for f in fsas)
                avg_score = round(sum(fsa_scores) / len(fsa_scores), 2) if fsa_scores else 0
                avg_hw = round(sum(headway_vals) / len(headway_vals), 1) if headway_vals else None
                underserved = [s for s in fsa_scores if s < 2.5]

                results[key] = {
                    "borough": borough,
                    "population": total_pop,
                    "fsa_count": len(fsas),
                    "avg_density_score": avg_score,
                    "label": score_label(avg_score),
                    "facility_counts": cat_totals,
                    "total_stops": total_stops,
                    "avg_headway_min": avg_hw,
                    "underserved_fsas": len(underserved),
                    "underserved_pct": round(len(underserved) / len(fsa_scores) * 100) if fsa_scores else 0,
                }

            a, b = results["a"], results["b"]
            advantages = {"a_leads": [], "b_leads": [], "tied": []}
            for metric in ["avg_density_score", "total_stops", "population"]:
                if a[metric] > b[metric]:
                    advantages["a_leads"].append(metric)
                elif b[metric] > a[metric]:
                    advantages["b_leads"].append(metric)
                else:
                    advantages["tied"].append(metric)
            if a.get("avg_headway_min") and b.get("avg_headway_min"):
                if a["avg_headway_min"] < b["avg_headway_min"]:
                    advantages["a_leads"].append("avg_headway_min (lower=better)")
                elif b["avg_headway_min"] < a["avg_headway_min"]:
                    advantages["b_leads"].append("avg_headway_min (lower=better)")

            return json.dumps({
                "borough_a": a,
                "borough_b": b,
                "advantages": advantages,
                "score_gap": round(a["avg_density_score"] - b["avg_density_score"], 2),
            })

        elif name == "get_routes_at_stop":
            agency = args["agency"].upper()
            stop_id = args["stop_id"]
            if agency == "STM":
                rows = execute_sql(queries.ROUTES_AT_STOP_STM.format(stop_id=stop_id.replace("'", "''")))
            elif agency == "STL":
                rows = execute_sql(queries.ROUTES_AT_STOP_STL.format(stop_id=stop_id.replace("'", "''")))
            else:
                return json.dumps({"error": "Agency must be 'STM' or 'STL'"})
            return json.dumps({"stop_id": stop_id, "agency": agency, "routes": rows, "route_count": len(rows)})

        elif name == "simulate_population_change":
            borough = args["borough"].upper().replace("'", "''")
            growth = args["growth_percent"]
            fsas = execute_sql(queries.BOROUGH_FSAS.format(borough=borough))
            if not fsas:
                return json.dumps({"error": f"Borough '{borough}' not found"})

            current_results = []
            simulated_results = []
            for fsa in fsas:
                lat, lon = fsa["latitude"], fsa["longitude"]
                facilities = execute_sql(queries.NEARBY_FACILITIES.format(lat=lat, lon=lon, radius=1500))
                counts = {c: 0 for c in CATEGORIES}
                for f in facilities:
                    if f["category"] in counts:
                        counts[f["category"]] += 1

                current_pop = fsa["population"]
                simulated_pop = max(1, int(current_pop * (1 + growth / 100)))

                current_scoring = calculate_fsa_score(counts, current_pop)
                simulated_scoring = calculate_fsa_score(counts, simulated_pop)

                current_results.append({
                    "postal_code": fsa["postal_code"],
                    "population": current_pop,
                    "density_score": current_scoring["density_score"],
                    "label": score_label(current_scoring["density_score"]),
                })
                simulated_results.append({
                    "postal_code": fsa["postal_code"],
                    "population": simulated_pop,
                    "density_score": simulated_scoring["density_score"],
                    "label": score_label(simulated_scoring["density_score"]),
                    "score_change": round(simulated_scoring["density_score"] - current_scoring["density_score"], 2),
                    "category_details": simulated_scoring["category_details"],
                })

            current_avg = round(sum(r["density_score"] for r in current_results) / len(current_results), 2)
            simulated_avg = round(sum(r["density_score"] for r in simulated_results) / len(simulated_results), 2)
            current_underserved = len([r for r in current_results if r["density_score"] < 2.5])
            simulated_underserved = len([r for r in simulated_results if r["density_score"] < 2.5])

            return json.dumps({
                "borough": borough,
                "growth_percent": growth,
                "current": {
                    "avg_score": current_avg,
                    "label": score_label(current_avg),
                    "underserved_fsas": current_underserved,
                },
                "simulated": {
                    "avg_score": simulated_avg,
                    "label": score_label(simulated_avg),
                    "underserved_fsas": simulated_underserved,
                },
                "score_change": round(simulated_avg - current_avg, 2),
                "new_underserved": simulated_underserved - current_underserved,
                "fsa_details": simulated_results,
            })

        elif name == "estimate_project_cost":
            from lib.costs import estimate_project_cost
            return json.dumps(estimate_project_cost(args["borough"]))

        elif name == "flag_infrastructure_needs":
            from lib.costs import flag_infrastructure_needs
            return json.dumps(flag_infrastructure_needs(args["borough"]))

        else:
            return json.dumps({"error": f"Unknown tool: {name}"})

    except Exception as e:
        logger.exception("Tool '%s' failed: %s", name, e)
        return json.dumps({"error": "Tool execution failed. Please try a different query."})


def chat_with_agent(user_message: str, history: list[dict] | None = None, summarize: bool = False) -> str:
    """Run a multi-turn conversation with the planning assistant, handling tool calls."""
    refusal = _screen_input(user_message)
    if refusal:
        return refusal

    messages = [{"role": "system", "content": SYSTEM_PROMPT}]

    if history:
        messages.extend(history[-20:])

    effective_message = user_message
    if summarize:
        effective_message += "\n\n[Respond concisely: bullet points and key metrics only, ~100 words max. No lengthy explanations.]"
    messages.append({"role": "user", "content": effective_message})

    # Multi-step tool calling loop (max 5 iterations)
    for _ in range(5):
        result = _call_llm(messages, tools=TOOLS)
        choice = result["choices"][0]
        msg = choice["message"]

        # If the model wants to call tools
        if msg.get("tool_calls"):
            messages.append(msg)
            for tc in msg["tool_calls"]:
                fn_name = tc["function"]["name"]
                fn_args = json.loads(tc["function"]["arguments"])
                tool_result = _execute_tool(fn_name, fn_args)
                messages.append({
                    "role": "tool",
                    "tool_call_id": tc["id"],
                    "content": tool_result,
                })
            continue

        # Model returned a final text response
        return msg.get("content", "I couldn't generate a response. Please try again.")

    return "Analysis complete but reached maximum tool call depth. Please refine your question."


def chat_with_agent_streaming(user_message: str, history: list[dict] | None = None, summarize: bool = False):
    """Generator that yields SSE events during agent execution for real-time feedback."""
    refusal = _screen_input(user_message)
    if refusal:
        yield json.dumps({"type": "done", "content": refusal})
        return

    messages = [{"role": "system", "content": SYSTEM_PROMPT}]

    if history:
        messages.extend(history[-20:])

    effective_message = user_message
    if summarize:
        effective_message += "\n\n[Respond concisely: bullet points and key metrics only, ~100 words max. No lengthy explanations.]"
    messages.append({"role": "user", "content": effective_message})

    for iteration in range(5):
        yield json.dumps({"type": "status", "content": f"Thinking (step {iteration + 1})..."})

        result = _call_llm(messages, tools=TOOLS)
        choice = result["choices"][0]
        msg = choice["message"]

        if msg.get("tool_calls"):
            messages.append(msg)
            for tc in msg["tool_calls"]:
                fn_name = tc["function"]["name"]
                fn_args = json.loads(tc["function"]["arguments"])
                yield json.dumps({"type": "tool_call", "tool": fn_name, "args": fn_args})

                tool_result = _execute_tool(fn_name, fn_args)
                messages.append({
                    "role": "tool",
                    "tool_call_id": tc["id"],
                    "content": tool_result,
                })
                yield json.dumps({"type": "tool_result", "tool": fn_name, "preview": tool_result[:200]})
            continue

        content = msg.get("content", "I couldn't generate a response. Please try again.")
        yield json.dumps({"type": "done", "content": content})
        return

    yield json.dumps({"type": "done", "content": "Analysis complete but reached maximum tool call depth. Please refine your question."})
