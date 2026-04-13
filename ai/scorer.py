"""
Keyword-based job relevance scorer (no API key required).

Scores 0–100 across four tiers:
  Tier 1 (50 pts) — domain keyword matches
  Tier 2 (25 pts) — position type fit
  Tier 3 (15 pts) — location match
  Tier 4 (10 pts) — no senior-role exclusion keywords
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from scrapers.base import classify_job_type

DOMAIN_KEYWORDS = [
    "computer vision",
    "generative ai",
    "generative model",
    "explainable ai",
    "diffusion model",
    "diffusion models",
    "transformers",
    "representation learning",
    "deep learning",
    "machine learning",
    "image generation",
    "scene understanding",
    "pytorch",
    "neural network",
    "foundation model",
    "multimodal",
    "visual language",
    "scene layout",
    "object detection",
    "image synthesis",
]

TARGET_TYPE_SCORES = {
    "phd": 25,
    "postdoc": 25,
    "research_scientist": 20,
    "ml_engineer": 15,
    "other": 5,
}

LOCATION_KEYWORDS = [
    "germany",
    "europe",
    "remote",
    "saarland",
    "berlin",
    "munich",
    "münchen",
    "hamburg",
    "zürich",
    "zurich",
    "amsterdam",
    "oxford",
    "cambridge",
    "paris",
    "london",
    "netherlands",
    "switzerland",
    "austria",
    "sweden",
    "denmark",
]

EXCLUDE_KEYWORDS = [
    "10+ years",
    "15+ years",
    "senior director",
    "vp of",
    "vice president",
    "chief ",
    "c-level",
]


def score_job(title: str, organization: str, description: str, **kwargs) -> dict:
    """
    Score a job posting using keyword matching.

    Returns:
        {
            "score": int (0-100),
            "reasoning": str,
            "job_type_detected": str,
            "include_recommendation_letter": bool,
        }
    """
    text = (title + " " + description).lower()

    # Tier 1 — domain keyword matches (up to 50 pts, 8 pts each)
    matched_keywords = [kw for kw in DOMAIN_KEYWORDS if kw in text]
    tier1 = min(50, len(matched_keywords) * 8)

    # Tier 2 — position type fit (up to 25 pts)
    job_type = classify_job_type(title, description)
    tier2 = TARGET_TYPE_SCORES.get(job_type, 5)

    # Tier 3 — location match (up to 15 pts)
    tier3 = 15 if any(loc in text for loc in LOCATION_KEYWORDS) else 0

    # Tier 4 — no exclusion keywords (up to 10 pts)
    tier4 = 0 if any(ex in text for ex in EXCLUDE_KEYWORDS) else 10

    total = min(100, tier1 + tier2 + tier3 + tier4)

    if matched_keywords:
        kw_summary = ", ".join(matched_keywords[:4])
        if len(matched_keywords) > 4:
            kw_summary += f" (+{len(matched_keywords) - 4} more)"
        reasoning = f"Matched {len(matched_keywords)} keyword(s): {kw_summary}. Position type: {job_type}."
    else:
        reasoning = f"No domain keyword matches. Position type: {job_type}."

    return {
        "score": total,
        "reasoning": reasoning,
        "job_type_detected": job_type,
        "include_recommendation_letter": job_type in ("phd", "postdoc"),
    }
