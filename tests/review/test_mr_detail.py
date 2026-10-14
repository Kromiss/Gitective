"""Tests of the MR detail panel data: forge parsing, storage and merge readiness (6.6)."""

from __future__ import annotations

import unittest
from datetime import datetime, timezone
from typing import Any

from gitective.database.store import MEMORY, Store
from gitective.database.sync import MrDetailData, ForgeData
from gitective.forge.errors import NetworkError
from gitective.forge.models import (
    Approvals,
    ChangedFile,
    CommitStatus,
    Discussion,
    Job,
    MergeRequest,
    MergeState,
    PipelineRef,
    User,
)
from gitective.review.mr_detail import (
    WARN,
    discussion_place,
    log_tail,
    readiness,
    top_files,
    unresolved_discussions,
)
from gitective.review.rules import KO, NA, OK
from tests.factories import mr_json, user_json

NOW = datetime(2026, 10, 14, 19, 0, tzinfo=timezone.utc)
ALICE = User.from_json(user_json(1, "alice"))


def mr(state: str = "opened", draft: bool = False) -> MergeRequest:
    data = mr_json(iid=87, state=state, draft=draft)
    data["sha"] = "abc"
    return MergeRequest.from_json(data)


def detail(**changes: Any) -> MrDetailData:
    base: dict[str, Any] = {
        "fetched_at": NOW,
        "state": MergeState("mergeable", pipeline=PipelineRef(5, "success")),
        "approvals": Approvals((ALICE,), required=1, left=0),
    }
    base.update(changes)
    return MrDetailData(**base)


class ParsingTests(unittest.TestCase):
    def test_merge_request_people_and_path(self) -> None:
        data = mr_json(iid=3)
        data.update(assignees=[user_json(7, "me")], reviewers=[user_json(8, "rev")],
                    references={"full": "group/sub/repo!3"})
        parsed = MergeRequest.from_json(data)
        self.assertEqual([u.username for u in parsed.assignees], ["me"])
        self.assertEqual([u.username for u in parsed.reviewers], ["rev"])
        self.assertEqual(parsed.project_path, "group/sub/repo")
        old_style = mr_json(iid=4)
        old_style["assignee"] = user_json(9, "solo")
        self.assertEqual([u.id for u in MergeRequest.from_json(old_style).assignees], [9])

    def test_merge_state_approvals_discussions_files(self) -> None:
        state = MergeState.from_json({"detailed_merge_status": "ci_must_pass", "has_conflicts": True,
                                      "diverged_commits_count": 4, "blocking_discussions_resolved": False,
                                      "head_pipeline": {"id": 9, "status": "failed", "web_url": "u"}})
        self.assertEqual((state.merge_status, state.has_conflicts, state.behind_by), ("ci_must_pass", True, 4))
        self.assertEqual(state.pipeline, PipelineRef(9, "failed", None, "u"))
        approvals = Approvals.from_json({"approved_by": [{"user": user_json(1, "alice")}], "approvals_required": 2,
                                         "approvals_left": 1})
        self.assertEqual((len(approvals.approved_by), approvals.required, approvals.left), (1, 2, 1))
        thread = Discussion.from_json({"notes": [
            {"resolvable": True, "resolved": False, "author": user_json(2, "bob"), "body": "Arrondi ?",
             "position": {"new_path": "src/DiscountService.java", "new_line": 88}},
            {"resolvable": True, "resolved": True, "author": user_json(1, "alice"), "body": "ok"}]})
        assert thread is not None
        self.assertFalse(thread.resolved)
        self.assertEqual(discussion_place(thread), "DiscountService.java:88")
        self.assertIsNone(Discussion.from_json({"notes": [{"resolvable": False, "author": user_json(2, "bob")}]}))
        changed = ChangedFile.from_json({"new_path": "a.py", "diff": "@@ -1 +1 @@\n-old\n+new\n+more\n context"})
        self.assertEqual((changed.added, changed.removed), (2, 1))

    def test_detail_round_trips_through_the_store(self) -> None:
        store = Store(MEMORY)
        original = detail(discussions=(Discussion(ALICE, "x", False, "a.py", 3),),
                          files=(ChangedFile("a.py", 3, 1),), jobs=(Job(1, "tests", "failed", 240.0),),
                          statuses=(CommitStatus("jenkins", "failed", NOW),), log="boom")
        store.put_mr_detail(10, 87, 1.0, original)
        self.assertEqual(store.get_mr_detail(10, 87, MrDetailData), (1.0, original))


class DetailForge:
    base_url = "https://gitlab.test"

    def __init__(self) -> None:
        self.calls: list[str] = []
        self.offline = False

    def _call(self, name: str) -> None:
        if self.offline:
            raise NetworkError("down")
        self.calls.append(name)

    def get_merge_state(self, project_id: int, iid: int) -> MergeState:
        self._call("state")
        return MergeState("ci_must_pass", pipeline=PipelineRef(5, "failed"))

    def get_approvals(self, project_id: int, iid: int) -> Approvals:
        self._call("approvals")
        return Approvals()

    def list_discussions(self, project_id: int, iid: int) -> list[Discussion]:
        self._call("discussions")
        return []

    def list_changed_files(self, project_id: int, iid: int) -> list[ChangedFile]:
        self._call("files")
        return [ChangedFile("a.py", 1, 0)]

    def list_pipeline_jobs(self, project_id: int, pipeline_id: int) -> list[Job]:
        self._call("jobs")
        return [Job(11, "lint", "success"), Job(12, "tests", "failed", 60.0)]

    def job_log(self, project_id: int, job_id: int) -> str:
        self._call(f"log:{job_id}")
        return "x" * 30_000 + "\nFAIL"

    def list_commit_statuses(self, project_id: int, sha: str) -> list[CommitStatus]:
        self._call("statuses")
        return []


