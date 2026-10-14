"""Tests of the process rules, score, people mapping and statistics."""

import unittest

from gitective.forge.models import Commit, MergeRequest, User
from gitective.settings.config_file import CustomRule, Person, Settings
from gitective.shared.people import PersonDirectory
from gitective.review.rules import (
    ASSIGNEE,
    KO,
    NA,
    OK,
    PIPELINE,
    SELF_MERGE,
    TICKET,
    MrFields,
    RuleSet,
    score_level,
    validate_regex,
)
from gitective.reporting.statistics import format_days, per_person, weekly_scores
from tests.factories import commit_json, mr_json, user_json

TITLE = CustomRule(name="Titre conforme", field="title", pattern=r"^\[[A-Z]+-\d+\] .+", id="r_title")
LINK = CustomRule(name="Lien ticket", field="description", pattern=r"https://jira\.test/browse/[A-Z]+-\d+", id="r_link")
LINK_REGEX = r"https://jira\.test/browse/[A-Z]+-\d+"
TICKET_REGEX = r"[A-Z]+-\d+"
WEIGHTS = {TICKET: 25.0, SELF_MERGE: 25.0}


def make_rules(*extra: CustomRule) -> RuleSet:
    return RuleSet([TITLE, LINK, *extra], LINK_REGEX, TICKET_REGEX, WEIGHTS)


class CustomRuleTests(unittest.TestCase):
    def test_match_and_no_match_modes(self) -> None:
        forbidden = CustomRule(name="Pas de WIP", field="title", pattern="WIP", mode="no_match", id="r_wip")
        rules = make_rules(forbidden)
        ok = rules.check_fields(MrFields(title="[PROJ-1] Done", description=""))
        ko = rules.check_fields(MrFields(title="WIP stuff", description=""))
        self.assertEqual(ok["r_title"].status, OK)
        self.assertEqual(ok["r_wip"].status, OK)
        self.assertEqual(ko["r_title"].status, KO)
        self.assertEqual(ko["r_wip"].status, KO)

    def test_branch_fields(self) -> None:
        rule = CustomRule(name="Branche", field="source_branch", pattern=r"^(feature|fix)/", id="r_branch")
        rules = make_rules(rule)
        self.assertEqual(rules.check_fields(MrFields("t", "", source_branch="feature/x"))["r_branch"].status, OK)
        self.assertEqual(rules.check_fields(MrFields("t", "", source_branch="misc"))["r_branch"].status, KO)

    def test_commit_rule_requires_every_commit(self) -> None:
        rule = CustomRule(name="Commits", field="commits", pattern=r"^[A-Z]+-\d+", id="r_commits")
        rules = make_rules(rule)
        self.assertTrue(rules.needs_commits)
        good = MrFields("t", "", commits=(("a1", "PROJ-1 fix"), ("b2", "PROJ-1 test")))
        bad = MrFields("t", "", commits=(("a1", "PROJ-1 fix"), ("b2", "oops")))
        self.assertEqual(rules.check_fields(good)["r_commits"].status, OK)
        result = rules.check_fields(bad)["r_commits"]
        self.assertEqual(result.status, KO)
        self.assertIn("b2", result.detail)

    def test_commit_rule_without_commits_is_na(self) -> None:
        rule = CustomRule(name="Commits", field="commits", pattern="x", id="r_commits")
        self.assertEqual(make_rules(rule).check_fields(MrFields("t", ""))["r_commits"].status, NA)

    def test_inactive_rule_is_ignored(self) -> None:
        rule = CustomRule(name="Off", field="title", pattern="never", active=False, id="r_off")
        rules = make_rules(rule)
        self.assertNotIn("r_off", rules.check_fields(MrFields("t", "")))
        self.assertNotIn("r_off", [c.id for c in rules.criteria])

    def test_rule_without_pattern_is_ko(self) -> None:
        rules = RuleSet([CustomRule(name="Vide", id="r_empty")], LINK_REGEX, TICKET_REGEX, WEIGHTS)
        self.assertEqual(rules.check_fields(MrFields("t", ""))["r_empty"].status, KO)


