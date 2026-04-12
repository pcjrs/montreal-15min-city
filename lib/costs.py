"""Project cost estimation and infrastructure gap flagging for Montreal boroughs."""

import json

from lib.db import execute_sql
from lib import queries
from lib.scoring import calculate_fsa_score, CATEGORIES, THRESHOLDS, score_label

# Quebec/Montreal construction benchmarks (CAD, millions)
FACILITY_COSTS = {
    "healthcare": {"label": "CLSC / Health Clinic", "low": 15, "high": 25},
    "education": {"label": "School / Library Branch", "low": 20, "high": 50},
    "cultural": {"label": "Library / Cultural Centre", "low": 8, "high": 15},
    "recreation": {"label": "Community Center / Park", "low": 5, "high": 15},
}

# Timeline benchmarks
FACILITY_TIMELINES = {
    "healthcare": {"planning": 12, "design": 12, "construction": 24, "total_range": "3-4 years"},
    "education": {"planning": 12, "design": 18, "construction": 30, "total_range": "4-5 years"},
    "cultural": {"planning": 9, "design": 12, "construction": 18, "total_range": "2.5-3.5 years"},
    "recreation": {"planning": 6, "design": 9, "construction": 12, "total_range": "1.5-2.5 years"},
}

PRIORITY_ORDER = ["healthcare", "education", "recreation", "cultural"]


def estimate_project_cost(borough: str) -> dict:
    """Calculate cost/timeline to close all infrastructure gaps in a borough."""
    borough = borough.upper().replace("'", "''")
    fsas = execute_sql(queries.BOROUGH_FSAS.format(borough=borough))
    if not fsas:
        return {"error": f"Borough '{borough}' not found"}

    fsa_details = []
    total_needed = {c: 0 for c in CATEGORIES}
    total_cost_low = 0.0
    total_cost_high = 0.0

    for fsa in fsas:
        lat, lon = fsa["latitude"], fsa["longitude"]
        facilities = execute_sql(queries.NEARBY_FACILITIES.format(lat=lat, lon=lon, radius=1500))

        counts = {c: 0 for c in CATEGORIES}
        for f in facilities:
            if f["category"] in counts:
                counts[f["category"]] += 1

        scoring = calculate_fsa_score(counts, fsa["population"])
        gaps = []
        for detail in scoring["category_details"]:
            cat = detail["category"]
            deficit = detail["expected"] - detail["actual"]
            if deficit > 0:
                cost_info = FACILITY_COSTS[cat]
                gaps.append({
                    "category": cat,
                    "facility_type": cost_info["label"],
                    "current": detail["actual"],
                    "needed": detail["expected"],
                    "deficit": deficit,
                    "cost_low_M": round(deficit * cost_info["low"], 1),
                    "cost_high_M": round(deficit * cost_info["high"], 1),
                    "timeline": FACILITY_TIMELINES[cat]["total_range"],
                })
                total_needed[cat] += deficit
                total_cost_low += deficit * cost_info["low"]
                total_cost_high += deficit * cost_info["high"]

        if gaps:
            fsa_details.append({
                "postal_code": fsa["postal_code"],
                "fsa_name": fsa["fsa_name"],
                "population": fsa["population"],
                "current_score": scoring["density_score"],
                "label": score_label(scoring["density_score"]),
                "gaps": gaps,
            })

    # Build phased plan
    phases = []
    for i, cat in enumerate(PRIORITY_ORDER):
        if total_needed[cat] > 0:
            ci = FACILITY_COSTS[cat]
            phases.append({
                "phase": i + 1,
                "category": cat,
                "facility_type": ci["label"],
                "facilities_needed": total_needed[cat],
                "cost_range_M": f"${total_needed[cat] * ci['low']}-{total_needed[cat] * ci['high']}M",
                "timeline": FACILITY_TIMELINES[cat]["total_range"],
            })

    return {
        "borough": borough,
        "total_population": sum(f["population"] for f in fsas),
        "fsas_with_gaps": len(fsa_details),
        "total_fsas": len(fsas),
        "total_facilities_needed": sum(total_needed.values()),
        "total_cost_range_M": f"${round(total_cost_low)}-{round(total_cost_high)}M",
        "cost_low_M": round(total_cost_low, 1),
        "cost_high_M": round(total_cost_high, 1),
        "phased_plan": phases,
        "fsa_details": fsa_details[:15],
        "facilities_needed_by_category": total_needed,
    }


