"""Density-aware scoring for the 15-minute city accessibility auditor."""

CATEGORIES = ["healthcare", "education", "cultural", "recreation"]

# Per-capita thresholds: 1 facility per N people
THRESHOLDS = {
    "healthcare": 5000,   # WHO + Quebec CLSC density (clinics, CLSCs, hospitals)
    "education": 4000,    # Quebec school placement + library branch density
    "cultural": 15000,    # Destination-based; lower density expected
    "recreation": 3000,   # Canadian Parks & Rec Assoc; neighborhood-scale
}

PRESENCE_WEIGHT = 0.3
ADEQUACY_WEIGHT = 0.7


def calculate_category_score(count: int, population: int, threshold: int) -> dict:
    """Score a single category based on facility count relative to population need.

    Returns dict with: score (0.0-1.0), present, adequacy_ratio, expected, actual.
    """
    expected = max(1, population // threshold)
    present = count >= 1
    presence_score = PRESENCE_WEIGHT if present else 0.0
    adequacy_ratio = min(1.0, count / expected) if expected > 0 else 1.0
    adequacy_score = min(ADEQUACY_WEIGHT, ADEQUACY_WEIGHT * adequacy_ratio)

    return {
        "score": round(presence_score + adequacy_score, 2),
        "present": present,
        "adequacy_ratio": round(adequacy_ratio, 2),
        "expected": expected,
        "actual": count,
    }


def calculate_fsa_score(facility_counts: dict, population: int) -> dict:
    """Compute density-aware composite score for an FSA.

    Args:
        facility_counts: {"healthcare": N, "education": N, "cultural": N, "recreation": N}
        population: FSA population

    Returns dict with: density_score, legacy_score, category_details[].
    """
    category_details = []
    density_total = 0.0
    legacy_total = 0

    for cat in CATEGORIES:
        count = facility_counts.get(cat, 0)
        detail = calculate_category_score(count, population, THRESHOLDS[cat])
        detail["category"] = cat
        category_details.append(detail)
        density_total += detail["score"]
        if count > 0:
            legacy_total += 1

    return {
        "density_score": round(density_total, 2),
        "legacy_score": legacy_total,
        "category_details": category_details,
    }


def score_label(score: float) -> str:
    """Human-readable label for a 0.0-4.0 density score."""
    if score >= 3.5:
        return "Well-Served"
    if score >= 2.5:
        return "Adequate"
    if score >= 1.5:
        return "Underserved"
    if score >= 0.5:
        return "Poorly Served"
    return "Service Desert"