class TicketRuleTests(unittest.TestCase):
    def check(self, title: str, description: str) -> tuple[str, str]:
        result = make_rules().check_fields(MrFields(title, description))[TICKET]
        return result.status, result.detail

    def test_same_ticket(self) -> None:
        self.assertEqual(self.check("[PROJ-12] x", "https://jira.test/browse/PROJ-12"), (OK, "PROJ-12"))

    def test_different_ticket(self) -> None:
        status, detail = self.check("[PROJ-12] x", "https://jira.test/browse/PROJ-21")
        self.assertEqual(status, KO)
        self.assertEqual(detail, "PROJ-12 (titre) ≠ PROJ-21 (lien)")

    def test_missing_in_title_or_link(self) -> None:
        self.assertIn("absent du titre", self.check("No ticket", "https://jira.test/browse/PROJ-1")[1])
        self.assertIn("absent du lien", self.check("[PROJ-1] x", "no link")[1])
        self.assertIn("titre et du lien", self.check("x", "y")[1])

    def test_named_group_extracts_ticket(self) -> None:
        rules = RuleSet([], r"https://jira\.test/browse/\S+", r"(?:#|/)(?P<ticket>\d+)", WEIGHTS)
        result = rules.check_fields(MrFields("Fix #42", "https://jira.test/browse/42"))[TICKET]
        self.assertEqual((result.status, result.detail), (OK, "42"))

    def test_validate_regex(self) -> None:
        self.assertIsNone(validate_regex(TICKET_REGEX))
        self.assertIsNotNone(validate_regex("(unclosed"))


class EvaluationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.people = PersonDirectory([Person(name="Alice Martin", account_ids=[1, 7])])

    def evaluate(self, **kwargs: object) -> object:
        mr = MergeRequest.from_json(mr_json(**kwargs))  # type: ignore[arg-type]
        return make_rules().evaluate(mr, "group/repo", self.people)

    def test_compliant_mr_scores_100(self) -> None:
        ev = self.evaluate(merger=user_json(2, "bob"))
        self.assertEqual({r.status for k, r in ev.results.items() if k != PIPELINE}, {OK})
        self.assertEqual(ev.results[PIPELINE].status, NA)  # no CI expected by default
        self.assertEqual(ev.score, 100.0)

    def test_self_merge_with_other_account_is_ko(self) -> None:
        ev = self.evaluate(merger=user_json(7, "alice2"))
        self.assertEqual(ev.results[SELF_MERGE].status, KO)
        self.assertEqual(ev.score, 75.0)

    def test_open_mr_self_merge_na_excluded_from_score(self) -> None:
        ev = self.evaluate(state="opened", title="bad title")
        self.assertEqual(ev.results[SELF_MERGE].status, NA)
        # title KO and ticket KO (absent from title) out of 3 applicable criteria of weight 25.
        self.assertAlmostEqual(ev.score, 100 / 3, places=4)

    def test_commits_are_used_when_given(self) -> None:
        rule = CustomRule(name="Commits", field="commits", pattern="^PROJ", id="r_c")
        mr = MergeRequest.from_json(mr_json(merger=user_json(2, "bob")))
        commits = [Commit.from_json(commit_json("aaa", "PROJ-1 ok")), Commit.from_json(commit_json("bbb", "nope"))]
        ev = make_rules(rule).evaluate(mr, "group/repo", self.people, commits)
        self.assertEqual(ev.results["r_c"].status, KO)

    def test_score_level(self) -> None:
        self.assertEqual(score_level(100, 100, 50), "green")
        self.assertEqual(score_level(50, 100, 50), "orange")
        self.assertEqual(score_level(49.9, 100, 50), "red")