def flag_infrastructure_needs(borough: str) -> dict:
    """Identify gaps per FSA, simulate filled scores, and produce prioritized infrastructure flags."""
    borough = borough.upper().replace("'", "''")
    fsas = execute_sql(queries.BOROUGH_FSAS.format(borough=borough))
    if not fsas:
        return {"error": f"Borough '{borough}' not found"}

    flags = []
    total_beneficiaries = 0
    total_facilities_needed = 0
    borough_current_scores = []
    borough_projected_scores = []

    for fsa in fsas:
        lat, lon = fsa["latitude"], fsa["longitude"]
        facilities = execute_sql(queries.NEARBY_FACILITIES.format(lat=lat, lon=lon, radius=1500))

        counts = {c: 0 for c in CATEGORIES}
        for f in facilities:
            if f["category"] in counts:
                counts[f["category"]] += 1

        current_scoring = calculate_fsa_score(counts, fsa["population"])
        current_score = current_scoring["density_score"]
        borough_current_scores.append(current_score)

        # Determine what's missing and simulate filling gaps
        needed_facilities = []
        filled_counts = dict(counts)
        for detail in current_scoring["category_details"]:
            cat = detail["category"]
            deficit = detail["expected"] - detail["actual"]
            if deficit > 0:
                needed_facilities.append({
                    "category": cat,
                    "facility_type": FACILITY_COSTS[cat]["label"],
                    "current": detail["actual"],
                    "needed": detail["expected"],
                    "deficit": deficit,
                })
                filled_counts[cat] = detail["expected"]
                total_facilities_needed += deficit

        # Simulate score with gaps filled
        projected_scoring = calculate_fsa_score(filled_counts, fsa["population"])
        projected_score = projected_scoring["density_score"]
        borough_projected_scores.append(projected_score)

        # Assign priority
        if current_score < 1.0:
            priority = "CRITICAL"
        elif current_score < 2.0:
            priority = "HIGH"
        elif current_score < 2.5:
            priority = "MEDIUM"
        elif needed_facilities:
            priority = "LOW"
        else:
            priority = "NONE"

        if needed_facilities:
            total_beneficiaries += fsa["population"]
            flags.append({
                "postal_code": fsa["postal_code"],
                "fsa_name": fsa["fsa_name"],
                "population": fsa["population"],
                "current_score": current_score,
                "current_label": score_label(current_score),
                "projected_score": projected_score,
                "projected_label": score_label(projected_score),
                "score_improvement": round(projected_score - current_score, 2),
                "facilities_needed": needed_facilities,
                "total_deficit": sum(n["deficit"] for n in needed_facilities),
                "priority": priority,
            })

    # Sort: CRITICAL first, then by score_improvement desc
    priority_order = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3, "NONE": 4}
    flags.sort(key=lambda f: (priority_order.get(f["priority"], 4), -f["score_improvement"]))

    avg_current = round(sum(borough_current_scores) / len(borough_current_scores), 2) if borough_current_scores else 0
    avg_projected = round(sum(borough_projected_scores) / len(borough_projected_scores), 2) if borough_projected_scores else 0

    return {
        "borough": borough,
        "total_population": sum(f["population"] for f in fsas),
        "total_beneficiaries": total_beneficiaries,
        "total_facilities_needed": total_facilities_needed,
        "fsas_with_gaps": len(flags),
        "total_fsas": len(fsas),
        "borough_current_score": avg_current,
        "borough_current_label": score_label(avg_current),
        "borough_projected_score": avg_projected,
        "borough_projected_label": score_label(avg_projected),
        "borough_score_improvement": round(avg_projected - avg_current, 2),
        "infrastructure_flags": flags[:20],
        "priority_summary": {
            "CRITICAL": len([f for f in flags if f["priority"] == "CRITICAL"]),
            "HIGH": len([f for f in flags if f["priority"] == "HIGH"]),
            "MEDIUM": len([f for f in flags if f["priority"] == "MEDIUM"]),
            "LOW": len([f for f in flags if f["priority"] == "LOW"]),
        },
    }
