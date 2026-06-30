"""
query_builder.py — Builds targeted job search strings from role keyword_groups,
user-typed keywords, and selected company names.

The builder generates two kinds of queries:
  1. Generic  — role title + domain/tool terms (broad net)
  2. Targeted — role title + company name (direct company search)
"""

import itertools
import random
from typing import Optional


def _pick(group: list, n: int = 1) -> list:
    """Pick up to n items from a list without repetition."""
    return random.sample(group, min(n, len(group)))


def build_queries(
    role: dict,
    user_keywords: Optional[list[str]] = None,
    companies: Optional[list[str]] = None,
    max_generic: int = 4,
    max_targeted: int = 4,
) -> dict[str, list[str]]:
    """
    Generate search query strings for a role.

    Args:
        role:          role config dict from TRACKS (has 'keyword_groups')
        user_keywords: extra terms the user typed (e.g. ['gpu', 'arm'])
        companies:     company names to build targeted queries for
        max_generic:   how many generic (broad) queries to produce
        max_targeted:  how many company-targeted queries to produce

    Returns:
        {"generic": [...], "targeted": [...]}
    """
    groups = role.get("keyword_groups", {})
    titles = groups.get("titles", [role["label"]])
    user_kw = " ".join(user_keywords) if user_keywords else ""

    # --- Generic queries ---
    generic: list[str] = []
    other_group_keys = [k for k in groups if k != "titles"]

    for title in titles:
        if len(generic) >= max_generic:
            break
        extras = []
        # Pick 1 term from up to 2 different non-title groups
        sampled_groups = random.sample(other_group_keys, min(2, len(other_group_keys)))
        for gk in sampled_groups:
            term = _pick(groups[gk], 1)
            if term:
                extras.append(term[0])
        query_parts = [title] + extras
        if user_kw:
            query_parts.append(user_kw)
        q = " ".join(query_parts)
        if q not in generic:
            generic.append(q)

    # Ensure we have enough by filling with title + user_kw combos
    for title in titles:
        if len(generic) >= max_generic:
            break
        q = f"{title} {user_kw}".strip()
        if q not in generic:
            generic.append(q)

    # --- Company-targeted queries ---
    targeted: list[str] = []
    if companies:
        best_title = titles[0]
        alt_title = titles[1] if len(titles) > 1 else titles[0]
        for i, company in enumerate(companies[:max_targeted]):
            title = best_title if i % 2 == 0 else alt_title
            parts = [title, company]
            if user_kw:
                parts.append(user_kw)
            q = " ".join(parts)
            if q not in targeted:
                targeted.append(q)

    return {"generic": generic, "targeted": targeted}


def all_queries(generic: list[str], targeted: list[str]) -> list[str]:
    """Flatten generic + targeted into a single deduplicated list."""
    seen: set[str] = set()
    result = []
    for q in generic + targeted:
        if q not in seen:
            seen.add(q)
            result.append(q)
    return result


def display_query_preview(role_label: str, generic: list[str], targeted: list[str],
                          sources: list[str], must_have_sample: list[str]) -> None:
    """Print a formatted preview panel of the queries that will run."""
    from rich.console import Console
    from rich.panel import Panel
    from rich.text import Text

    console = Console()
    lines = Text()

    if generic:
        lines.append("Generic (broad net):\n", style="bold dim")
        for i, q in enumerate(generic, 1):
            lines.append(f"  {i}. ", style="dim")
            lines.append(f'"{q}"\n', style="cyan")

    if targeted:
        lines.append("\nCompany-targeted:\n", style="bold dim")
        for i, q in enumerate(targeted, len(generic) + 1):
            lines.append(f"  {i}. ", style="dim")
            lines.append(f'"{q}"\n', style="green")

    lines.append(f"\nSources: ", style="dim")
    lines.append(", ".join(sources), style="yellow")
    lines.append(f"\nPre-filter keywords: ", style="dim")
    lines.append(", ".join(must_have_sample[:6]) + " ...", style="dim italic")

    total = len(generic) + len(targeted)
    console.print(Panel(
        lines,
        title=f"[bold]{role_label}[/bold] — {total} search queries",
        border_style="blue",
        padding=(0, 1),
    ))
