#!/usr/bin/env python3
"""
Job Tracker — AI-powered job notification tool for Praveen's two role tracks.

Pipeline:
  Stage 1 — Pick resume track (AI or Hardware)
  Stage 2 — Pick sub-role + optional extra keywords
  Stage 3 — Pick company focus (Tier 1, Tier 2, crossover, custom)
  Stage 4 — Preview generated search queries → confirm or edit → run

Sources:  Adzuna (free) · Remotive (AI track) · JSearch (optional) · Google Jobs (optional)
Scoring:  Any OpenAI-compatible LLM (Groq free, Gemini free, Ollama local, Anthropic/OpenAI paid)
Alerts:   macOS desktop notifications
Storage:  SQLite deduplication across runs

Usage:
  python tracker.py                          # interactive 4-stage flow
  python tracker.py --role dv                # skip menu, use DV role
  python tracker.py --role dv --keywords "gpu arm"
  python tracker.py --all                    # all roles (cron mode)
  python tracker.py --loop --role rtl       # scheduled, RTL only
  python tracker.py --digest                 # show today's matches
"""

import argparse
import hashlib
import json
import os
import re
import sqlite3
import subprocess
import time
from datetime import datetime, date
from pathlib import Path
from typing import Optional

import requests
import schedule
from dotenv import load_dotenv
from openai import OpenAI
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt, Confirm
from rich.table import Table
from rich.text import Text

load_dotenv(Path(__file__).parent / ".env")

from config import TRACKS, COMPANIES, MIN_SCORE, TIER1_BONUS, CHECK_INTERVAL_HOURS, MAX_JOBS_PER_QUERY
from query_builder import build_queries, all_queries, display_query_preview
from career_pages import fetch_all_career_pages, career_page_sources_for_track

console = Console()
DB_PATH = Path(__file__).parent / "jobs.db"


# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------

LIFECYCLE_STATUSES = ["new", "reviewed", "applied", "interviewing", "offer", "rejected", "skipped"]

def init_db():
    con = sqlite3.connect(DB_PATH)
    con.execute("""
        CREATE TABLE IF NOT EXISTS jobs (
            id          TEXT PRIMARY KEY,
            role_track  TEXT,
            role_key    TEXT,
            title       TEXT,
            company     TEXT,
            location    TEXT,
            url         TEXT,
            score       INTEGER,
            reason      TEXT,
            source      TEXT,
            found_at    TEXT,
            notified    INTEGER DEFAULT 0,
            status      TEXT DEFAULT 'new',
            updated_at  TEXT
        )
    """)
    # Migrate existing DB — add columns if missing
    existing = {row[1] for row in con.execute("PRAGMA table_info(jobs)")}
    for col, defn in [("status", "TEXT DEFAULT 'new'"), ("updated_at", "TEXT")]:
        if col not in existing:
            con.execute(f"ALTER TABLE jobs ADD COLUMN {col} {defn}")
    con.commit()
    return con


def job_exists(con: sqlite3.Connection, job_id: str) -> bool:
    return con.execute("SELECT 1 FROM jobs WHERE id=?", (job_id,)).fetchone() is not None


def save_job(con: sqlite3.Connection, job: dict):
    con.execute("""
        INSERT OR IGNORE INTO jobs
          (id, role_track, role_key, title, company, location, url,
           score, reason, source, found_at)
        VALUES (:id, :role_track, :role_key, :title, :company, :location,
                :url, :score, :reason, :source, :found_at)
    """, job)
    con.commit()


def mark_notified(con: sqlite3.Connection, job_id: str):
    con.execute("UPDATE jobs SET notified=1 WHERE id=?", (job_id,))
    con.commit()


def update_status(con: sqlite3.Connection, job_id: str, status: str):
    con.execute(
        "UPDATE jobs SET status=?, updated_at=? WHERE id=?",
        (status, datetime.now().isoformat(), job_id),
    )
    con.commit()


def find_jobs_by_url_fragment(con: sqlite3.Connection, fragment: str) -> list[tuple]:
    """Find jobs where URL contains fragment — used by --update CLI."""
    return con.execute(
        "SELECT id, title, company, status FROM jobs WHERE url LIKE ?",
        (f"%{fragment}%",),
    ).fetchall()


# ---------------------------------------------------------------------------
# Job fetching
# ---------------------------------------------------------------------------

def _job_id(source: str, raw_id) -> str:
    return hashlib.md5(f"{source}:{raw_id}".encode()).hexdigest()


def fetch_adzuna(query: str) -> list[dict]:
    app_id = os.getenv("ADZUNA_APP_ID")
    app_key = os.getenv("ADZUNA_APP_KEY")
    if not app_id or not app_key:
        return []
    try:
        r = requests.get(
            "https://api.adzuna.com/v1/api/jobs/us/search/1",
            params={
                "app_id": app_id, "app_key": app_key,
                "what": query,
                "results_per_page": MAX_JOBS_PER_QUERY,
                "sort_by": "date", "max_days_old": 14,
            },
            timeout=15,
        )
        r.raise_for_status()
        return [
            {
                "source_id": j.get("id", ""),
                "title": j.get("title", ""),
                "company": j.get("company", {}).get("display_name", "Unknown"),
                "location": j.get("location", {}).get("display_name", ""),
                "url": j.get("redirect_url", ""),
                "description": j.get("description", ""),
                "source": "adzuna",
            }
            for j in r.json().get("results", [])
        ]
    except Exception as e:
        console.print(f"[dim yellow]Adzuna: {e}[/dim yellow]")
        return []


