"""Tags tab: rows, filters, models and the tag pipeline reads (TG-02..TG-09)."""

from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone
from typing import Any

from gitective.database.store import MEMORY, Store
from gitective.database.sync import ForgeData
from gitective.forge.errors import NetworkError
from gitective.forge.models import Job, PipelineRef, Tag
from gitective.repository.tags import build_rows, first_line, visible_tags
from gitective.settings.config_file import TrackedProject
from gitective.shared.dates import day_range, parse_date
from gitective.shared.people import PersonDirectory

NOW = datetime(2026, 10, 16, 10, 0, tzinfo=timezone.utc)
BILLING = TrackedProject(id=10, path="acme/billing-api", web_url="https://gitlab.test/acme/billing-api")
PORTAL = TrackedProject(id=11, path="acme/portal-web")


def tag_json(name: str, message: str = "", release: dict[str, Any] | None = None, target: str | None = None,
             sha: str = "4f1a9c2e" + "0" * 32, days: int = 1) -> dict[str, Any]:
    commit = {"id": sha, "title": "Merge branch 'x'", "author_name": "Léa", "author_email": "lea@acme.test",
              "committed_date": (NOW - timedelta(days=days)).isoformat()}
    return {"name": name, "message": message, "target": target or sha, "commit": commit, "release": release}


class ModelTests(unittest.TestCase):
    def test_annotated_lightweight_and_release(self) -> None:
        light = Tag.from_json(tag_json("v1"))
        annotated = Tag.from_json(tag_json("v2", "Version 2\n\nDétails", {"tag_name": "v2", "description": "Notes"},
                                           target="b" * 40))
        self.assertEqual((light.annotated, light.has_release, light.message), (False, False, ""))
        self.assertEqual((annotated.annotated, annotated.release_name, annotated.release_notes),
                         (True, "v2", "Notes"))
        self.assertEqual(first_line("\n  Version 2\nsuite"), "Version 2")


class FilterTests(unittest.TestCase):
    def setUp(self) -> None:
        stored = [(10, Tag.from_json(tag_json("v2.4.0", "Export CSV", {"description": "Relances"})), None),
                  (11, Tag.from_json(tag_json("rc-1", sha="b" * 40, days=40)), NOW.timestamp()),
                  (12, Tag.from_json(tag_json("untracked")), None)]
        self.rows = build_rows(stored, [BILLING, PORTAL], PersonDirectory([]))

    def names(self, rows: list[Any]) -> list[str]:
        return [r.tag.name for r in rows]

    def test_rows_of_tracked_repositories_with_deleted_mark_and_links(self) -> None:
        self.assertEqual(self.names(self.rows), ["v2.4.0", "rc-1"])
        self.assertIsNotNone(self.rows[1].deleted_at)
        self.assertEqual(self.rows[0].web_url, "https://gitlab.test/acme/billing-api/-/tags/v2.4.0")
        self.assertEqual(self.rows[1].web_url, "")

    def test_repository_text_sha_and_period_filters(self) -> None:
        self.assertEqual(self.names(visible_tags(self.rows, [11], "", None)), ["rc-1"])
        self.assertEqual(self.names(visible_tags(self.rows, [], "relances", None)), ["v2.4.0"])  # release notes
        self.assertEqual(self.names(visible_tags(self.rows, [], "export", None)), ["v2.4.0"])  # message
        self.assertEqual(self.names(visible_tags(self.rows, [], "4", None)), ["v2.4.0"])  # SHA prefix, 1 char
        self.assertEqual(self.names(visible_tags(self.rows, [], "b", None)), ["rc-1"])
        last_week = day_range(parse_date("09/10/2026"), parse_date("16/10/2026"))
        self.assertEqual(self.names(visible_tags(self.rows, [], "", last_week)), ["v2.4.0"])


class PipelineForge:
    """Forge stand-in for the tag pipeline reads; records calls."""

    def __init__(self) -> None:
        self.status = "running"
        self.calls: list[str] = []
        self.offline = False

    def latest_pipeline(self, project_id: int, ref: str) -> PipelineRef | None:
        if self.offline:
            raise NetworkError("down")
        self.calls.append("pipeline")
        return PipelineRef(5, self.status, NOW)

    def list_pipeline_jobs(self, project_id: int, pipeline_id: int) -> list[Job]:
        return [Job(1, "build", "success"), Job(2, "deploy", "failed", 12.0)]

    def job_log(self, project_id: int, job_id: int) -> str:
        self.calls.append(f"log {job_id}")
        return "ERROR: deploy failed\n"


class TagPipelineTests(unittest.TestCase):
    def test_read_until_finished_and_again_when_the_tag_moves(self) -> None:
        """TG-09: unfinished pipelines are read again, a finished one only if the tag points elsewhere."""
        forge = PipelineForge()
        data = ForgeData(forge, Store(MEMORY))  # type: ignore[arg-type]
        tag = Tag.from_json(tag_json("v1"))
        self.assertEqual(data.tag_pipeline(10, tag).pipeline.status, "running")  # type: ignore[union-attr]
        forge.status = "failed"
        detail = data.tag_pipeline(10, tag)
        self.assertEqual((detail.log_job_id, detail.log), (2, "ERROR: deploy failed\n"))
        data.tag_pipeline(10, tag)  # finished: from the base
        self.assertEqual(forge.calls, ["pipeline", "log 2", "pipeline", "log 2"])
        moved = Tag.from_json(tag_json("v1", sha="c" * 40))
        data.tag_pipeline(10, moved)
        self.assertEqual(forge.calls.count("pipeline"), 3)
        forge.offline = True
        offline = data.tag_pipeline(10, Tag.from_json(tag_json("v1", sha="d" * 40)))
        self.assertEqual(offline.pipeline.id, 5)  # type: ignore[union-attr]
        self.assertIsNotNone(data.offline_since)


if __name__ == "__main__":
    unittest.main()
