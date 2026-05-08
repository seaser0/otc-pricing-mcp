#!/usr/bin/env python3
"""Build the SQLite FTS5 index of OTC documentation from the upstream RST repos.

Reads `opentelekomcloud-docs/<service>` repos via the GitHub Contents API,
parses the Sphinx RST sources under `umn/source/` and `api-ref/source/`,
splits each page at h2/h3 boundaries, and writes one row per section into
`data/otc_docs.sqlite3` (FTS5 virtual table) plus `data/otc_docs.manifest.json`.

The MCP server (`tools/docs.py`) only reads from the SQLite file at runtime —
this script never runs in production. It is invoked weekly by
`.github/workflows/sync-docs.yml` and on demand by maintainers.

Design notes:
- The HTML site at docs.otc.t-systems.com is gated by Anubis AND blocks all
  crawlers via robots.txt. We deliberately use the GitHub upstream instead;
  it's the same content, Apache-2.0, with no rate limits.
- Pages are normalised to a canonical URL on the public-OTC docs host so the
  search results point a human reader at something they can open in a
  browser. Swiss-OTC availability is a separate flag (cloud column).
- Index is committed to the repo (~5-15 MB for the current allow-list) so
  the MCP works out of the box with `uv sync` — no first-run network call.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import re
import sqlite3
import sys
import urllib.error
import urllib.request
from collections.abc import Iterator
from contextlib import closing
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from docutils.core import publish_parts
from docutils.utils import SystemMessage
from markdownify import markdownify

logger = logging.getLogger("sync_otc_docs")

# Initial service allow-list. Each entry is the GitHub repo name under
# the opentelekomcloud-docs org. Add or remove freely; the next sync run
# picks up the change.
DEFAULT_SERVICES: tuple[str, ...] = (
    "elastic-cloud-server",
    "elastic-volume-service",
    "object-storage-service",
    "virtual-private-cloud",
    "cloud-backup-and-recovery",
    "cloud-eye",
    "cloud-trace-service",
    "elastic-ip",
    "nat-gateway",
    "elastic-load-balancer",
    "key-management-service",
    "anti-ddos",
    "image-management-service",
    "auto-scaling",
    "identity-and-access-management",
)

# Files to skip — table-of-contents pages and changelogs add noise without
# search value (the body is mostly toctree directives or version bumps).
SKIP_FILE_NAMES: frozenset[str] = frozenset({"index.rst", "change_history.rst"})

GITHUB_API = "https://api.github.com"
RAW_BASE = "https://raw.githubusercontent.com"
PUBLIC_DOCS_BASE = "https://docs.otc.t-systems.com"

SCHEMA_VERSION = 1


@dataclass
class Section:
    """One searchable chunk of documentation."""

    service: str
    cloud: str  # 'public-otc' | 'swiss-otc' | 'both'
    url: str
    anchor: str  # slug of the heading, used as URL fragment
    title: str  # page H1
    h2: str
    h3: str
    body: str
    upstream_commit: str
    rst_path: str  # for debugging — repo-relative path to the source file


@dataclass
class ManifestEntry:
    """One row in data/otc_docs.manifest.json."""

    service: str
    upstream_commit: str
    branch: str
    rst_files_seen: int
    sections_indexed: int
    last_synced: str  # ISO 8601


@dataclass
class SyncResult:
    """End-of-run summary."""

    services: list[ManifestEntry] = field(default_factory=list)
    sections_total: int = 0
    skipped_services: list[tuple[str, str]] = field(default_factory=list)


# --------------------------------------------------------------------------
# GitHub access (no auth required for public repos; honours GITHUB_TOKEN env
# if set so CI doesn't burn the unauthenticated rate limit).
# --------------------------------------------------------------------------


def _gh_request(url: str) -> Any:
    req = urllib.request.Request(url, headers={"Accept": "application/vnd.github+json"})
    token = os.environ.get("GITHUB_TOKEN")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    with urllib.request.urlopen(req, timeout=30) as resp:  # noqa: S310 - hardcoded github.com
        return json.loads(resp.read().decode("utf-8"))


def _resolve_default_branch_and_sha(service: str) -> tuple[str, str]:
    """Look up the default branch + its HEAD commit SHA for one service repo."""
    repo_meta = _gh_request(f"{GITHUB_API}/repos/opentelekomcloud-docs/{service}")
    branch = repo_meta["default_branch"]
    branch_meta = _gh_request(
        f"{GITHUB_API}/repos/opentelekomcloud-docs/{service}/branches/{branch}"
    )
    sha = branch_meta["commit"]["sha"]
    return branch, sha


def _list_rst_paths(service: str, sha: str, sub_path: str) -> list[str]:
    """Recursively list `.rst` files under <repo>/<sub_path> at commit <sha>.

    Uses the git tree API which returns the whole tree in one call for
    repos this size — far cheaper than recursive Contents API walks.
    """
    tree = _gh_request(
        f"{GITHUB_API}/repos/opentelekomcloud-docs/{service}/git/trees/{sha}?recursive=1"
    )
    if tree.get("truncated"):
        logger.warning("git tree for %s truncated; some files may be missed", service)
    paths: list[str] = []
    for entry in tree.get("tree", []):
        path = entry.get("path", "")
        if (
            entry.get("type") == "blob"
            and path.startswith(sub_path + "/")
            and path.endswith(".rst")
            and Path(path).name not in SKIP_FILE_NAMES
        ):
            paths.append(path)
    return sorted(paths)


def _fetch_rst(service: str, sha: str, path: str) -> str:
    raw_url = f"{RAW_BASE}/opentelekomcloud-docs/{service}/{sha}/{path}"
    with urllib.request.urlopen(raw_url, timeout=30) as resp:  # noqa: S310 - raw.githubusercontent.com
        return resp.read().decode("utf-8")


# --------------------------------------------------------------------------
# RST → Markdown → sections
# --------------------------------------------------------------------------

# `:ref:` and similar Sphinx roles are not understood by stock docutils.
# Strip them to plain text BEFORE handing the source to docutils so we don't
# get spammed with WARN noise and broken cross-references in the output.
_REF_ROLE = re.compile(r":(?:ref|doc|term|abbr|samp|file|guilabel|menuselection):`([^<`]+?)(?:<[^>]+>)?`")
# Sphinx custom directives (toctree, figure with options, etc.) docutils chokes
# on — replace the entire directive block with empty content.
_TOCTREE_BLOCK = re.compile(r"^\.\.\s+toctree::.*?(?=^\S|\Z)", re.DOTALL | re.MULTILINE)
# Page-level metadata Sphinx adds (e.g. `:original_name: ...`) at the top.
_FIELD_LIST_TOP = re.compile(r"\A(?::[\w-]+:[^\n]*\n)+", re.MULTILINE)


def _preprocess_rst(rst: str) -> str:
    """Strip Sphinx-isms that confuse stock docutils."""
    rst = _REF_ROLE.sub(lambda m: m.group(1).strip(), rst)
    rst = _TOCTREE_BLOCK.sub("", rst)
    rst = _FIELD_LIST_TOP.sub("", rst, count=1)
    return rst


def _rst_to_html(rst: str) -> str:
    """RST → HTML body fragment. Errors are downgraded to warnings."""
    try:
        parts = publish_parts(
            source=rst,
            writer_name="html5",
            settings_overrides={
                "report_level": 5,  # suppress all docutils warnings on stderr
                "halt_level": 5,
                "embed_stylesheet": False,
                "input_encoding": "unicode",
                "output_encoding": "unicode",
            },
        )
        return str(parts.get("html_body") or parts.get("fragment") or "")
    except SystemMessage as exc:
        logger.debug("docutils SystemMessage: %s", exc)
        return ""


_HEADING_TAG_RE = re.compile(r"<(h[1-6])[^>]*>", re.IGNORECASE)


def _split_html_at_headings(html: str) -> list[tuple[str, str, str, str]]:
    """Split HTML body at h2/h3 boundaries.

    Returns: list of (title_h1, h2, h3, html_chunk). h1 is the whole-page
    title (constant per page). h2/h3 are empty strings for the chunk that
    sits before the first h2.
    """
    # Pull the page title (first <h1>...).
    m = re.search(r"<h1[^>]*>(.*?)</h1>", html, re.IGNORECASE | re.DOTALL)
    h1_text = _strip_tags(m.group(1)) if m else ""

    # Tokenise on heading tags.
    pos = 0
    chunks: list[tuple[str, str, str, str]] = []
    cur_h2 = ""
    cur_h3 = ""
    cur_buf: list[str] = []

    def _flush() -> None:
        if cur_buf:
            chunks.append((h1_text, cur_h2, cur_h3, "".join(cur_buf)))

    for tag_match in _HEADING_TAG_RE.finditer(html):
        # text since previous heading boundary
        cur_buf.append(html[pos : tag_match.start()])
        # close any heading text up to its end tag
        end_tag = f"</{tag_match.group(1)}>"
        end_idx = html.find(end_tag, tag_match.end())
        if end_idx == -1:
            break
        heading_text = _strip_tags(html[tag_match.end() : end_idx])

        level = tag_match.group(1).lower()
        if level == "h2":
            _flush()
            cur_buf = []
            cur_h2, cur_h3 = heading_text, ""
        elif level == "h3":
            _flush()
            cur_buf = []
            cur_h3 = heading_text
        # h1 boundary is page-level; skip emitting an empty chunk before it.
        pos = end_idx + len(end_tag)

    cur_buf.append(html[pos:])
    _flush()
    return chunks


_TAG_RE = re.compile(r"<[^>]+>")


def _strip_tags(s: str) -> str:
    return _TAG_RE.sub("", s).strip()


def _slugify(s: str, max_len: int = 64) -> str:
    """URL-safe slug for a section anchor."""
    s = re.sub(r"[^\w\s-]", "", s.lower()).strip()
    s = re.sub(r"[\s_-]+", "-", s)
    return s[:max_len]


# --------------------------------------------------------------------------
# Path → canonical URL
# --------------------------------------------------------------------------


def _rst_path_to_url(service: str, rst_path: str) -> str:
    """Map e.g. umn/source/service_overview/what_is_ecs.rst to the docs URL.

    Pattern: <PUBLIC_DOCS_BASE>/<service>/<umn|api-ref>/<rest>.html
    """
    parts = rst_path.split("/")
    # parts[0] = 'umn' or 'api-ref'; parts[1] = 'source'; rest is the path.
    if len(parts) < 3 or parts[1] != "source":
        # Defensive — unexpected layout. Fall back to a github URL.
        return f"https://github.com/opentelekomcloud-docs/{service}/blob/HEAD/{rst_path}"
    section = parts[0]
    rest = "/".join(parts[2:])
    if rest.endswith(".rst"):
        rest = rest[:-4] + ".html"
    return f"{PUBLIC_DOCS_BASE}/{service}/{section}/{rest}"


# --------------------------------------------------------------------------
# Sync driver
# --------------------------------------------------------------------------


def _process_rst_file(
    service: str, cloud: str, sha: str, rst_path: str, rst_text: str
) -> Iterator[Section]:
    html = _rst_to_html(_preprocess_rst(rst_text))
    if not html.strip():
        return
    url = _rst_path_to_url(service, rst_path)
    for h1, h2, h3, html_chunk in _split_html_at_headings(html):
        body = markdownify(html_chunk, heading_style="ATX", strip=["script", "style"]).strip()
        if not body:
            continue
        anchor_seed = h3 or h2 or h1 or rst_path
        full_url = url + ("#" + _slugify(anchor_seed) if (h2 or h3) else "")
        yield Section(
            service=service,
            cloud=cloud,
            url=full_url,
            anchor=_slugify(anchor_seed),
            title=h1,
            h2=h2,
            h3=h3,
            body=body,
            upstream_commit=sha,
            rst_path=rst_path,
        )


def _sync_service(
    service: str, cloud: str = "both"
) -> tuple[ManifestEntry, Iterator[Section]]:
    """Yield sections lazily so the driver can stream them straight to disk.

    Holding all sections in memory crashed a 2 GB host on the full
    allow-list; streaming bounds the working set to one RST file at a time.
    """
    branch, sha = _resolve_default_branch_and_sha(service)

    # Discover the RST file list eagerly (cheap) but defer body parsing so
    # the caller can interleave INSERTs with parsing work.
    rst_paths_per_subtree: list[tuple[str, list[str]]] = []
    for sub_path in ("umn/source", "api-ref/source"):
        try:
            rst_paths = _list_rst_paths(service, sha, sub_path)
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                # Some services have no api-ref tree — that's normal.
                logger.debug("%s: no %s tree", service, sub_path)
                continue
            raise
        rst_paths_per_subtree.append((sub_path, rst_paths))

    rst_files_total = sum(len(paths) for _, paths in rst_paths_per_subtree)
    sections_indexed = 0

    def _generate() -> Iterator[Section]:
        nonlocal sections_indexed
        for _sub_path, paths in rst_paths_per_subtree:
            for rst_path in paths:
                rst_text = _fetch_rst(service, sha, rst_path)
                for section in _process_rst_file(service, cloud, sha, rst_path, rst_text):
                    sections_indexed += 1
                    yield section

    from datetime import datetime, timezone

    # `entry` is filled in fully only after the generator is exhausted; the
    # caller MUST iterate the generator before reading entry.sections_indexed.
    entry = ManifestEntry(
        service=service,
        upstream_commit=sha,
        branch=branch,
        rst_files_seen=rst_files_total,
        sections_indexed=0,  # populated below
        last_synced=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    )

    def _wrap() -> Iterator[Section]:
        for s in _generate():
            yield s
        entry.sections_indexed = sections_indexed

    return entry, _wrap()


# --------------------------------------------------------------------------
# SQLite FTS5 writer
# --------------------------------------------------------------------------


def _open_index_for_write(db_path: Path) -> tuple[sqlite3.Connection, Path]:
    """Initialise an empty FTS5 index at <db_path>.tmp; caller streams into it."""
    tmp = db_path.with_suffix(db_path.suffix + ".tmp")
    if tmp.exists():
        tmp.unlink()
    con = sqlite3.connect(tmp)
    con.executescript(
        f"""
        PRAGMA journal_mode = WAL;

        CREATE TABLE meta (
            key   TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );
        INSERT INTO meta (key, value) VALUES ('schema_version', '{SCHEMA_VERSION}');

        -- One row per (page section). Heading levels live in their own
        -- columns so bm25() can weight matches in titles higher than
        -- matches in body text.
        CREATE VIRTUAL TABLE docs USING fts5(
            service       UNINDEXED,
            cloud         UNINDEXED,
            url           UNINDEXED,
            anchor        UNINDEXED,
            upstream_commit UNINDEXED,
            title,
            h2,
            h3,
            body,
            tokenize = "porter unicode61 remove_diacritics 2"
        );
        """
    )
    con.commit()
    return con, tmp


def _stream_into_index(con: sqlite3.Connection, sections: Iterator[Section]) -> int:
    """Stream sections directly into an open FTS5 index, batched.

    Avoids the multi-hundred-MB working set the previous batch-everything
    approach needed: docutils + markdownify + a 6 k-row Python list together
    OOM-killed the sync on 2 GB hosts. With 200-row batches the resident
    set stays well under 200 MB even for the full allow-list.
    """
    sql = (
        "INSERT INTO docs (service, cloud, url, anchor, upstream_commit, "
        "title, h2, h3, body) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)"
    )
    inserted = 0
    batch: list[tuple[Any, ...]] = []
    cursor = con.cursor()
    for s in sections:
        batch.append(
            (s.service, s.cloud, s.url, s.anchor, s.upstream_commit, s.title, s.h2, s.h3, s.body)
        )
        if len(batch) >= 200:
            cursor.executemany(sql, batch)
            inserted += len(batch)
            batch.clear()
            con.commit()
    if batch:
        cursor.executemany(sql, batch)
        inserted += len(batch)
        con.commit()
    return inserted


def _finalise_index(con: sqlite3.Connection, tmp: Path, db_path: Path, total_sections: int) -> None:
    """Optimise, vacuum, drop WAL/SHM, atomically swap into place."""
    con.execute(
        "INSERT INTO meta (key, value) VALUES ('section_count', ?)",
        (str(total_sections),),
    )
    con.commit()
    # ANALYZE-equivalent for FTS5 — improves bm25() scoring stats.
    con.execute("INSERT INTO docs(docs) VALUES('optimize')")
    con.commit()
    con.close()
    # VACUUM + journal_mode change must run outside any transaction.
    with closing(sqlite3.connect(tmp)) as con2:
        con2.isolation_level = None  # autocommit
        # Switch back to rollback journal so the final file has no WAL/SHM
        # side cars when committed. Truncate any pending WAL frames first.
        con2.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        con2.execute("PRAGMA journal_mode = DELETE")
        con2.execute("VACUUM")
    # Remove the temporary WAL/SHM siblings; rename leaves them otherwise.
    for sibling_suffix in ("-wal", "-shm"):
        sibling = Path(str(tmp) + sibling_suffix)
        if sibling.exists():
            sibling.unlink()
    tmp.replace(db_path)


def _write_manifest(manifest_path: Path, result: SyncResult) -> None:
    payload = {
        "schema_version": SCHEMA_VERSION,
        "section_count": result.sections_total,
        "services": [
            {
                "service": e.service,
                "upstream_commit": e.upstream_commit,
                "branch": e.branch,
                "rst_files_seen": e.rst_files_seen,
                "sections_indexed": e.sections_indexed,
                "last_synced": e.last_synced,
            }
            for e in sorted(result.services, key=lambda x: x.service)
        ],
        "skipped": [{"service": s, "reason": r} for s, r in result.skipped_services],
    }
    manifest_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Build the OTC docs FTS5 index from opentelekomcloud-docs upstream"
    )
    parser.add_argument(
        "--services",
        nargs="*",
        default=list(DEFAULT_SERVICES),
        help="Override the default service allow-list",
    )
    parser.add_argument(
        "--db",
        type=Path,
        default=Path("data/otc_docs.sqlite3"),
        help="Output SQLite path (default: data/otc_docs.sqlite3)",
    )
    parser.add_argument(
        "--manifest",
        type=Path,
        default=Path("data/otc_docs.manifest.json"),
        help="Output manifest JSON path",
    )
    parser.add_argument(
        "-v", "--verbose", action="count", default=0, help="-v=INFO, -vv=DEBUG"
    )
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=[logging.WARNING, logging.INFO, logging.DEBUG][min(args.verbose, 2)],
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    args.db.parent.mkdir(parents=True, exist_ok=True)
    args.manifest.parent.mkdir(parents=True, exist_ok=True)

    result = SyncResult()
    con, tmp_db = _open_index_for_write(args.db)
    try:
        for service in args.services:
            try:
                logger.info("syncing %s", service)
                entry, svc_sections = _sync_service(service)
                inserted = _stream_into_index(con, svc_sections)
                result.sections_total += inserted
                result.services.append(entry)
                logger.info(
                    "%s: %d rst files, %d sections, sha=%s",
                    service,
                    entry.rst_files_seen,
                    entry.sections_indexed,
                    entry.upstream_commit[:8],
                )
            except urllib.error.HTTPError as exc:
                logger.error("%s: HTTP %s — skipping", service, exc.code)
                result.skipped_services.append((service, f"HTTP {exc.code}"))
            except Exception as exc:  # noqa: BLE001 - top-level driver, log & continue
                logger.error("%s: %s — skipping", service, exc)
                result.skipped_services.append((service, str(exc)))

        if result.sections_total == 0:
            logger.error("no sections produced; refusing to overwrite %s", args.db)
            con.close()
            for sibling in (tmp_db, *(Path(str(tmp_db) + s) for s in ("-wal", "-shm"))):
                if sibling.exists():
                    sibling.unlink()
            return 1

        _finalise_index(con, tmp_db, args.db, result.sections_total)
    except BaseException:
        con.close()
        raise
    _write_manifest(args.manifest, result)

    digest = hashlib.sha256(args.db.read_bytes()).hexdigest()[:16]
    logger.info(
        "wrote %s (%d sections, sha256:%s) and %s",
        args.db,
        result.sections_total,
        digest,
        args.manifest,
    )
    if result.skipped_services:
        logger.warning("skipped %d services: %s", len(result.skipped_services), result.skipped_services)
    return 0


if __name__ == "__main__":
    sys.exit(main())