def fetch_remotive(query: str) -> list[dict]:
    try:
        r = requests.get(
            "https://remotive.com/api/remote-jobs",
            params={"search": query, "limit": MAX_JOBS_PER_QUERY},
            timeout=15,
        )
        r.raise_for_status()
        cutoff = datetime.now().timestamp() - (5 * 86400)  # 5 days
        jobs = []
        for j in r.json().get("jobs", []):
            pub = j.get("publication_date", "")
            try:
                ts = datetime.fromisoformat(pub.rstrip("Z")).timestamp()
                if ts < cutoff:
                    continue
            except Exception:
                pass
            jobs.append({
                "source_id": str(j.get("id", "")),
                "title": j.get("title", ""),
                "company": j.get("company_name", "Unknown"),
                "location": j.get("candidate_required_location", "Remote"),
                "url": j.get("url", ""),
                "description": j.get("description", "")[:1500],
                "source": "remotive",
            })
        return jobs
    except Exception as e:
        console.print(f"[dim yellow]Remotive: {e}[/dim yellow]")
        return []


def fetch_jsearch(query: str) -> list[dict]:
    key = os.getenv("RAPIDAPI_JSEARCH_KEY")
    if not key:
        return []
    try:
        r = requests.get(
            "https://jsearch.p.rapidapi.com/search",
            headers={"X-RapidAPI-Key": key, "X-RapidAPI-Host": "jsearch.p.rapidapi.com"},
            params={"query": f"{query} United States", "page": "1",
                    "num_pages": "1", "date_posted": "week"},
            timeout=15,
        )
        r.raise_for_status()
        return [
            {
                "source_id": j.get("job_id", ""),
                "title": j.get("job_title", ""),
                "company": j.get("employer_name", "Unknown"),
                "location": f"{j.get('job_city', '')}, {j.get('job_state', '')}".strip(", "),
                "url": j.get("job_apply_link", j.get("job_google_link", "")),
                "description": (j.get("job_description") or "")[:1500],
                "source": "jsearch",
            }
            for j in r.json().get("data", [])[:MAX_JOBS_PER_QUERY]
        ]
    except Exception as e:
        console.print(f"[dim yellow]JSearch: {e}[/dim yellow]")
        return []


def fetch_google_jobs(query: str) -> list[dict]:
    key = os.getenv("SERPAPI_KEY")
    if not key:
        return []
    try:
        r = requests.get(
            "https://serpapi.com/search",
            params={
                "engine": "google_jobs",
                "q": query,
                "api_key": key,
                "chips": "date_posted:week",
                "hl": "en",
                "gl": "us",
            },
            timeout=15,
        )
        r.raise_for_status()
        return [
            {
                "source_id": j.get("job_id", j.get("title", "") + j.get("company_name", "")),
                "title": j.get("title", ""),
                "company": j.get("company_name", "Unknown"),
                "location": j.get("location", ""),
                "url": (j.get("related_links") or [{}])[0].get("link", ""),
                "description": j.get("description", "")[:1500],
                "source": "google_jobs",
            }
            for j in r.json().get("jobs_results", [])[:MAX_JOBS_PER_QUERY]
        ]
    except Exception as e:
        console.print(f"[dim yellow]Google Jobs: {e}[/dim yellow]")
        return []


def fetch_jobs_for_queries(
    track_key: str,
    queries: list[str],
    role_key: str,
    role: dict,
) -> list[dict]:
    """
    Fetch jobs across sources with per-source query strategy:

    Adzuna    — AND-matches all words, so use short title-only queries (3-4 words max).
                Pull titles directly from role keyword_groups['titles'].
    JSearch   — full enriched queries (handles long strings well)
    Google Jobs — full enriched queries
    Remotive  — AI track only, short queries

    HW track skips Remotive (almost no hardware jobs there).
    """
    is_hw = (track_key == "HW")
    seen_urls: set[str] = set()
    jobs: list[dict] = []

    def _add(new_jobs):
        for j in new_jobs:
            url = j.get("url", "")
            if url and url not in seen_urls:
                seen_urls.add(url)
                j["role_track"] = track_key
                j["role_key"] = role_key
                jobs.append(j)

    # Adzuna: use only the role's title list (short, clean job title strings)
    adzuna_queries = role.get("keyword_groups", {}).get("titles", queries[:3])
    for q in adzuna_queries:
        _add(fetch_adzuna(q))

    # JSearch + Google Jobs: full enriched + company-targeted queries
    for q in queries:
        _add(fetch_jsearch(q))
        _add(fetch_google_jobs(q))

    # Remotive: AI track only, use short title queries
    if not is_hw:
        for q in adzuna_queries[:3]:
            _add(fetch_remotive(q))

    # Direct company career pages (Greenhouse + Lever — no API key needed)
    career_kws = role.get("keyword_groups", {}).get("titles", [])
    # Flatten titles into individual words for title matching
    title_words = []
    for t in career_kws:
        title_words.extend(t.lower().split())
    # Also add must_have_any short terms
    for kw in role.get("must_have_any", [])[:5]:
        title_words.append(kw.lower())
    career_jobs = fetch_all_career_pages(track_key, list(set(title_words)))
    for j in career_jobs:
        j["role_key"] = role_key
        url = j.get("url", "")
        if url and url not in seen_urls:
            seen_urls.add(url)
            jobs.append(j)

    return jobs


