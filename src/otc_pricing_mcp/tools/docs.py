"""Documentation search tools: search_otc_docs, get_otc_doc_section.

Read-only SQLite FTS5 lookups against an index built offline by
`scripts/sync_otc_docs.py` from the upstream `opentelekomcloud-docs/<service>`
repos. The index ships with the package; the runtime never touches the
docs.otc.t-systems.com HTML site (Anubis-gated + robots-disallowed).

If the index file is missing the tools surface a clear error rather than
silently returning empty results — the same anti-pattern issues #4 / #6
caught for the pricing tools.
"""

from __future__ import annotations

import os
import sqlite3
from contextlib import closing
from pathlib import Path
from typing import Any, Literal

# Column weights for FTS5 BM25 — matches in title rank ~10x as much as in
# body, headings ~5x. Tuned by spot-checking the queries listed in the
# acceptance criteria for issue #5; revisit if recall feels off.
_BM25_WEIGHTS = (10.0, 5.0, 5.0, 1.0)  # title, h2, h3, body

_DB_PATH_ENV = "OTC_DOCS_DB"


def _resolve_db_path() -> Path:
    """Find the SQLite index file.

    Priority:
      1. OTC_DOCS_DB env var
      2. Wheel-bundled `<otc_pricing_mcp>/data/otc_docs.sqlite3` (via the
         `[tool.hatch.build.targets.wheel.force-include]` mapping in
         pyproject.toml).
      3. Repo checkout: walk upwards from this module's location looking for
         a `data/otc_docs.sqlite3` (so a fresh `git clone` + tests work).
    """
    override = os.environ.get(_DB_PATH_ENV)
    if override:
        return Path(override)

    # `__file__` lives at  .../otc_pricing_mcp/tools/docs.py
    # In an installed wheel:  .../otc_pricing_mcp/data/otc_docs.sqlite3
    bundled = Path(__file__).resolve().parent.parent / "data" / "otc_docs.sqlite3"
    if bundled.exists():
        return bundled

    # Repo checkout: walk upwards looking for data/otc_docs.sqlite3.
    here = Path(__file__).resolve()
    for parent in here.parents:
        candidate = parent / "data" / "otc_docs.sqlite3"
        if candidate.exists():
            return candidate

    return Path("data/otc_docs.sqlite3")


def _open_db() -> sqlite3.Connection:
    db_path = _resolve_db_path()
    if not db_path.exists():
        raise FileNotFoundError(
            f"OTC docs index not found at {db_path}. "
            "Build it with `uv run --extra sync python scripts/sync_otc_docs.py` "
            f"or set {_DB_PATH_ENV} to an existing index file."
        )
    con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    return con


def _escape_match(query: str) -> str:
    """Quote each FTS5 token so user input can't break out of the MATCH grammar.

    FTS5 has its own mini-query syntax (operators AND/OR/NOT, prefix stars,
    NEAR(), column filters with `:`, parens). For an LLM-or-user-facing tool
    we want simple bag-of-words behaviour, so we wrap each whitespace-split
    token in double quotes (FTS5 phrase quoting). Embedded `"` are doubled
    per the FTS5 grammar.
    """
    tokens = [t for t in query.split() if t.strip()]
    if not tokens:
        return '""'
    quoted: list[str] = []
    for tok in tokens:
        # Drop FTS5 syntax characters that would cause a syntax error even
        # inside a phrase — `"` is the only one.
        safe = tok.replace('"', '""')
        quoted.append(f'"{safe}"')
    return " ".join(quoted)


