# HireRadar — AI Job Tracker for Hardware & AI Engineers

An intelligent, terminal-based job search pipeline built for engineers targeting **RTL / DV / SoC / Microarchitecture** and **AI Infrastructure / ML Platform** roles.

HireRadar fetches jobs across multiple sources, scores each one against your resume using an LLM, filters for experience level, sends macOS desktop notifications for strong matches, and lets you track every application through a kanban lifecycle — all from the command line.

---

## How it works

```
Stage 1 — Pick resume track       AI or Hardware
Stage 2 — Pick role + keywords    DV, RTL, UARCH, PERF, SOC, AI_INFRA, ML_PLATFORM
Stage 3 — Company targeting       Tier 1, startups, crossover, or custom
Stage 4 — Query preview           Confirm or regenerate before running
     ↓
Fetch jobs from 4 sources + 19 direct company career pages
     ↓
Keyword pre-filter  →  drop irrelevant / overqualified titles before LLM
     ↓
LLM scores each job 0–10 against your resume (experience-aware)
     ↓
macOS notification for every match ≥ 6/10 with clickable job link
     ↓
SQLite DB stores all jobs with lifecycle status
```

---

## Features

- **Dynamic query builder** — combines role keyword groups + your typed keywords + company names to generate targeted boolean search strings (no hardcoded queries)
- **Direct career page scraping** — hits Greenhouse and Lever public APIs for 19 companies (Tenstorrent, Groq, Cerebras, Rivos, Anthropic, Modal, Hugging Face, etc.) — no API key needed
- **Experience-aware scoring** — LLM is told you have 2–3 years; Principal/Staff/Director titles are dropped before scoring
- **Company tier system** — Tier 1 (NVIDIA, AMD, Qualcomm, Apple, Intel…), Tier 2 startups, AI×HW crossover — company-targeted queries fire separately
- **Tier 1 score bonus** — jobs at top-tier companies get +1 to score so borderline matches surface
- **Job lifecycle tracking** — mark jobs as `reviewed`, `applied`, `interviewing`, `offer`, `rejected`
- **Kanban digest** — `--digest` shows all tracked jobs grouped by status
- **Provider-agnostic LLM** — Groq (free), Gemini (free), Ollama (local), Anthropic, or OpenAI — swap with one `.env` line

---

## Job sources

| Source | Key needed | What it covers |
|---|---|---|
| [Remotive](https://remotive.com) | None | Remote tech jobs (AI track) |
| [Adzuna](https://developer.adzuna.com) | Free (200 calls/day) | US jobs — Indeed, Monster, Reed + more |
| [JSearch / RapidAPI](https://rapidapi.com/letscrape-6bRBa3QguO5/api/jsearch) | Free tier | LinkedIn, Indeed, Glassdoor |
| [Google Jobs / SerpAPI](https://serpapi.com) | Free (100/month) | All job boards + company pages |
| Greenhouse API | None | Tenstorrent, Groq, Cerebras, Etched, SiFive, Anthropic, Scale AI, Cohere, Together AI, Baseten, Untether AI, Ventana |
| Lever API | None | Rivos, Ampere, d-Matrix, Replicate, Modal, Hugging Face, W&B |

---

## Target roles

**Hardware track** (uses RTL resume):

| Role | Aliases | Key search terms |
|---|---|---|
| RTL Design | `rtl`, `digital design` | RTL Design Engineer, ASIC RTL, Digital Design Engineer |
| Design Verification | `dv`, `verification`, `uvm` | DV Engineer, Hardware Verification, UVM, cocotb |
| Performance Modeling | `perf`, `cpu modeling` | CPU/GPU Performance Engineer, cycle-accurate simulation |
| Microarchitecture | `uarch`, `microarchitecture` | CPU Architect, Processor Design, pipeline |
| SoC / ASIC | `soc`, `asic` | SoC Design, ASIC Engineer, IP integration |

**AI track** (uses AI resume):

| Role | Aliases |
|---|---|
| AI Infrastructure | `ai`, `ai infra`, `llm`, `eval` |
| ML Platform / MLOps | `mlops`, `ml platform` |

---

## Setup

```bash
git clone https://github.com/praveensaravanan30/hire-radar.git
cd hire-radar/tracker
bash setup.sh
```

Edit `tracker/.env` and add your keys:

```env
# Required — pick one (Groq is free and fast)
AI_PROVIDER=groq
GROQ_API_KEY=gsk_...

# Optional job sources (add any for broader results)
ADZUNA_APP_ID=
ADZUNA_APP_KEY=
RAPIDAPI_JSEARCH_KEY=
SERPAPI_KEY=
```

Get a free Groq key at [console.groq.com](https://console.groq.com) — takes 60 seconds, no credit card.

---

## Usage

```bash
cd tracker

# Interactive 4-stage flow (recommended)
.venv/bin/python tracker.py

# Skip menu — run specific role directly
.venv/bin/python tracker.py --role dv
.venv/bin/python tracker.py --role rtl --keywords "gpu arm"
.venv/bin/python tracker.py --role ai_infra --keywords "llm eval"

# Run all roles at once (good for cron)
.venv/bin/python tracker.py --all

# Run on a schedule (every 3 hours)
.venv/bin/python tracker.py --loop --role dv

# Show kanban lifecycle view
.venv/bin/python tracker.py --digest

# Update a job's status
.venv/bin/python tracker.py --update "tenstorrent/jobs/4659518007" reviewed
.venv/bin/python tracker.py --update "5777429351" applied
.venv/bin/python tracker.py --update "nvidia" interviewing
```

**Lifecycle statuses:** `new` → `reviewed` → `applied` → `interviewing` → `offer` / `rejected` / `skipped`

---

## Automate with cron

Run every 3 hours in the background, log to file:

```bash
crontab -e

# Add:
0 */3 * * * cd /path/to/hire-radar/tracker && .venv/bin/python tracker.py --role dv >> logs/tracker.log 2>&1
```

---

## Project structure

```
tracker/
├── tracker.py        Main script — pipeline, fetch, score, notify, CLI
├── config.py         Role profiles, keyword groups, company tiers
├── query_builder.py  Dynamic search string generator
├── career_pages.py   Greenhouse + Lever direct scrapers (19 companies)
├── requirements.txt
├── setup.sh          One-time setup script
├── .env.example      API key template
└── logs/             Log output from scheduled runs
```

---

## AI providers

| Provider | Cost | Setup |
|---|---|---|
| **Groq** (default) | Free — 14,400 req/day | [console.groq.com](https://console.groq.com) |
| Google Gemini | Free — 1,500 req/day | [aistudio.google.com](https://aistudio.google.com/app/apikey) |
| Ollama | Free, local | [ollama.com](https://ollama.com) |
| Anthropic | Paid | [console.anthropic.com](https://console.anthropic.com) |
| OpenAI | Paid | [platform.openai.com](https://platform.openai.com) |

Switch providers by changing `AI_PROVIDER` in `.env` — no code changes needed.

---

## Adding more companies

In `career_pages.py`, append to `COMPANY_BOARDS`:

```python
{"name": "YourCompany", "ats": "greenhouse", "slug": "yourcompany-slug", "track": "HW"},
{"name": "AnotherCo",   "ats": "lever",      "slug": "anotherco",        "track": "AI"},
```

Find the slug from the company's job board URL:
- Greenhouse: `job-boards.greenhouse.io/{slug}/jobs`
- Lever: `jobs.lever.co/{slug}`