# ---------------------------------------------------------------------------
# Pre-filter (must_have_any check — runs before LLM to skip obvious mismatches)
# ---------------------------------------------------------------------------

# Titles that almost always require 7+ years — drop before LLM
_OVERQUALIFIED_TITLES = [
    "principal", "staff engineer", "distinguished", "fellow",
    "director", "vp ", "vice president", "head of", "chief ",
    "managing", "manager,", "manager ",
]

def passes_prefilter(job: dict, role: dict) -> bool:
    title = job.get("title", "").lower()
    text  = f"{title} {job.get('description', '')}".lower()

    # Drop roles that are clearly too senior
    if any(kw in title for kw in _OVERQUALIFIED_TITLES):
        return False

    # Must contain at least one domain keyword
    return any(kw.lower() in text for kw in role.get("must_have_any", []))


# ---------------------------------------------------------------------------
# AI Scoring
# ---------------------------------------------------------------------------

def build_ai_client() -> tuple[OpenAI, str]:
    provider = os.getenv("AI_PROVIDER", "groq").lower()

    if provider == "groq":
        key = os.getenv("GROQ_API_KEY")
        if not key:
            raise ValueError("GROQ_API_KEY not set. Free key at console.groq.com")
        return (OpenAI(api_key=key, base_url="https://api.groq.com/openai/v1"),
                os.getenv("GROQ_MODEL", "llama-3.1-8b-instant"))

    if provider == "gemini":
        key = os.getenv("GEMINI_API_KEY")
        if not key:
            raise ValueError("GEMINI_API_KEY not set. Free key at aistudio.google.com")
        return (OpenAI(api_key=key, base_url="https://generativelanguage.googleapis.com/v1beta/openai/"),
                os.getenv("GEMINI_MODEL", "gemini-1.5-flash"))

    if provider == "ollama":
        return (OpenAI(api_key="ollama", base_url=os.getenv("OLLAMA_URL", "http://localhost:11434/v1")),
                os.getenv("OLLAMA_MODEL", "llama3.2"))

    if provider == "anthropic":
        key = os.getenv("ANTHROPIC_API_KEY")
        if not key:
            raise ValueError("ANTHROPIC_API_KEY not set.")
        return (OpenAI(api_key=key, base_url="https://api.anthropic.com/v1"),
                os.getenv("ANTHROPIC_MODEL", "claude-3-5-haiku-20241022"))

    if provider == "openai":
        key = os.getenv("OPENAI_API_KEY")
        if not key:
            raise ValueError("OPENAI_API_KEY not set.")
        return OpenAI(api_key=key), os.getenv("OPENAI_MODEL", "gpt-4o-mini")

    raise ValueError(f"Unknown AI_PROVIDER '{provider}'. Options: groq, gemini, ollama, anthropic, openai")


def score_job(
    client: OpenAI,
    model: str,
    job: dict,
    role: dict,
    tier1_companies: list[str],
) -> tuple[int, str]:
    """Score a job 0-10. Adds TIER1_BONUS if company is in tier1_companies."""
    company_hint = ""
    if any(c.lower() in job.get("company", "").lower() for c in tier1_companies):
        company_hint = (
            f"\nNOTE: '{job['company']}' is a top-tier target employer for this candidate. "
            f"Add {TIER1_BONUS} bonus point to your score."
        )

    prompt = f"""You are evaluating job fit for a candidate. Score this job 0-10 for fit.

CANDIDATE PROFILE:
{role['scoring_context'].strip()}
{company_hint}

JOB POSTING:
Title: {job['title']}
Company: {job['company']}
Location: {job['location']}
Description:
{(job.get('description') or '')[:1200]}

EXPERIENCE LEVEL: Candidate has ~2-3 years total experience (1 internship + research + current role).
Score 0-2 if the role explicitly requires 5+ years. Score 3-4 if it requires 4-5 years.
Only score 6+ if the role is entry-level, new-grad, 0-3 years, or doesn't state a minimum.
"Senior" in the title is okay if the description says 3-5 years — use judgment.

Reply with ONLY valid JSON: {{"score": <0-10 int>, "reason": "<max 12 words: why fit or not>"}}
Rubric: 10=perfect fit, 7-9=strong, 5-6=stretch/worth a shot, 0-4=poor or overqualified.
"""
    try:
        resp = client.chat.completions.create(
            model=model,
            max_tokens=150,
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"},
        )
        data = json.loads(resp.choices[0].message.content.strip())
        return int(data.get("score", 0)), data.get("reason", "")
    except Exception as e:
        console.print(f"[dim yellow]Scoring error: {e}[/dim yellow]")
        return 0, "scoring failed"