def search_otc_docs(
    query: str,
    scope: Literal["public", "swiss", "both"] = "both",
    service: str | None = None,
    top_k: int = 5,
) -> dict[str, Any]:
    """Full-text search across the indexed Open Telekom Cloud documentation.

    Args:
        query: Free-form search terms (BM25-ranked, AND-of-tokens semantics).
        scope: "public" = Public OTC (eu-de/eu-nl), "swiss" = Swiss OTC
               (eu-ch2), "both" = no filter. Defaults to "both" since most
               umn pages apply to both clouds.
        service: Optional service repo name (e.g. "elastic-cloud-server")
                 to constrain results. None = all services.
        top_k: Number of hits to return (clamped to [1, 50]).

    Returns:
        {
            'hits': [
                {
                    'url': str,             # canonical docs.otc URL with anchor
                    'title': str,           # page H1
                    'h2': str,              # section H2 ('' if before first H2)
                    'h3': str,
                    'service': str,         # opentelekomcloud-docs repo name
                    'cloud': str,           # 'public-otc' / 'swiss-otc' / 'both'
                    'upstream_commit': str, # SHA of the RST source
                    'snippet': str,         # body excerpt with <b>...</b> matches
                    'rank': float,          # BM25 score (more negative = better)
                },
                ...
            ],
            'query': str,
            'total_hits': int,   # results.length (capped at top_k)
            'index_section_count': int,
        }

    Raises:
        ValueError: scope or top_k is out of range.
        FileNotFoundError: the SQLite index has not been built yet.
    """
    if scope not in ("public", "swiss", "both"):
        raise ValueError(f"scope must be one of 'public', 'swiss', 'both' (got {scope!r})")
    top_k = max(1, min(50, int(top_k)))

    match_expr = _escape_match(query)

    where = ["docs MATCH ?"]
    params: list[Any] = [match_expr]
    if scope == "public":
        where.append("cloud IN ('public-otc', 'both')")
    elif scope == "swiss":
        where.append("cloud IN ('swiss-otc', 'both')")
    if service:
        where.append("service = ?")
        params.append(service)

    # Every interpolation below is from controlled, non-user input:
    # _BM25_WEIGHTS is a module constant tuple of floats, and `where` is built
    # exclusively from literal strings above. User-supplied values reach the
    # query only via parameterised placeholders (`params` list).
    sql = f"""
        SELECT
            url, title, h2, h3, service, cloud, upstream_commit,
            snippet(docs, 8, '<b>', '</b>', '...', 24) AS snippet,
            bm25(docs, {_BM25_WEIGHTS[0]}, {_BM25_WEIGHTS[1]},
                 {_BM25_WEIGHTS[2]}, {_BM25_WEIGHTS[3]}) AS rank
        FROM docs
        WHERE {" AND ".join(where)}
        ORDER BY rank
        LIMIT ?
    """  # nosec B608
    params.append(top_k)

    with closing(_open_db()) as con:
        try:
            rows = con.execute(sql, params).fetchall()
        except sqlite3.OperationalError as exc:
            # Most likely cause: a query that is technically valid FTS5 but
            # produces nothing parseable after _escape_match. Convert to an
            # empty-hits response rather than blowing up the tool call.
            if "fts5: syntax error" in str(exc).lower():
                rows = []
            else:
                raise
        section_count = con.execute("SELECT value FROM meta WHERE key = 'section_count'").fetchone()
        total_sections = int(section_count[0]) if section_count else 0

    hits = [dict(r) for r in rows]
    return {
        "hits": hits,
        "query": query,
        "total_hits": len(hits),
        "index_section_count": total_sections,
    }


def get_otc_doc_section(
    url: str,
    section: str | None = None,
) -> dict[str, Any]:
    """Fetch one (or one section of one) indexed documentation page.

    Args:
        url: Canonical URL as returned by `search_otc_docs` (with or without
             the section anchor `#...`).
        section: Optional heading title to restrict the response to a single
                 H2 / H3 section. Case-insensitive substring match against
                 the indexed h2/h3 columns. None returns every section of
                 the page concatenated under one record.

    Returns:
        {
            'url': str,             # the requested URL (without section override)
            'title': str,           # page title
            'service': str,
            'cloud': str,
            'upstream_commit': str,
            'sections': [           # one entry per H2/H3 chunk that survived filtering
                {'h2': str, 'h3': str, 'anchor': str, 'body': str}, ...
            ],
            'matched': bool,        # False if no rows matched
        }

    Raises:
        FileNotFoundError: the SQLite index has not been built yet.
    """
    # Strip an optional `#anchor` fragment so the caller can paste either
    # form back. The indexed `url` column already includes the anchor when
    # present, but for a "whole page" request we want every section, so we
    # match on the URL prefix.
    fragment = ""
    base_url = url
    if "#" in url:
        base_url, fragment = url.split("#", 1)

    sql_parts = ["url LIKE ?"]
    params: list[Any] = [base_url + "%"]
    if section:
        sql_parts.append("(LOWER(h2) LIKE ? OR LOWER(h3) LIKE ?)")
        like = f"%{section.lower()}%"
        params.extend([like, like])
    elif fragment:
        # The caller passed a specific section anchor — honour it.
        sql_parts.append("anchor = ?")
        params.append(fragment)

    # `sql_parts` is built from literal strings above; user input only flows
    # in via the `params` list bound to placeholders.
    sql = f"""
        SELECT url, title, service, cloud, upstream_commit, h2, h3, anchor, body
        FROM docs
        WHERE {" AND ".join(sql_parts)}
        ORDER BY rowid
    """  # nosec B608

    with closing(_open_db()) as con:
        rows = con.execute(sql, params).fetchall()

    if not rows:
        return {
            "url": base_url,
            "title": "",
            "service": "",
            "cloud": "",
            "upstream_commit": "",
            "sections": [],
            "matched": False,
        }

    first = rows[0]
    return {
        "url": base_url,
        "title": first["title"],
        "service": first["service"],
        "cloud": first["cloud"],
        "upstream_commit": first["upstream_commit"],
        "sections": [
            {
                "h2": r["h2"],
                "h3": r["h3"],
                "anchor": r["anchor"],
                "body": r["body"],
            }
            for r in rows
        ],
        "matched": True,
    }
