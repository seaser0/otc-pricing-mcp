"""Unit tests for the docs search tools (#5).

Builds a tiny in-tempdir SQLite FTS5 index that mirrors the production
schema, then exercises search_otc_docs / get_otc_doc_section against it
via the OTC_DOCS_DB env override. Keeps the tests offline and decoupled
from the actually-committed index.

Boundary-validation coverage targets the QA bugs filed in the
2026-05-09 round (issues #40-#45) — the silent-zero / silent-clamp /
silent-empty / LIKE-injection family.
"""

from __future__ import annotations

import sqlite3
from contextlib import closing
from pathlib import Path

import pytest

from otc_pricing_mcp.tools.docs import (
    _DB_PATH_ENV,
    _reset_service_cache,
    get_otc_doc_section,
    search_otc_docs,
)


def _build_fixture_index(db_path: Path) -> None:
    """Construct a 5-row FTS5 index with the same schema as the real one."""
    with closing(sqlite3.connect(db_path)) as con:
        con.executescript(
            """
            CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
            INSERT INTO meta (key, value) VALUES ('schema_version', '1'),
                                                  ('section_count', '5');
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
            # A second page for the same service so we can exercise the
            # "page-prefix must not leak across pages" guarantee.
            (
                "elastic-cloud-server",
                "both",
                "https://docs.otc.t-systems.com/elastic-cloud-server/umn/quickstart/login.html#step-1",
                "step-1",
                "abc123",
                "Logging In",
                "Step 1",
                "",
                "Open the management console and choose Compute > Elastic Cloud Server.",
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
    _reset_service_cache()
    return db


class TestSearchOtcDocs:
    def test_returns_dict_with_expected_shape(self, docs_index: Path) -> None:
        r = search_otc_docs("flavor families")
        assert isinstance(r, dict)
        assert {"hits", "query", "total_hits", "index_section_count", "notes"} <= r.keys()
        assert r["index_section_count"] == 5
        assert r["notes"] == []

    def test_finds_relevant_hit(self, docs_index: Path) -> None:
        r = search_otc_docs("memory database SAP HANA")
        assert r["total_hits"] >= 1
        assert "Large-Memory" in r["hits"][0]["h2"]

    # --- #41: empty / whitespace query is invalid input ---

    def test_empty_query_raises(self, docs_index: Path) -> None:
        with pytest.raises(ValueError, match="non-empty"):
            search_otc_docs("")

    def test_whitespace_query_raises(self, docs_index: Path) -> None:
        with pytest.raises(ValueError, match="non-empty"):
            search_otc_docs("   \t\n")

    # --- #42: top_k bounds are enforced; over-cap clamps with a note ---

    def test_top_k_zero_raises(self, docs_index: Path) -> None:
        with pytest.raises(ValueError, match="top_k must be >= 1"):
            search_otc_docs("ECS", top_k=0)

    def test_top_k_negative_raises(self, docs_index: Path) -> None:
        with pytest.raises(ValueError, match="top_k must be >= 1"):
            search_otc_docs("ECS", top_k=-5)

    def test_top_k_over_cap_clamped_with_note(self, docs_index: Path) -> None:
        r = search_otc_docs("ECS", top_k=999)
        assert len(r["hits"]) <= 50
        assert any("999" in n and "50" in n for n in r["notes"])

    def test_top_k_at_cap_no_note(self, docs_index: Path) -> None:
        r = search_otc_docs("ECS", top_k=50)
        assert r["notes"] == []

    # --- #43: unknown service is rejected ---

    def test_unknown_service_raises(self, docs_index: Path) -> None:
        with pytest.raises(ValueError, match="unknown service"):
            search_otc_docs("ECS", service="not-a-real-service")

    def test_empty_service_raises(self, docs_index: Path) -> None:
        with pytest.raises(ValueError, match="non-empty"):
            search_otc_docs("ECS", service="")

    def test_known_service_filter(self, docs_index: Path) -> None:
        r = search_otc_docs("disks IOPS", service="elastic-volume-service")
        assert r["total_hits"] >= 1
        for hit in r["hits"]:
            assert hit["service"] == "elastic-volume-service"

    # --- pre-existing coverage ---

    def test_invalid_scope_raises(self, docs_index: Path) -> None:
        with pytest.raises(ValueError, match="scope"):
            search_otc_docs("anything", scope="moon")  # type: ignore[arg-type]

    def test_scope_swiss_excludes_public_only(self, docs_index: Path) -> None:
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
        _reset_service_cache()
        r_swiss = search_otc_docs("Anti-DDoS only available", scope="swiss")
        assert all("anti-ddos" not in h["service"] for h in r_swiss["hits"])
        r_public = search_otc_docs("Anti-DDoS only available", scope="public")
        assert any("anti-ddos" in h["service"] for h in r_public["hits"])

    def test_snippet_highlights_matches(self, docs_index: Path) -> None:
        r = search_otc_docs("SAP HANA")
        assert r["total_hits"] >= 1
        assert "<b>" in r["hits"][0]["snippet"]
        assert "</b>" in r["hits"][0]["snippet"]

    def test_special_chars_in_query_dont_blow_up(self, docs_index: Path) -> None:
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
        _reset_service_cache()
        with pytest.raises(FileNotFoundError, match="OTC docs index"):
            search_otc_docs("anything")


class TestGetOtcDocSection:
    _ECS_PAGE = (
        "https://docs.otc.t-systems.com/elastic-cloud-server/umn/service_overview/ecs_types.html"
    )

    def test_returns_full_page_by_url(self, docs_index: Path) -> None:
        r = get_otc_doc_section(self._ECS_PAGE)
        assert r["matched"] is True
        assert r["page_found"] is True
        assert r["title"] == "ECS Types"
        # Service is single-page-scoped; no leak of "Logging In" sections.
        assert len(r["sections"]) == 3
        h2s = {s["h2"] for s in r["sections"]}
        assert {"", "General-Purpose", "Large-Memory"} <= h2s

    def test_section_filter_by_substring(self, docs_index: Path) -> None:
        r = get_otc_doc_section(self._ECS_PAGE, section="memory")
        assert r["matched"] is True
        assert len(r["sections"]) == 1
        assert r["sections"][0]["h2"] == "Large-Memory"

    def test_anchor_in_url_honoured(self, docs_index: Path) -> None:
        r = get_otc_doc_section(self._ECS_PAGE + "#general-purpose")
        assert r["matched"] is True
        assert len(r["sections"]) == 1
        assert r["sections"][0]["anchor"] == "general-purpose"

    # --- #40: LIKE-prefix injection / cross-page leakage ---

    def test_empty_url_raises(self, docs_index: Path) -> None:
        with pytest.raises(ValueError, match="non-empty"):
            get_otc_doc_section("")

    def test_whitespace_url_raises(self, docs_index: Path) -> None:
        with pytest.raises(ValueError, match="non-empty"):
            get_otc_doc_section("   ")

    def test_relative_url_raises(self, docs_index: Path) -> None:
        with pytest.raises(ValueError, match="absolute https"):
            get_otc_doc_section("/elastic-cloud-server/")

    def test_percent_wildcard_url_rejected(self, docs_index: Path) -> None:
        # Even if the user manages to pass an absolute URL containing `%`,
        # it must not expand into a SQL wildcard match.
        r = get_otc_doc_section("https://docs.otc.t-systems.com/%")
        assert r["matched"] is False
        assert r["page_found"] is False
        assert r["sections"] == []

    def test_underscore_wildcard_url_rejected(self, docs_index: Path) -> None:
        r = get_otc_doc_section("https://docs.otc.t-systems.com/_______________")
        assert r["matched"] is False
        assert r["page_found"] is False
        assert r["sections"] == []

    def test_prefix_url_does_not_match_a_subpage(self, docs_index: Path) -> None:
        # A URL that's a *prefix* of an indexed page must not match the page —
        # only the canonical page URL (or that URL + #anchor) should match.
        r = get_otc_doc_section(
            "https://docs.otc.t-systems.com/elastic-cloud-server/umn/service_overview/"
        )
        assert r["matched"] is False
        assert r["page_found"] is False

    def test_page_url_matches_only_its_own_sections(self, docs_index: Path) -> None:
        # The fixture has two distinct pages under elastic-cloud-server. The
        # ecs_types page must not return rows from quickstart/login.html.
        r = get_otc_doc_section(self._ECS_PAGE)
        for section in r["sections"]:
            assert "Logging In" not in section.get("h2", "")
        assert all(s["anchor"] != "step-1" for s in r["sections"])

    # --- #44: distinguish page-not-found from section-filter-excluded-all ---

    def test_unknown_url_page_not_found(self, docs_index: Path) -> None:
        r = get_otc_doc_section("https://docs.otc.t-systems.com/nonexistent/page.html")
        assert r["matched"] is False
        assert r["page_found"] is False
        assert r["available_sections"] == []

    def test_known_url_unknown_section_marks_page_found(self, docs_index: Path) -> None:
        r = get_otc_doc_section(self._ECS_PAGE, section="this-section-does-not-exist")
        assert r["matched"] is False
        assert r["page_found"] is True
        # Available sections list must include actual H2s of the page so the
        # caller can retry with a known-good name.
        assert "General-Purpose" in r["available_sections"]
        assert "Large-Memory" in r["available_sections"]

    def test_known_url_unknown_anchor_marks_page_found(self, docs_index: Path) -> None:
        r = get_otc_doc_section(self._ECS_PAGE + "#nonexistent-anchor")
        assert r["matched"] is False
        assert r["page_found"] is True

    # --- #45: section="" is invalid input, not "no filter" ---

    def test_empty_section_raises(self, docs_index: Path) -> None:
        with pytest.raises(ValueError, match="non-empty"):
            get_otc_doc_section(self._ECS_PAGE, section="")

    def test_whitespace_section_raises(self, docs_index: Path) -> None:
        with pytest.raises(ValueError, match="non-empty"):
            get_otc_doc_section(self._ECS_PAGE, section="   ")

    # --- pre-existing coverage ---

    def test_index_missing_raises(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv(_DB_PATH_ENV, str(tmp_path / "nope.sqlite3"))
        _reset_service_cache()
        with pytest.raises(FileNotFoundError):
            get_otc_doc_section("https://example.com/")