class PeopleAndStatsTests(unittest.TestCase):
    def test_unmapped_account_is_its_own_person(self) -> None:
        directory = PersonDirectory([])
        ref = directory.for_user(MergeRequest.from_json(mr_json()).author)
        self.assertEqual(ref.key, "u:1")

    def test_git_identity_mapping(self) -> None:
        directory = PersonDirectory([Person(name="Alice", git_identities=["alice@test"])])
        self.assertEqual(directory.for_git("whatever", "ALICE@test").name, "Alice")
        self.assertTrue(directory.for_git("Bob", "bob@test").key.startswith("g:"))

    def test_avatar_from_most_recent_account(self) -> None:
        directory = PersonDirectory([Person(name="Alice", account_ids=[3, 9, 5])])
        user = User.from_json(user_json(5, "alice5"))
        self.assertEqual(directory.for_user(user).avatar_user_id, 9)

    def test_per_person_and_weekly(self) -> None:
        people = PersonDirectory([])
        rules = make_rules()
        evs = [
            rules.evaluate(MergeRequest.from_json(mr_json(iid=1, merger=user_json(2, "bob"))), "g/r", people),
            rules.evaluate(MergeRequest.from_json(mr_json(iid=2, title="bad", merger=user_json(2, "bob"),
                                                          created_at="2026-09-28T08:00:00Z")), "g/r", people),
        ]
        stats = {s.person.key: s for s in per_person(evs)}
        self.assertEqual(stats["u:1"].mr_count, 2)
        self.assertEqual(stats["u:1"].ko_counts["r_title"], 1)
        self.assertIsNotNone(stats["u:1"].lead_time_days)
        # The merger gets a row of its own, without authored MRs (ST-13).
        self.assertEqual((stats["u:2"].mr_count, stats["u:2"].merged_count, stats["u:2"].score_avg), (0, 2, None))
        weeks, series = weekly_scores(evs, ["u:1"])
        self.assertEqual(len(weeks), 2)
        self.assertEqual(len(series["u:1"]), 2)
        self.assertEqual(format_days(2.25), "2,2 j")


class AssigneeRuleTests(unittest.TestCase):
    """RC-06 and the merger-is-not-the-assignee flag (TA-05)."""

    def evaluate(self, active: bool, assignees: list[dict], merger_id: int = 2, people: list[Person] | None = None):
        data = mr_json(merger=user_json(merger_id, "merger"))
        data["assignees"] = assignees
        rules = RuleSet([TITLE, LINK], LINK_REGEX, TICKET_REGEX, {**WEIGHTS, ASSIGNEE: 25.0}, assignee_rule=active)
        return rules, rules.evaluate(MergeRequest.from_json(data), "group/repo", PersonDirectory(people or []))

    def test_inactive_rule_adds_no_column_but_keeps_the_flag(self) -> None:
        rules, ev = self.evaluate(False, [user_json(3, "carol")])
        self.assertNotIn(ASSIGNEE, ev.results)
        self.assertNotIn(ASSIGNEE, [c.id for c in rules.criteria])
        self.assertEqual(ev.merger_not_assignee, "Mergée par Merger, assignée à Carol")

    def test_active_rule_counts_in_the_score(self) -> None:
        rules, ev = self.evaluate(True, [user_json(3, "carol")])
        self.assertIn(ASSIGNEE, [c.id for c in rules.criteria])
        self.assertEqual(ev.results[ASSIGNEE].status, KO)
        _, ok = self.evaluate(True, [user_json(2, "merger"), user_json(3, "carol")])
        self.assertEqual(ok.results[ASSIGNEE].status, OK)
        self.assertGreater(ok.score, ev.score)

    def test_same_person_other_account_and_missing_assignee(self) -> None:
        people = [Person(name="Carol", account_ids=[3, 30])]
        _, same = self.evaluate(True, [user_json(3, "carol")], merger_id=30, people=people)
        self.assertEqual((same.results[ASSIGNEE].status, same.merger_not_assignee), (OK, ""))
        _, none = self.evaluate(True, [])
        self.assertEqual(none.results[ASSIGNEE].status, NA)


class SettingsTests(unittest.TestCase):
    def test_missing_keys_use_defaults(self) -> None:
        settings = Settings.from_dict({"parallel_requests": 99, "weights": {"ticket": 5}})
        self.assertEqual([r.id for r in settings.rules], ["r_title", "r_link"])
        self.assertEqual(settings.parallel_requests, 16)
        self.assertEqual(settings.weights, {"ticket": 5.0, "self_merge": 25.0, "pipeline": 25.0, "assignee": 25.0})
        self.assertFalse(settings.assignee_rule)
        self.assertEqual(settings.filters.drafts, "all")

    def test_former_overview_refresh_key_and_bad_drafts_value(self) -> None:
        settings = Settings.from_dict({"overview_refresh": 12, "filters": {"drafts": "maybe", "assignees": ["u:7"]}})
        self.assertEqual(settings.sync_minutes, 12)
        self.assertEqual((settings.filters.drafts, settings.filters.assignees), ("all", ["u:7"]))

    def test_round_trip(self) -> None:
        settings = Settings()
        settings.rules.append(CustomRule(name="X", field="commits", pattern="y", mode="no_match"))
        again = Settings.from_dict(settings.to_dict())
        self.assertEqual(again.rules, settings.rules)


if __name__ == "__main__":
    unittest.main()
