"""Unit tests for the docs search tools (#5).

Builds a tiny in-tempdir SQLite FTS5 index that mirrors the production
schema, then exercises search_otc_docs / get_otc_doc_section against it
via the OTC_DOCS_DB env override. Keeps the tests offline and decoupled
from the actually-committed index.
"""

from __future__ import annotations

import sqlite3
from contextlib import closing
from pathlib import Path

import pytest

from otc_pricing_mcp.tools.docs import (
    _DB_PATH_ENV,
    get_otc_doc_section,
    search_otc_docs,
)


def _build_fixture_index(db_path: Path) -> None:
    """Construct a 4-row FTS5 index with the same schema as the real one."""
    with closing(sqlite3.connect(db_path)) as con:
        con.executescript(
            """
            CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
            INSERT INTO meta (key, value) VALUES ('schema_version', '1'),
                                                  ('section_count', '4');
            CREATE VIRTUAL TABLE docs USING fts5(
                service       UNINDEXED,
                cloud         UNINDEXED,
                url           UNINDEXED,
                anchor        UNINDEXED,
                upstream_commit UNINDEXED,
                title, h2, h3, body,
                tokenize = "porter unicode61 remove_diacritics 2"
            );
            """
        )
        rows = [
            (
                "elastic-cloud-server",
                "both",
                "https://docs.otc.t-systems.com/elastic-cloud-server/umn/service_overview/ecs_types.html",
                "",
                "abc123",
                "ECS Types",
                "",
                "",
                "Elastic Cloud Server provides several flavor families for general purpose, compute, memory, and GPU workloads.",
            ),
            (
                "elastic-cloud-server",
                "both",
                "https://docs.otc.t-systems.com/elastic-cloud-server/umn/service_overview/ecs_types.html#general-purpose",
                "general-purpose",
                "abc123",
                "ECS Types",
                "General-Purpose",
                "",
                "S3 instances offer balanced vCPU and memory for typical web workloads. Available in eu-de, eu-nl, and Swiss OTC.",
            ),
            (
                "elastic-cloud-server",
                "both",
                "https://docs.otc.t-systems.com/elastic-cloud-server/umn/service_overview/ecs_types.html#large-memory",
                "large-memory",
                "abc123",
                "ECS Types",
                "Large-Memory",
                "",
                "E6 large-memory instances are tuned for in-memory databases and SAP HANA workloads.",
            ),
            (
                "elastic-volume-service",
                "swiss-otc",
                "https://docs.otc.t-systems.com/elastic-volume-service/umn/service_overview/disk_types.html",
                "",
                "def456",
                "EVS Disk Types",
                "",
                "",
                "Ultra-High I/O (SSD) disks deliver up to 50,000 IOPS for latency-sensitive workloads on Swiss OTC.",
            ),
        ]
        con.executemany(
            "INSERT INTO docs (service, cloud, url, anchor, upstream_commit, title, h2, h3, body) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            rows,
        )
        con.execute("INSERT INTO docs(docs) VALUES('optimize')")
        con.commit()