# ---------------------------------------------------------------------------
# Notifications
# ---------------------------------------------------------------------------

def notify_macos(title: str, subtitle: str, body: str):
    body_safe = body.replace('"', "'")[:100]
    subtitle_safe = subtitle.replace('"', "'")
    script = (
        f'display notification "{body_safe}" '
        f'with title "{title}" subtitle "{subtitle_safe}" sound name "Ping"'
    )
    try:
        subprocess.run(["osascript", "-e", script], check=True, capture_output=True)
    except Exception:
        pass


def notify_job(job: dict, score: int, reason: str, role_label: str):
    title = f"Job Match [{score}/10] — {role_label}"
    subtitle = f"{job['company']}  |  {job['location'] or 'Remote'}"
    body = f"{job['title']} — {reason}"
    notify_macos(title, subtitle, body)
    score_color = "green" if score >= 8 else "yellow"
    url = job.get("url", "")
    console.print(
        f"  [bold {score_color}]NOTIFY[/bold {score_color}] "
        f"[{score_color}][{score}/10][/{score_color}] "
        f"{job['title']} @ [bold]{job['company']}[/bold]"
        + (f"\n         [dim][link={url}]{url}[/link][/dim]" if url else "")
    )


# ---------------------------------------------------------------------------
# Interactive 4-stage selector
# ---------------------------------------------------------------------------

def _fuzzy_match_role(user_input: str) -> Optional[tuple[str, str, dict]]:
    """
    Match user text against role aliases.
    Returns (track_key, role_key, role_dict) or None if no match.
    """
    text = user_input.lower().strip()
    for track_key, track in TRACKS.items():
        for role_key, role in track["roles"].items():
            if text == role_key.lower():
                return track_key, role_key, role
            for alias in role.get("aliases", []):
                if text == alias or alias.startswith(text) or text in alias:
                    return track_key, role_key, role
    return None


def stage1_pick_track() -> str:
    """Returns track_key: 'AI' or 'HW'."""
    console.print()
    opts = Text()
    for i, (k, t) in enumerate(TRACKS.items(), 1):
        opts.append(f"  [{i}] ", style="bold cyan")
        opts.append(f"{t['label']}\n")
    console.print(Panel(opts, title="[bold]Stage 1 — Which resume?[/bold]",
                        border_style="cyan", padding=(0, 1)))
    while True:
        choice = Prompt.ask("[cyan]>[/cyan]").strip()
        if choice == "1":
            return "AI"
        if choice == "2":
            return "HW"
        console.print("[yellow]Enter 1 or 2[/yellow]")


def stage2_pick_role(track_key: str) -> tuple[str, dict, list[str]]:
    """Returns (role_key, role_dict, user_keywords)."""
    track = TRACKS[track_key]
    roles = list(track["roles"].items())

    opts = Text()
    for i, (k, r) in enumerate(roles, 1):
        aliases_preview = ", ".join(r.get("aliases", [])[:3])
        opts.append(f"  [{i}] ", style="bold green")
        opts.append(f"{r['label']}")
        opts.append(f"  [dim]({aliases_preview})[/dim]\n")
    opts.append(f"  [0] ", style="bold")
    opts.append("All roles in this track\n")

    console.print()
    console.print(Panel(opts,
                        title=f"[bold]Stage 2 — {track['label']}: Pick a role[/bold]",
                        border_style="green", padding=(0, 1)))
    console.print("[dim]  Tip: type a number or a keyword like 'dv', 'rtl', 'perf', 'uarch'[/dim]\n")

    selected_role_key = None
    selected_role = None

    while True:
        choice = Prompt.ask("[green]>[/green]").strip()

        if choice == "0":
            # All roles — caller handles this
            return "__ALL__", {}, []

        if choice.isdigit():
            idx = int(choice) - 1
            if 0 <= idx < len(roles):
                selected_role_key, selected_role = roles[idx]
                break
        else:
            match = _fuzzy_match_role(choice)
            if match:
                tk, selected_role_key, selected_role = match
                if tk != track_key:
                    console.print(f"[yellow]That role belongs to the {TRACKS[tk]['label']} — switching track.[/yellow]")
                    track_key = tk
                break
            console.print(f"[yellow]No match for '{choice}'. Try a number or keyword.[/yellow]")

    console.print(f"\n  Selected: [bold green]{selected_role['label']}[/bold green]")

    kw_input = Prompt.ask(
        "\n  Extra keywords? [dim](e.g. 'cpu gpu arm', or Enter to skip)[/dim]",
        default="",
    ).strip()
    user_keywords = [k.strip() for k in kw_input.split() if k.strip()]

    return selected_role_key, selected_role, user_keywords


