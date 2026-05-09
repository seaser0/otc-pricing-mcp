"""Documentation search tools: search_otc_docs, get_otc_doc_section.

Read-only SQLite FTS5 lookups against an index built offline by
`scripts/sync_otc_docs.py` from the upstream `opentelekomcloud-docs/<service>`
repos. The index ships with the package; the runtime never touches the
docs.otc.t-systems.com HTML site (Anubis-gated + robots-disallowed).

Boundary validation is strict: empty/whitespace inputs, out-of-range
`top_k`, unknown services, and URLs that don't look like absolute OTC docs
URLs all raise ValueError so the MCP layer can surface ``isError=true``.
This is the pattern issues #4 / #6 / #31 / #33 / #35 / #41-#45 caught for
the pricing tools — silent-zero / silent-clamp / silent-empty are bugs,
not features.
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

_TOP_K_MAX = 50

# Cache the indexed-service list so service-filter validation doesn't pay
# the SQLite round-trip on every call. Built lazily on the first call that
# needs it; reset via _reset_service_cache() in tests.
_SERVICE_CACHE: frozenset[str] | None = None


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

    bundled = Path(__file__).resolve().parent.parent / "data" / "otc_docs.sqlite3"
    if bundled.exists():
        return bundled

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


def _reset_service_cache() -> None:
    """Test hook: drop the cached service list so a new fixture is picked up."""
    global _SERVICE_CACHE
    _SERVICE_CACHE = None


def _indexed_services() -> frozenset[str]:
    global _SERVICE_CACHE
    if _SERVICE_CACHE is None:
        with closing(_open_db()) as con:
            rows = con.execute("SELECT DISTINCT service FROM docs").fetchall()
        _SERVICE_CACHE = frozenset(r[0] for r in rows if r[0])
    return _SERVICE_CACHE


def _escape_match(query: str) -> str:
    """Quote each FTS5 token so user input can't break out of the MATCH grammar.

    FTS5 has its own mini-query syntax (operators AND/OR/NOT, prefix stars,
    NEAR(), column filters with `:`, parens). For an LLM-or-user-facing tool
    we want simple bag-of-words behaviour, so we wrap each whitespace-split
    token in double quotes (FTS5 phrase quoting). Embedded `"` are doubled
    per the FTS5 grammar.
    """
    tokens = query.split()
    if not tokens:
        return '""'
    quoted: list[str] = []
    for tok in tokens:
        safe = tok.replace('"', '""')
        quoted.append(f'"{safe}"')
    return " ".join(quoted)


def _escape_like(pattern: str) -> str:
    """Escape SQL LIKE wildcards so user input doesn't expand the pattern.

    Pair with ``ESCAPE '\\'`` in the SQL. Without this, a URL containing
    ``%`` matches every row and ``_`` matches arbitrary single characters
    (issue #40).
    """
    return pattern.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def search_otc_docs(
    query: str,
    scope: Literal["public", "swiss", "both"] = "both",
    service: str | None = None,
    top_k: int = 5,
) -> dict[str, Any]:
    """Full-text search across the indexed Open Telekom Cloud documentation.

    Args:
        query: Free-form search terms (BM25-ranked, AND-of-tokens semantics).
               Must contain at least one non-whitespace character.
        scope: "public" = Public OTC (eu-de/eu-nl), "swiss" = Swiss OTC
               (eu-ch2), "both" = no filter. Defaults to "both" since most
               umn pages apply to both clouds.
        service: Optional service repo name (e.g. "elastic-cloud-server")
                 to constrain results. Must match a service actually indexed.
                 None = all services.
        top_k: Number of hits to return. Must be in [1, 50]; values > 50
               are accepted but clamped to 50 with a note in the response.

    Returns:
        ``{'hits': [...], 'query': str, 'total_hits': int,
        'index_section_count': int, 'notes': list[str]}``

    Raises:
        ValueError: query is empty/whitespace, scope is invalid, top_k is
            <= 0, or service is not in the indexed set.
        FileNotFoundError: the SQLite index has not been built yet.
    """
    if not isinstance(query, str) or not query.strip():
        raise ValueError("query must be a non-empty string")
    if scope not in ("public", "swiss", "both"):
        raise ValueError(f"scope must be one of 'public', 'swiss', 'both' (got {scope!r})")

    try:
        top_k_int = int(top_k)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"top_k must be an integer (got {top_k!r})") from exc
    if top_k_int <= 0:
        raise ValueError(f"top_k must be >= 1 (got {top_k_int})")

    notes: list[str] = []
    if top_k_int > _TOP_K_MAX:
        notes.append(f"top_k={top_k_int} capped to {_TOP_K_MAX}")
        top_k_int = _TOP_K_MAX

    if service is not None:
        if not isinstance(service, str) or not service.strip():
            raise ValueError("service must be None or a non-empty string")
        valid = _indexed_services()
        if service not in valid:
            sample = ", ".join(sorted(valid)[:8])
            raise ValueError(
                f"unknown service {service!r}. "
                f"{len(valid)} services are indexed; first few: {sample}, ..."
            )

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
    params.append(top_k_int)

    with closing(_open_db()) as con:
        try:
            rows = con.execute(sql, params).fetchall()
        except sqlite3.OperationalError as exc:
            # Catches the rare case where _escape_match output is still
            # rejected by FTS5 (e.g. a token consisting entirely of
            # punctuation that the tokenizer drops). Surface as zero hits
            # rather than a 500 — query was syntactically valid at our
            # boundary, just unsearchable post-tokenization.
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
        "notes": notes,
    }


def get_otc_doc_section(
    url: str,
    section: str | None = None,
) -> dict[str, Any]:
    """Fetch one (or one section of one) indexed documentation page.

    Args:
        url: Canonical absolute https://docs.otc.t-systems.com/... URL as
             returned by ``search_otc_docs``. Optionally with ``#anchor``.
             Empty / wildcard / relative URLs are rejected.
        section: Optional H2/H3 heading title to restrict the response to a
                 single section. Case-insensitive substring match against
                 the indexed h2/h3 columns. Empty string is rejected; pass
                 None for "no section filter".

    Returns:
        ``{'url', 'title', 'service', 'cloud', 'upstream_commit', 'sections',
        'matched', 'page_found', 'available_sections'}``. ``page_found`` is
        true whenever any row exists for the page; ``matched`` is true only
        when the section filter (if any) actually selected something.
        ``available_sections`` lists the page's H2 headings when the page
        was found but the filter excluded everything — so the caller can
        retry with a known-good section name.

    Raises:
        ValueError: url is empty/whitespace, doesn't start with ``https://``,
                    or section is the empty string.
        FileNotFoundError: the SQLite index has not been built yet.
    """
    if not isinstance(url, str) or not url.strip():
        raise ValueError("url must be a non-empty string")
    if not url.startswith("https://"):
        raise ValueError(
            f"url must be an absolute https://docs.otc.t-systems.com/... URL (got {url!r})"
        )
    if section is not None:
        if not isinstance(section, str) or not section.strip():
            raise ValueError("section must be None or a non-empty non-whitespace string")

    # Section anchor handling. The indexed `url` column always stores the
    # full canonical URL including the anchor (e.g. `<page>#<anchor>`), so:
    #   - URL with `#anchor`    → exact match on that one section.
    #   - URL without `#anchor` → match every row whose URL is `<page>#*`.
    # LIKE-pattern characters in user input (% _) are escaped so a typo or
    # malicious wildcard can't fan out into other pages (issue #40).
    if "#" in url:
        sql_where = "url = ?"
        params: list[Any] = [url]
        page_url, _frag = url.split("#", 1)
    else:
        page_url = url
        like_pattern = _escape_like(url) + "#%"
        sql_where = "(url = ? OR url LIKE ? ESCAPE '\\')"
        params = [url, like_pattern]

    if section:
        sql_where = f"({sql_where}) AND (LOWER(h2) LIKE ? OR LOWER(h3) LIKE ?)"
        like = f"%{section.lower()}%"
        params.extend([like, like])

    sql = f"""
        SELECT url, title, service, cloud, upstream_commit, h2, h3, anchor, body
        FROM docs
        WHERE {sql_where}
        ORDER BY rowid
    """  # nosec B608

    with closing(_open_db()) as con:
        rows = con.execute(sql, params).fetchall()
        if rows:
            page_found = True
        else:
            # No rows under the combined filter. Disambiguate: does the page
            # itself exist (so the caller should retry with a different
            # section / no section), or is the URL unknown to the index?
            if "#" in url:
                # Specific anchor URL didn't match. Ask the page-level query
                # to find out whether the page exists at all.
                page_like = _escape_like(page_url) + "#%"
                page_rows = con.execute(
                    "SELECT 1 FROM docs WHERE url = ? OR url LIKE ? ESCAPE '\\' LIMIT 1",
                    [page_url, page_like],
                ).fetchall()
                page_found = bool(page_rows)
            elif section:
                # Page-without-anchor + section filter excluded everything.
                # Re-check whether the page exists without the section filter.
                page_like = _escape_like(page_url) + "#%"
                page_rows = con.execute(
                    "SELECT 1 FROM docs WHERE url = ? OR url LIKE ? ESCAPE '\\' LIMIT 1",
                    [page_url, page_like],
                ).fetchall()
                page_found = bool(page_rows)
            else:
                page_found = False

        available_sections: list[str] = []
        if page_found and not rows:
            page_like = _escape_like(page_url) + "#%"
            avail = con.execute(
                """
                SELECT DISTINCT h2 FROM docs
                WHERE (url = ? OR url LIKE ? ESCAPE '\\') AND h2 != ''
                ORDER BY rowid
                """,
                [page_url, page_like],
            ).fetchall()
            available_sections = [r[0] for r in avail]

    if not rows:
        first_meta: dict[str, str] = {
            "title": "",
            "service": "",
            "cloud": "",
            "upstream_commit": "",
        }
        if page_found:
            with closing(_open_db()) as con:
                page_like = _escape_like(page_url) + "#%"
                meta_row = con.execute(
                    """
                    SELECT title, service, cloud, upstream_commit FROM docs
                    WHERE url = ? OR url LIKE ? ESCAPE '\\'
                    ORDER BY rowid
                    LIMIT 1
                    """,
                    [page_url, page_like],
                ).fetchone()
            if meta_row is not None:
                first_meta = {
                    "title": meta_row["title"],
                    "service": meta_row["service"],
                    "cloud": meta_row["cloud"],
                    "upstream_commit": meta_row["upstream_commit"],
                }
        return {
            "url": page_url,
            "title": first_meta["title"],
            "service": first_meta["service"],
            "cloud": first_meta["cloud"],
            "upstream_commit": first_meta["upstream_commit"],
            "sections": [],
            "matched": False,
            "page_found": page_found,
            "available_sections": available_sections,
        }

    # Sanity: every selected row must belong to the same page. The escaped-
    # LIKE + anchor-boundary filter above guarantees this for valid input;
    # the assertion makes the invariant explicit so a future schema change
    # doesn't silently re-introduce cross-page mixing (issue #40).
    distinct_urls = {r["url"].split("#", 1)[0] for r in rows}
    if len(distinct_urls) > 1:
        raise RuntimeError(
            f"internal error: section query matched multiple pages "
            f"({len(distinct_urls)} distinct URLs). Refusing to mix metadata."
        )

    first = rows[0]
    return {
        "url": page_url,
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
        "page_found": True,
        "available_sections": [],
    }