@pytest.fixture
def docs_index(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    db = tmp_path / "fixture.sqlite3"
    _build_fixture_index(db)
    monkeypatch.setenv(_DB_PATH_ENV, str(db))
    return db


class TestSearchOtcDocs:
    def test_returns_dict_with_expected_shape(self, docs_index: Path) -> None:
        r = search_otc_docs("flavor families")
        assert isinstance(r, dict)
        assert {"hits", "query", "total_hits", "index_section_count"} <= r.keys()
        assert r["index_section_count"] == 4

    def test_finds_relevant_hit(self, docs_index: Path) -> None:
        r = search_otc_docs("memory database SAP HANA")
        assert r["total_hits"] >= 1
        # Top hit must be the Large-Memory section.
        assert "Large-Memory" in r["hits"][0]["h2"]

    def test_top_k_clamped(self, docs_index: Path) -> None:
        r = search_otc_docs("ECS", top_k=999)  # silently clamped
        assert len(r["hits"]) <= 50

    def test_top_k_minimum(self, docs_index: Path) -> None:
        r = search_otc_docs("ECS", top_k=0)  # clamped to 1
        assert len(r["hits"]) == 1

    def test_invalid_scope_raises(self, docs_index: Path) -> None:
        with pytest.raises(ValueError, match="scope"):
            search_otc_docs("anything", scope="moon")  # type: ignore[arg-type]

    def test_scope_swiss_excludes_public_only(self, docs_index: Path) -> None:
        # The fixture has one swiss-otc row (EVS) and three 'both' rows; with
        # scope='swiss' all should still appear (both clouds), but a
        # public-otc-only row would be filtered. Add one and verify.
        with closing(sqlite3.connect(docs_index)) as con:
            con.execute(
                "INSERT INTO docs (service, cloud, url, anchor, upstream_commit, title, h2, h3, body) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    "anti-ddos",
                    "public-otc",
                    "https://docs.otc.t-systems.com/anti-ddos/umn/overview.html",
                    "",
                    "ghi789",
                    "Anti-DDoS",
                    "",
                    "",
                    "Anti-DDoS is only available on Public OTC.",
                ),
            )
            con.commit()
        r_swiss = search_otc_docs("Anti-DDoS only available", scope="swiss")
        assert all("anti-ddos" not in h["service"] for h in r_swiss["hits"])
        r_public = search_otc_docs("Anti-DDoS only available", scope="public")
        assert any("anti-ddos" in h["service"] for h in r_public["hits"])

    def test_service_filter(self, docs_index: Path) -> None:
        r = search_otc_docs("disks IOPS", service="elastic-volume-service")
        assert r["total_hits"] >= 1
        for hit in r["hits"]:
            assert hit["service"] == "elastic-volume-service"

    def test_snippet_highlights_matches(self, docs_index: Path) -> None:
        r = search_otc_docs("SAP HANA")
        assert r["total_hits"] >= 1
        # snippet() in FTS5 wraps matches in the (open, close) markers we passed.
        assert "<b>" in r["hits"][0]["snippet"]
        assert "</b>" in r["hits"][0]["snippet"]

    def test_special_chars_in_query_dont_blow_up(self, docs_index: Path) -> None:
        # FTS5 has its own grammar (AND/OR/NOT/parens/'NEAR'); user input must
        # be quoted so 'memory (large)' doesn't trip the parser.
        r = search_otc_docs("memory (large)")
        assert isinstance(r, dict)
        assert "hits" in r

    def test_quotes_in_query_dont_blow_up(self, docs_index: Path) -> None:
        r = search_otc_docs('foo "bar" baz')
        assert isinstance(r, dict)

    def test_index_missing_raises_filenotfound(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv(_DB_PATH_ENV, str(tmp_path / "does-not-exist.sqlite3"))
        with pytest.raises(FileNotFoundError, match="OTC docs index"):
            search_otc_docs("anything")


class TestGetOtcDocSection:
    def test_returns_full_page_by_url(self, docs_index: Path) -> None:
        r = get_otc_doc_section(
            "https://docs.otc.t-systems.com/elastic-cloud-server/umn/service_overview/ecs_types.html"
        )
        assert r["matched"] is True
        assert r["title"] == "ECS Types"
        # All three ECS sections (page-level + General-Purpose + Large-Memory).
        assert len(r["sections"]) == 3
        h2s = {s["h2"] for s in r["sections"]}
        assert {"", "General-Purpose", "Large-Memory"} <= h2s

    def test_section_filter_by_substring(self, docs_index: Path) -> None:
        r = get_otc_doc_section(
            "https://docs.otc.t-systems.com/elastic-cloud-server/umn/service_overview/ecs_types.html",
            section="memory",
        )
        assert r["matched"] is True
        assert len(r["sections"]) == 1
        assert r["sections"][0]["h2"] == "Large-Memory"

    def test_anchor_in_url_honoured(self, docs_index: Path) -> None:
        # Passing the full URL with #anchor restricts to that one section.
        r = get_otc_doc_section(
            "https://docs.otc.t-systems.com/elastic-cloud-server/umn/service_overview/ecs_types.html#general-purpose"
        )
        assert r["matched"] is True
        assert len(r["sections"]) == 1
        assert r["sections"][0]["anchor"] == "general-purpose"

    def test_unknown_url_returns_matched_false(self, docs_index: Path) -> None:
        r = get_otc_doc_section("https://docs.otc.t-systems.com/nonexistent/page.html")
        assert r["matched"] is False
        assert r["sections"] == []

    def test_index_missing_raises(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv(_DB_PATH_ENV, str(tmp_path / "nope.sqlite3"))
        with pytest.raises(FileNotFoundError):
            get_otc_doc_section("https://example.com/")