def stage3_pick_companies(track_key: str) -> list[str]:
    """Returns a list of company names to include in targeted queries."""
    co = COMPANIES.get(track_key, {})
    tier1 = co.get("tier1", [])
    tier2 = co.get("tier2", [])
    crossover = co.get("crossover", [])

    opts = Text()
    opts.append("  [1] ", style="bold"); opts.append(f"Tier 1 only  ({', '.join(tier1[:4])} ...)\n")
    opts.append("  [2] ", style="bold"); opts.append(f"Tier 1 + Startups  (adds {', '.join(tier2[:3])} ...)\n")
    if crossover:
        opts.append("  [3] ", style="bold"); opts.append(f"AI×HW crossover  ({', '.join(crossover)})\n")
        opts.append("  [4] ", style="bold"); opts.append("All tiers\n")
        opts.append("  [5] ", style="bold"); opts.append("Custom (type names)\n")
        opts.append("  [0] ", style="bold"); opts.append("No company filter (broad search only)\n")
    else:
        opts.append("  [3] ", style="bold"); opts.append("All tiers\n")
        opts.append("  [4] ", style="bold"); opts.append("Custom (type names)\n")
        opts.append("  [0] ", style="bold"); opts.append("No company filter\n")

    console.print()
    console.print(Panel(opts, title="[bold]Stage 3 — Company targeting[/bold]",
                        border_style="yellow", padding=(0, 1)))

    while True:
        choice = Prompt.ask("[yellow]>[/yellow]").strip()

        if choice == "0":
            return []
        if choice == "1":
            return tier1
        if choice == "2":
            return tier1 + tier2
        if crossover:
            if choice == "3":
                return crossover
            if choice == "4":
                return tier1 + tier2 + crossover
            if choice == "5":
                names = Prompt.ask("  Type company names (comma-separated)").strip()
                return [n.strip() for n in names.split(",") if n.strip()]
        else:
            if choice == "3":
                return tier1 + tier2
            if choice == "4":
                names = Prompt.ask("  Type company names (comma-separated)").strip()
                return [n.strip() for n in names.split(",") if n.strip()]

        console.print("[yellow]Invalid choice.[/yellow]")


def stage4_query_preview(
    role: dict,
    user_keywords: list[str],
    companies: list[str],
    track_key: str,
) -> list[str]:
    """Show query preview. Returns the confirmed query list (user can regenerate)."""
    while True:
        result = build_queries(role, user_keywords, companies)
        generic, targeted = result["generic"], result["targeted"]

        active_sources = ["Adzuna", "JSearch", "Google Jobs"]
        if track_key == "AI":
            active_sources.append("Remotive")

        console.print()
        display_query_preview(
            role["label"],
            generic,
            targeted,
            active_sources,
            role.get("must_have_any", []),
        )

        choice = Prompt.ask(
            "\n  Proceed? [dim][Y=yes / n=cancel / r=regenerate queries][/dim]",
            default="Y",
        ).strip().lower()

        if choice in ("y", ""):
            return all_queries(generic, targeted)
        if choice == "n":
            console.print("[yellow]Cancelled.[/yellow]")
            raise SystemExit(0)
        if choice == "r":
            continue  # regenerate with different random picks


# ---------------------------------------------------------------------------
# Core run loop
# ---------------------------------------------------------------------------

