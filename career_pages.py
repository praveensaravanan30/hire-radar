"""
career_pages.py — Direct company career page scrapers.

Hits Greenhouse and Lever public JSON APIs (no key needed) for target companies.
These sources catch postings that don't always appear on Adzuna/JSearch/SerpAPI.

Greenhouse API: https://boards-api.greenhouse.io/v1/boards/{slug}/jobs
Lever API:      https://api.lever.co/v0/postings/{slug}?mode=json

Companies are grouped by track (HW / AI) and ATS (greenhouse / lever).
Add more companies by appending to the COMPANY_BOARDS list below.
"""

import hashlib
import requests
from rich.console import Console

console = Console()

# ---------------------------------------------------------------------------
# Company → ATS slug mapping
# ---------------------------------------------------------------------------

COMPANY_BOARDS = [
    # ── Hardware / Semiconductor ─────────────────────────────────────────────
    {"name": "Tenstorrent",  "ats": "greenhouse", "slug": "tenstorrent",          "track": "HW"},
    {"name": "Groq",         "ats": "greenhouse", "slug": "groq",                  "track": "HW"},
    {"name": "Cerebras",     "ats": "greenhouse", "slug": "cerebrasyasystems",     "track": "HW"},
    {"name": "Etched",       "ats": "greenhouse", "slug": "etched",                "track": "HW"},
    {"name": "Rivos",        "ats": "lever",      "slug": "rivos",                 "track": "HW"},
    {"name": "Ampere",       "ats": "lever",      "slug": "amperecomputing",       "track": "HW"},
    {"name": "d-Matrix",     "ats": "lever",      "slug": "d-matrix",              "track": "HW"},
    {"name": "SiFive",       "ats": "greenhouse", "slug": "sifive",                "track": "HW"},
    {"name": "Ventana",      "ats": "greenhouse", "slug": "ventanamicro",          "track": "HW"},
    {"name": "Untether AI",  "ats": "greenhouse", "slug": "untether",              "track": "HW"},

    # ── AI / ML ──────────────────────────────────────────────────────────────
    {"name": "Anthropic",    "ats": "greenhouse", "slug": "anthropic",             "track": "AI"},
    {"name": "Scale AI",     "ats": "greenhouse", "slug": "scaleai",               "track": "AI"},
    {"name": "Cohere",       "ats": "greenhouse", "slug": "cohere",                "track": "AI"},
    {"name": "Together AI",  "ats": "greenhouse", "slug": "togetherai",            "track": "AI"},
    {"name": "Baseten",      "ats": "greenhouse", "slug": "baseten",               "track": "AI"},
    {"name": "Replicate",    "ats": "lever",      "slug": "replicate",             "track": "AI"},
    {"name": "Modal",        "ats": "lever",      "slug": "modal-labs",            "track": "AI"},
    {"name": "Hugging Face", "ats": "lever",      "slug": "huggingface",           "track": "AI"},
    {"name": "Weights & Biases", "ats": "lever",  "slug": "wandb",                 "track": "AI"},
]

TIMEOUT = 12


# ---------------------------------------------------------------------------
# Fetchers
# ---------------------------------------------------------------------------

def _job_id_career(ats: str, slug: str, raw_id) -> str:
    return hashlib.md5(f"career:{ats}:{slug}:{raw_id}".encode()).hexdigest()


def fetch_greenhouse(company_name: str, slug: str) -> list[dict]:
    """Fetch all jobs from a Greenhouse board."""
    try:
        url = f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs"
        r = requests.get(url, params={"content": "true"}, timeout=TIMEOUT)
        if r.status_code == 404:
            return []
        r.raise_for_status()
        jobs = []
        for j in r.json().get("jobs", []):
            dept = ""
            depts = j.get("departments", [])
            if depts:
                dept = depts[0].get("name", "")
            jobs.append({
                "source_id": str(j.get("id", "")),
                "title":     j.get("title", ""),
                "company":   company_name,
                "location":  j.get("location", {}).get("name", ""),
                "url":       j.get("absolute_url", ""),
                "description": _strip_html(j.get("content", ""))[:1500],
                "department": dept,
                "source":    "greenhouse",
            })
        return jobs
    except Exception as e:
        console.print(f"[dim yellow]Greenhouse ({slug}): {e}[/dim yellow]")
        return []


def fetch_lever(company_name: str, slug: str) -> list[dict]:
    """Fetch all jobs from a Lever board."""
    try:
        url = f"https://api.lever.co/v0/postings/{slug}"
        r = requests.get(url, params={"mode": "json"}, timeout=TIMEOUT)
        if r.status_code == 404:
            return []
        r.raise_for_status()
        jobs = []
        for j in r.json():
            cats = j.get("categories", {})
            jobs.append({
                "source_id": j.get("id", ""),
                "title":     j.get("text", ""),
                "company":   company_name,
                "location":  cats.get("location", j.get("workplaceType", "")),
                "url":       j.get("hostedUrl", ""),
                "description": _build_lever_description(j)[:1500],
                "department": cats.get("department", ""),
                "source":    "lever",
            })
        return jobs
    except Exception as e:
        console.print(f"[dim yellow]Lever ({slug}): {e}[/dim yellow]")
        return []


def _strip_html(html: str) -> str:
    """Very lightweight HTML stripper — no extra deps needed."""
    import re
    text = re.sub(r"<[^>]+>", " ", html or "")
    return re.sub(r"\s+", " ", text).strip()


def _build_lever_description(j: dict) -> str:
    """Combine Lever's list/description blocks into plain text."""
    parts = []
    for block in j.get("descriptionPlain", "").split("\n"):
        if block.strip():
            parts.append(block.strip())
    for lst in j.get("lists", []):
        parts.append(lst.get("text", ""))
        for item in lst.get("content", "").split("<li>"):
            clean = _strip_html(item).strip()
            if clean:
                parts.append(f"- {clean}")
    return "\n".join(parts)


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def fetch_all_career_pages(track_key: str, role_keywords: list[str]) -> list[dict]:
    """
    Fetch jobs from all career pages for the given track.
    Filters by role_keywords (must appear in title — case-insensitive).
    Returns job dicts in the same format as other fetchers.

    Args:
        track_key:     'HW' or 'AI'
        role_keywords: list of title keywords to filter on
                       e.g. ['verification', 'DV', 'RTL'] for DV role
    """
    boards = [b for b in COMPANY_BOARDS if b["track"] == track_key]
    kws = [k.lower() for k in role_keywords]

    all_jobs: list[dict] = []
    for board in boards:
        name, ats, slug = board["name"], board["ats"], board["slug"]

        if ats == "greenhouse":
            raw = fetch_greenhouse(name, slug)
        elif ats == "lever":
            raw = fetch_lever(name, slug)
        else:
            continue

        for j in raw:
            title_lower = j["title"].lower()
            # Title must contain at least one role keyword
            if kws and not any(k in title_lower for k in kws):
                continue
            j["role_track"] = track_key
            all_jobs.append(j)

    return all_jobs


def career_page_sources_for_track(track_key: str) -> list[str]:
    """Return company names that will be scraped for a given track."""
    return [b["name"] for b in COMPANY_BOARDS if b["track"] == track_key]