class DetailSyncTests(unittest.TestCase):
    def test_open_mr_read_once_per_session_and_failed_job_log_tail_kept(self) -> None:
        forge = DetailForge()
        data = ForgeData(forge, Store(MEMORY))  # type: ignore[arg-type]
        first = data.mr_detail(10, mr())
        self.assertEqual(forge.calls, ["state", "jobs", "log:12", "approvals", "discussions", "files"])
        self.assertTrue(first.log.endswith("FAIL"))
        self.assertLessEqual(len(first.log), 20_000)
        data.mr_detail(10, mr())
        self.assertEqual(len(forge.calls), 6)  # same session: stored copy
        data.new_session()
        data.mr_detail(10, mr())
        self.assertEqual(len(forge.calls), 12)

    def test_merged_mr_read_once_and_offline_fallback(self) -> None:
        forge = DetailForge()
        store = Store(MEMORY)
        merged = mr(state="merged")
        ForgeData(forge, store).mr_detail(10, merged)  # type: ignore[arg-type]
        self.assertNotIn("state", forge.calls)
        self.assertIn("statuses", forge.calls)  # no pipeline known: commit statuses instead
        count = len(forge.calls)
        again = ForgeData(forge, store)  # type: ignore[arg-type]
        again.mr_detail(10, merged)
        self.assertEqual(len(forge.calls), count)
        forge.offline = True
        offline = ForgeData(forge, store)  # type: ignore[arg-type]
        self.assertEqual(offline.mr_detail(10, mr()).files, (ChangedFile("a.py", 1, 0),))  # stored copy
        with self.assertRaises(NetworkError):
            offline.mr_detail(11, mr())  # nothing stored for this project


class ReadinessTests(unittest.TestCase):
    def statuses(self, result: Any) -> dict[str, str]:
        return {i.text: i.status for i in result.items}

    def test_mergeable_mr_is_ready(self) -> None:
        result = readiness(mr(), detail())
        assert result is not None
        self.assertTrue(result.ready)
        self.assertEqual(self.statuses(result), {"Pas de conflit": OK, "Pipeline vert": OK,
                                                 "Discussions résolues": OK, "Approuvée 1 / 1": OK})

    def test_blocking_points_make_it_not_ready(self) -> None:
        thread = Discussion(ALICE, "Arrondi ?", False, "a.py", 1)
        result = readiness(mr(), detail(
            state=MergeState("ci_must_pass", has_conflicts=True, behind_by=4, blocking_discussions_resolved=True,
                             pipeline=PipelineRef(5, "failed")),
            approvals=Approvals((), required=1, left=1),
            discussions=(thread, Discussion(ALICE, "ok", True)),
            jobs=(Job(1, "tests-unitaires", "failed"),)))
        assert result is not None
        self.assertFalse(result.ready)
        self.assertEqual(self.statuses(result), {
            "Conflits à résoudre": KO, "Pipeline en échec": KO, "1 discussion(s) non résolue(s)": WARN,
            "Approuvée 0 / 1": KO, "4 commit(s) de retard sur main": WARN})
        self.assertEqual(next(i for i in result.items if i.status == KO and "Pipeline" in i.text).note,
                         "tests-unitaires")

    def test_draft_external_ci_and_free_edition_approvals(self) -> None:
        result = readiness(mr(draft=True), detail(
            state=MergeState("draft_status"), approvals=Approvals((ALICE,)),
            statuses=(CommitStatus("jenkins", "success", NOW),)))
        assert result is not None
        self.assertFalse(result.ready)
        statuses = self.statuses(result)
        self.assertEqual(statuses["CI verte"], OK)
        self.assertEqual(statuses["Approuvée par 1 personne(s)"], OK)
        self.assertEqual(statuses["MR en brouillon"], KO)
        self.assertEqual(self.statuses(readiness(mr(), detail(state=MergeState("mergeable"))))["Aucun pipeline"], NA)

    def test_not_shown_for_merged_mr(self) -> None:
        self.assertIsNone(readiness(mr(state="merged"), detail()))


class HelperTests(unittest.TestCase):
    def test_log_tail_strips_colors_and_sections(self) -> None:
        log = ("\x1b[0Ksection_start:1:step\r\x1b[0K\x1b[32;1mRunning tests\x1b[0;m\n"
               + "\n".join(f"line {i}" for i in range(20))
               + "\n\x1b[31;1mFAIL test_discount_rounding\x1b[0;m\nUploading artifacts\nCleaning up project\n")
        tail = log_tail(log, lines=3)
        self.assertEqual(tail, "line 18\nline 19\nFAIL test_discount_rounding")

    def test_top_files_and_unresolved(self) -> None:
        files = [ChangedFile(f"f{i}.py", i, 0) for i in range(7)]
        shown, hidden = top_files(files, 5)
        self.assertEqual([f.path for f in shown], ["f6.py", "f5.py", "f4.py", "f3.py", "f2.py"])
        self.assertEqual(hidden, 2)
        threads = [Discussion(ALICE, "a", False), Discussion(ALICE, "b", True)]
        self.assertEqual([d.body for d in unresolved_discussions(threads)], ["a"])
        self.assertEqual(discussion_place(threads[0]), "description")


if __name__ == "__main__":
    unittest.main()