def run_check(
    con: sqlite3.Connection,
    client: OpenAI,
    model: str,
    track_key: str,
    role_key: str,
    role: dict,
    queries: list[str],
    tier1_companies: list[str],
):
    console.rule(f"[bold cyan]Searching — {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    career_cos = career_page_sources_for_track(track_key)
    console.print(
        f"  [bold]{role['label']}[/bold]  |  {len(queries)} queries  |  "
        f"{len(tier1_companies)} target companies  |  "
        f"[dim]{len(career_cos)} career pages ({', '.join(career_cos[:4])}…)[/dim]\n"
    )

    jobs = fetch_jobs_for_queries(track_key, queries, role_key, role)
    console.print(f"  Fetched [bold]{len(jobs)}[/bold] unique postings")

    new_jobs = [j for j in jobs if not job_exists(con, _job_id(j["source"], j["source_id"]))]
    console.print(f"  [bold]{len(new_jobs)}[/bold] are new (not seen before)")

    pre_passed = [j for j in new_jobs if passes_prefilter(j, role)]
    pre_dropped = len(new_jobs) - len(pre_passed)
    console.print(f"  [bold]{len(pre_passed)}[/bold] pass keyword pre-filter  "
                  f"[dim]({pre_dropped} dropped before LLM)[/dim]\n")

    matched = 0
    for job in pre_passed:
        jid = _job_id(job["source"], job["source_id"])
        score, reason = score_job(client, model, job, role, tier1_companies)
        record = {
            "id": jid,
            "role_track": track_key,
            "role_key": role_key,
            "title": job["title"],
            "company": job["company"],
            "location": job["location"],
            "url": job["url"],
            "score": score,
            "reason": reason,
            "source": job["source"],
            "found_at": datetime.now().isoformat(),
        }
        save_job(con, record)

        if score >= MIN_SCORE:
            matched += 1
            notify_job(job, score, reason, role["label"])
            mark_notified(con, jid)
            time.sleep(0.4)

    # Save pre-filtered-out jobs with score=0 so we don't re-fetch them
    for job in new_jobs:
        if not passes_prefilter(job, role):
            jid = _job_id(job["source"], job["source_id"])
            save_job(con, {
                "id": jid, "role_track": track_key, "role_key": role_key,
                "title": job["title"], "company": job["company"],
                "location": job["location"], "url": job["url"],
                "score": 0, "reason": "pre-filter: no must_have keyword",
                "source": job["source"], "found_at": datetime.now().isoformat(),
            })

    console.print(
        f"\n  [bold]Done.[/bold]  {len(new_jobs)} new  |  {len(pre_passed)} scored  |  "
        f"[green]{matched}[/green] matched ≥{MIN_SCORE}/10\n"
    )


def browse_and_apply(con: sqlite3.Connection):
    """
    Show all new matched jobs as a numbered list.
    Type numbers to open in browser, then mark which ones you applied to.
    """
    rows = con.execute(
        "SELECT id, score, title, company, location, url, role_track, role_key, reason "
        "FROM jobs WHERE status='new' AND score >= ? ORDER BY score DESC",
        (MIN_SCORE,),
    ).fetchall()

    if not rows:
        console.print("[yellow]No new jobs. Run the tracker first.[/yellow]")
        return

    # Print numbered list
    console.print()
    console.rule("[bold cyan]New Job Matches[/bold cyan]")
    console.print()

    for i, (jid, score, title, company, location, url, track, rkey, reason) in enumerate(rows, 1):
        sc = "green" if score >= 8 else "yellow"
        loc = location.split(",")[0].strip() if location else "Remote"
        console.print(
            f"  [bold cyan]{i:>2}.[/bold cyan] [{sc}]{score}/10[/{sc}]  "
            f"[bold]{title}[/bold]  [dim]@ {company} · {loc} · {track}/{rkey}[/dim]"
        )
        if reason:
            console.print(f"      [dim italic]{reason}[/dim italic]")
        console.print(f"      [dim]{url[:90]}[/dim]\n")

    console.print(f"[dim]── {len(rows)} jobs total ──[/dim]\n")

    # Step 1: open in browser
    open_input = Prompt.ask(
        "Open in browser — type numbers separated by spaces (e.g. [bold]1 3 5[/bold]) or [bold]all[/bold] or Enter to skip"
    ).strip().lower()

    to_open: list[int] = []
    if open_input == "all":
        to_open = list(range(1, len(rows) + 1))
    elif open_input:
        to_open = [int(x) for x in open_input.split() if x.isdigit() and 1 <= int(x) <= len(rows)]

    for n in to_open:
        url = rows[n - 1][5]
        subprocess.run(["open", url], capture_output=True)
        console.print(f"  [dim]Opened #{n}: {url[:70]}[/dim]")

    if to_open:
        console.print(f"\n[dim]Opened {len(to_open)} jobs. Go apply, then come back here.[/dim]")
        Prompt.ask("\nPress Enter when you're ready to mark statuses", default="")

    # Step 2: mark applied
    applied_input = Prompt.ask(
        "Mark as [bold green]applied[/bold green] — type numbers (e.g. [bold]1 3[/bold]) or Enter to skip"
    ).strip()
    _bulk_update(con, rows, applied_input, "applied", "green")

    # Step 3: mark skipped
    skip_input = Prompt.ask(
        "Mark as [bold yellow]skipped[/bold yellow] — type numbers or Enter to skip"
    ).strip()
    _bulk_update(con, rows, skip_input, "skipped", "yellow")

    # Step 4: mark reviewed (save for later)
    review_input = Prompt.ask(
        "Mark as [bold blue]reviewed[/bold blue] (save for later) — type numbers or Enter to skip"
    ).strip()
    _bulk_update(con, rows, review_input, "reviewed", "blue")

    # Remaining unmarked stay as 'new'
    console.print()
    console.print("[dim]Done. Unmarked jobs stay as 'new'. Run --digest to see your full pipeline.[/dim]\n")


def _bulk_update(con, rows, input_str, status, color):
    if not input_str:
        return
    nums = [int(x) for x in input_str.split() if x.isdigit() and 1 <= int(x) <= len(rows)]
    for n in nums:
        jid = rows[n - 1][0]
        title = rows[n - 1][2]
        company = rows[n - 1][3]
        update_status(con, jid, status)
        console.print(f"  [{color}]→ {status}[/{color}]  {title} @ {company}")


def interactive_review(con: sqlite3.Connection):
    """
    Go through every 'new' job one by one, sorted by score desc.
    Keys:
      o — open URL in browser
      a — mark applied
      r — mark reviewed (save for later)
      s — skip (mark skipped)
      x — reject
      q — quit and save progress
    """
    rows = con.execute(
        "SELECT id, role_track, role_key, score, title, company, location, url, reason, source "
        "FROM jobs WHERE status='new' AND score >= ? ORDER BY score DESC",
        (MIN_SCORE,),
    ).fetchall()

    if not rows:
        console.print("[yellow]No new jobs to review. Run the tracker first or check --digest.[/yellow]")
        return

    total = len(rows)
    console.print(f"\n[bold]Review mode[/bold] — {total} new jobs, sorted by score\n")
    console.print(
        "  [bold cyan]o[/bold cyan] open in browser  "
        "[bold green]a[/bold green] applied  "
        "[bold blue]r[/bold blue] reviewed/save  "
        "[bold yellow]s[/bold yellow] skip  "
        "[bold red]x[/bold red] reject  "
        "[bold]q[/bold] quit\n"
    )

    for idx, (jid, track, rkey, score, title, company, location, url, reason, source) in enumerate(rows, 1):
        sc_color = "green" if score >= 8 else "yellow"

        # Job card
        console.rule(f"[dim]{idx}/{total}[/dim]")
        console.print(f"\n  [{sc_color}][bold]{score}/10[/bold][/{sc_color}]  "
                      f"[bold white]{title}[/bold white]")
        console.print(f"  [bold]{company}[/bold]  ·  {location or 'Location not listed'}  "
                      f"·  [dim]{track}/{rkey}[/dim]  ·  [dim]{source}[/dim]")
        if reason:
            console.print(f"  [italic dim]{reason}[/italic dim]")
        console.print(f"  [dim][link={url}]{url}[/link][/dim]\n")

        # Action prompt — loop until valid input
        opened = False
        while True:
            raw = Prompt.ask(
                "  Action",
                choices=["o", "a", "r", "s", "x", "q"],
                default="r",
                show_choices=True,
            ).strip().lower()

            if raw == "o":
                subprocess.run(["open", url], capture_output=True)
                if not opened:
                    console.print("  [dim]Opened in browser — enter your action after reviewing[/dim]")
                    opened = True
                continue  # stay on same job so they can act after viewing

            if raw == "q":
                remaining = total - idx
                console.print(f"\n[dim]Saved progress. {remaining} jobs remaining.[/dim]")
                return

            status_map = {"a": "applied", "r": "reviewed", "s": "skipped", "x": "rejected"}
            new_status = status_map[raw]
            update_status(con, jid, new_status)

            label_color = {"applied": "green", "reviewed": "blue",
                           "skipped": "yellow", "rejected": "red"}[new_status]
            console.print(f"  [{label_color}]→ {new_status}[/{label_color}]\n")
            break

    console.print(f"\n[bold green]All {total} jobs reviewed.[/bold green]")
    console.print("Run [bold].venv/bin/python tracker.py --digest[/bold] to see your full pipeline.\n")


def print_digest(con: sqlite3.Connection):
    """Kanban-style digest grouped by lifecycle status."""
    # Status display order and colors
    STATUS_STYLE = {
        "new":          ("bold white",  "New Matches"),
        "reviewed":     ("cyan",        "Reviewed"),
        "applied":      ("bold green",  "Applied"),
        "interviewing": ("bold yellow", "Interviewing"),
        "offer":        ("bold magenta","Offers"),
        "rejected":     ("red",         "Rejected"),
        "skipped":      ("dim",         "Skipped"),
    }

    any_found = False
    for status, (color, label) in STATUS_STYLE.items():
        rows = con.execute(
            "SELECT role_track, role_key, score, title, company, location, url, reason, id "
            "FROM jobs WHERE status=? AND score >= ? ORDER BY score DESC",
            (status, MIN_SCORE if status == "new" else 0),
        ).fetchall()
        if not rows:
            continue
        any_found = True

        table = Table(
            title=f"[{color}]{label}[/{color}]  ({len(rows)})",
            show_lines=True,
            title_justify="left",
        )
        table.add_column("Score", justify="center", width=6)
        table.add_column("Title", style="bold", width=32, no_wrap=False)
        table.add_column("Company", width=18)
        table.add_column("Role", style="cyan", width=8)
        table.add_column("Why / Note", width=36, no_wrap=False)
        table.add_column("Link", style="dim", no_wrap=True)

        for track, rkey, score, title, company, location, url, reason, jid in rows:
            sc = "green" if score >= 8 else ("yellow" if score >= 6 else "dim")
            short_reason = (reason or "")[:120]
            short_url = url[:55] + "…" if len(url) > 55 else url
            table.add_row(
                f"[{sc}]{score}[/{sc}]",
                f"[link={url}]{title}[/link]",
                company,
                f"{track}/{rkey}",
                short_reason,
                short_url,
            )
        console.print(table)
        console.print()

    if not any_found:
        console.print(f"[yellow]No tracked jobs yet. Run the tracker first.[/yellow]")

    console.print(
        f"[dim]Update status: python tracker.py --update <url-fragment> <status>[/dim]\n"
        f"[dim]Statuses: {' · '.join(LIFECYCLE_STATUSES)}[/dim]\n"
        f"[dim]DB: {DB_PATH}[/dim]"
    )


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def _resolve_role_from_flag(role_alias: str) -> Optional[tuple[str, str, dict]]:
    from query_builder import build_queries as _bq
    alias = role_alias.lower().strip()
    for tk, track in TRACKS.items():
        for rk, role in track["roles"].items():
            if alias == rk.lower() or alias in role.get("aliases", []):
                return tk, rk, role
    return None


def main():
    parser = argparse.ArgumentParser(description="AI Job Tracker")
    parser.add_argument("--role", help="Skip menu, use this role alias (e.g. dv, rtl, ai)")
    parser.add_argument("--keywords", help="Extra search keywords (e.g. 'gpu arm')")
    parser.add_argument("--companies", help="Comma-separated company names to target")
    parser.add_argument("--all", action="store_true", dest="all_roles",
                        help="Run all roles without interactive menu")
    parser.add_argument("--loop", action="store_true",
                        help="Run on a schedule (CHECK_INTERVAL_HOURS)")
    parser.add_argument("--digest", action="store_true",
                        help="Print kanban lifecycle view and exit")
    parser.add_argument("--review", action="store_true",
                        help="Review new jobs one by one, open in browser, mark status")
    parser.add_argument("--browse", action="store_true",
                        help="See all new jobs as a list, open multiple in browser, bulk-mark applied")
    parser.add_argument("--update", nargs=2, metavar=("URL_FRAGMENT", "STATUS"),
                        help=f"Update job status. Statuses: {', '.join(LIFECYCLE_STATUSES)}")
    args = parser.parse_args()

    con = init_db()

    try:
        client, model = build_ai_client()
        provider = os.getenv("AI_PROVIDER", "groq")
        console.print(f"[dim]AI: {provider} / {model}[/dim]")
    except ValueError as e:
        console.print(f"[red]{e}[/red]")
        raise SystemExit(1)

    if args.digest:
        print_digest(con)
        return

    if args.browse:
        browse_and_apply(con)
        return

    if args.review:
        interactive_review(con)
        return

    if args.update:
        fragment, new_status = args.update
        new_status = new_status.lower()
        if new_status not in LIFECYCLE_STATUSES:
            console.print(f"[red]Unknown status '{new_status}'. Valid: {', '.join(LIFECYCLE_STATUSES)}[/red]")
            raise SystemExit(1)
        matches = find_jobs_by_url_fragment(con, fragment)
        if not matches:
            console.print(f"[yellow]No job found with URL containing '{fragment}'[/yellow]")
            raise SystemExit(1)
        for jid, title, company, old_status in matches:
            update_status(con, jid, new_status)
            console.print(f"[green]Updated[/green]  {title} @ {company}  "
                          f"[dim]{old_status}[/dim] → [bold]{new_status}[/bold]")
        return

    # --- Non-interactive path (--role / --all flags) ---
    if args.role or args.all_roles:
        user_keywords = args.keywords.split() if args.keywords else []
        company_list = [c.strip() for c in args.companies.split(",")] if args.companies else []

        def get_role_configs():
            if args.all_roles:
                for tk, track in TRACKS.items():
                    for rk, role in track["roles"].items():
                        yield tk, rk, role, COMPANIES.get(tk, {}).get("tier1", [])
            else:
                match = _resolve_role_from_flag(args.role)
                if not match:
                    console.print(f"[red]Unknown role '{args.role}'. "
                                  f"Try: {', '.join(r for t in TRACKS.values() for r in t['roles'])}[/red]")
                    raise SystemExit(1)
                tk, rk, role = match
                tier1 = company_list or COMPANIES.get(tk, {}).get("tier1", [])
                yield tk, rk, role, tier1

        def do_run():
            for tk, rk, role, tier1 in get_role_configs():
                queries_d = build_queries(role, user_keywords, tier1)
                queries = all_queries(queries_d["generic"], queries_d["targeted"])
                run_check(con, client, model, tk, rk, role, queries, tier1)

        if args.loop:
            console.print(f"[cyan]Loop mode: every {CHECK_INTERVAL_HOURS}h. Ctrl+C to stop.[/cyan]")
            do_run()
            schedule.every(CHECK_INTERVAL_HOURS).hours.do(do_run)
            while True:
                schedule.run_pending()
                time.sleep(60)
        else:
            do_run()
        return

    # --- Interactive 4-stage path ---
    console.print(Panel(
        "[bold]Job Tracker[/bold] — AI-powered search for Praveen's two tracks",
        border_style="bold blue",
    ))

    track_key = stage1_pick_track()
    role_key, role, user_keywords = stage2_pick_role(track_key)

    if role_key == "__ALL__":
        # User picked "All roles" in stage 2
        companies = stage3_pick_companies(track_key)
        tier1 = COMPANIES.get(track_key, {}).get("tier1", [])
        for rk, role in TRACKS[track_key]["roles"].items():
            queries_d = build_queries(role, user_keywords, companies)
            queries = all_queries(queries_d["generic"], queries_d["targeted"])
            run_check(con, client, model, track_key, rk, role, queries, tier1)
        return

    companies = stage3_pick_companies(track_key)
    tier1_co = COMPANIES.get(track_key, {}).get("tier1", [])
    queries = stage4_query_preview(role, user_keywords, companies, track_key)

    if args.loop:
        console.print(f"\n[cyan]Loop mode: every {CHECK_INTERVAL_HOURS}h. Ctrl+C to stop.[/cyan]")
        run_check(con, client, model, track_key, role_key, role, queries, tier1_co)
        schedule.every(CHECK_INTERVAL_HOURS).hours.do(
            run_check, con=con, client=client, model=model,
            track_key=track_key, role_key=role_key, role=role,
            queries=queries, tier1_companies=tier1_co,
        )
        while True:
            schedule.run_pending()
            time.sleep(60)
    else:
        run_check(con, client, model, track_key, role_key, role, queries, tier1_co)


if __name__ == "__main__":
    main()
