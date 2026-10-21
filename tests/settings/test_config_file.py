"""config.json loading and saving, and the Config tab validation (section 3, OC-07)."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from gitective.review.settings_form import NumberFields, apply_numbers, changes_by_page, group_error
from gitective.settings import config_file as config
from gitective.settings.config_file import CustomRule, Settings


def fields(**changes: object) -> NumberFields:
    values: dict[str, object] = {"weights": {"ticket": "25", "self_merge": "25", "pipeline": "25", "assignee": "25"},
                                 "green": "100", "orange": "50", "parallel": "6", "sync_minutes": "5"}
    values.update(changes)
    return NumberFields(**values)  # type: ignore[arg-type]


class RegexGroupTests(unittest.TestCase):
    def test_group_must_exist_in_the_regex(self) -> None:
        self.assertEqual(group_error(r"(#)(\d+)", "2"), "")
        self.assertEqual(group_error(r"(#)(\d+)", "0"), "")
        self.assertEqual(group_error("", "0"), "")
        self.assertIn("2 groupe", group_error(r"(#)(\d+)", "3"))
        self.assertTrue(group_error(r"(#)(\d+)", "-1"))
        self.assertTrue(group_error(r"(#)(\d+)", "x"))

    def test_saved_groups_are_kept_and_checked(self) -> None:
        loaded = Settings.from_dict({"ticket_group": 2, "link_group": 1,
                                     "rules": [{"name": "a", "group": 3}, {"name": "b", "group": "x"}]})
        self.assertEqual((loaded.ticket_group, loaded.link_group), (2, 1))
        self.assertEqual([r.group for r in loaded.rules], [3, 0])
        self.assertEqual(Settings.from_dict({"ticket_group": -1}).ticket_group, 0)

    def test_save_refuses_a_missing_group(self) -> None:
        settings = Settings(ticket_regex=r"(#)(\d+)")
        self.assertIn("1 groupe", apply_numbers(Settings(link_regex="(a)"), fields(link_group="2")))
        self.assertEqual(apply_numbers(settings, fields(ticket_group="2")), "")
        self.assertEqual(settings.ticket_group, 2)


class UnsavedChangesTests(unittest.TestCase):
    """Config sub-tabs flag what differs from the saved settings (OC-15)."""

    def test_counts_per_sub_tab(self) -> None:
        saved = {"general.url": "a", "general.theme": "dark", "rules.green": "100", "advanced.parallel": "6"}
        form = dict(saved, **{"general.url": "b", "general.theme": "light", "advanced.parallel": "8"})
        self.assertEqual(changes_by_page(saved, form), {"general": 2, "advanced": 1})

    def test_back_to_the_saved_value_is_clean(self) -> None:
        saved = {"rules.rules": "[]"}
        self.assertEqual(changes_by_page(saved, {"rules.rules": "[]"}), {})

    def test_added_or_removed_key_counts(self) -> None:
        self.assertEqual(changes_by_page({"rules.weight_x": "1"}, {}), {"rules": 1})


class ConfigFileTests(unittest.TestCase):
    def test_config_view_is_remembered_and_checked(self) -> None:
        self.assertEqual(Settings.from_dict({"config_view": "advanced"}).config_view, "advanced")
        self.assertEqual(Settings.from_dict({"config_view": "nope"}).config_view, "general")

    def test_new_settings_survive_a_save_and_a_load(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "config.json"
            settings = Settings(assignee_rule=True, notify_merges=False, notify_assigned=True, sync_minutes=12,
                                detail_width=500, notify_own_merged=False)
            settings.filters.assignees, settings.filters.drafts = ["p:kevin"], "only"
            config.save(settings, path)
            again = config.load(path)
            self.assertEqual((again.assignee_rule, again.notify_merges, again.notify_assigned, again.sync_minutes,
                              again.detail_width, again.notify_own_merged), (True, False, True, 12, 500, False))
            self.assertEqual((again.filters.assignees, again.filters.drafts), (["p:kevin"], "only"))

    def test_older_file_gets_safe_defaults(self) -> None:
        old = Settings.from_dict({"gitlab_url": "https://gitlab.test", "overview_refresh": 9,
                                  "weights": {"ticket": 10, "self_merge": 20, "pipeline": 30}})
        self.assertEqual((old.sync_minutes, old.assignee_rule, old.notify_merges, old.notify_assigned,
                          old.detail_width, old.notify_own_merged), (9, False, True, True, 420, True))
        self.assertEqual(old.weights["assignee"], 25.0)
        self.assertEqual((old.filters.assignees, old.filters.reviewers, old.filters.drafts), ([], [], "all"))

    def test_out_of_range_values_are_clamped(self) -> None:
        settings = Settings.from_dict({"sync_minutes": 0, "detail_width": 5000, "parallel_requests": "x"})
        self.assertEqual((settings.sync_minutes, settings.detail_width, settings.parallel_requests), (1, 900, 6))
        self.assertEqual(Settings.from_dict({"detail_width": 10}).detail_width, 280)
        # A damaged value must not throw the whole file (and the token) away.
        damaged = Settings.from_dict({"token": "secret", "detail_width": "wide", "sync_minutes": None})
        self.assertEqual((damaged.token, damaged.detail_width, damaged.sync_minutes), ("secret", 420, 5))

    def test_branch_and_tag_settings(self) -> None:
        """BR-04, BR-05, BR-06, TG-04: defaults, then values read back; unknown states are dropped."""
        default = Settings.from_dict({})
        self.assertEqual((default.branch_exclude_regex, default.dead_branch_days, default.branch_filters.states,
                          default.tag_filters.total),
                         (r"^(main|master|develop.*)$", 30, ["active", "dead", "merged"], True))
        read = Settings.from_dict({"dead_branch_days": "0", "branch_filters": {"states": ["deleted", "zz"]},
                                   "tag_filters": "broken", "branch_exclude_regex": "^wip/"})
        self.assertEqual((read.dead_branch_days, read.branch_filters.states, read.tag_filters.total,
                          read.branch_exclude_regex), (1, ["deleted"], True, "^wip/"))

    def test_compare_lines_survive_a_save_and_a_load(self) -> None:
        """TC-02, TG-01."""
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "config.json"
            settings = Settings(tags_view="compare")
            settings.tag_compares = [config.CompareLine(10, "main", "v1.0", "a1")]
            config.save(settings, path)
            again = config.load(path)
            self.assertEqual((again.tags_view, again.tag_compares), ("compare", settings.tag_compares))
        self.assertEqual(Settings.from_dict({"tags_view": "x", "tag_compares": ["bad"]}).tags_view, "browse")

    def test_unreadable_file_gives_defaults(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "config.json"
            path.write_text("{not json", encoding="utf-8")
            self.assertEqual(config.load(path), Settings())


class FormValidationTests(unittest.TestCase):
    def test_valid_form_is_stored_with_comma_decimals(self) -> None:
        settings = Settings()
        error = apply_numbers(settings, fields(green="99,5", parallel=" 8 ", sync_minutes="15"))
        self.assertEqual(error, "")
        self.assertEqual((settings.green_threshold, settings.parallel_requests, settings.sync_minutes), (99.5, 8, 15))

    def test_invalid_regex_blocks_saving(self) -> None:
        settings = Settings(rules=[CustomRule(name="Cassée", pattern="(")])
        self.assertIn("règle « Cassée »", apply_numbers(settings, fields()))
        self.assertIn("lien ticket", apply_numbers(Settings(link_regex="[a-"), fields()))

    def test_branch_regex_and_dead_days_validated(self) -> None:
        """OC-07, OC-10."""
        self.assertIn("exclusion des branches", apply_numbers(Settings(branch_exclude_regex="(main"), fields()))
        self.assertIn("Branche morte", apply_numbers(Settings(), fields(dead_branch_days="0")))
        settings = Settings()
        self.assertEqual(apply_numbers(settings, fields(dead_branch_days=" 45 ")), "")
        self.assertEqual(settings.dead_branch_days, 45)

    def test_numbers_weights_and_thresholds(self) -> None:
        self.assertIn("saisissez des nombres", apply_numbers(Settings(), fields(green="beaucoup")))
        self.assertIn("valeurs positives", apply_numbers(Settings(), fields(
            weights={"ticket": "-1", "self_merge": "0", "pipeline": "0", "assignee": "0"})))
        self.assertIn("orange ≤ vert", apply_numbers(Settings(), fields(green="40", orange="60")))

    def test_rc06_weight_counts_only_when_ticked(self) -> None:
        no_rules = Settings(rules=[])
        only_rc06 = {"ticket": "0", "self_merge": "0", "pipeline": "0", "assignee": "25"}
        self.assertIn("total supérieur à 0", apply_numbers(no_rules, fields(weights=only_rc06)))
        self.assertEqual(apply_numbers(Settings(rules=[], assignee_rule=True), fields(weights=only_rc06)), "")

    def test_ranges(self) -> None:
        self.assertIn("Requêtes simultanées", apply_numbers(Settings(), fields(parallel="17")))
        self.assertIn("Synchronisation automatique", apply_numbers(Settings(), fields(sync_minutes="0")))
        self.assertIn("Synchronisation automatique", apply_numbers(Settings(), fields(sync_minutes="2.5")))


class LanguageAndNewMrSettingsTests(unittest.TestCase):
    def test_language_defaults_to_french_and_new_mr_notifications_off(self) -> None:
        self.assertEqual((Settings().language, Settings().notify_new_mrs), ("fr", False))
        loaded = Settings.from_dict({"language": "en", "notify_new_mrs": True})
        self.assertEqual((loaded.language, loaded.notify_new_mrs), ("en", True))
        self.assertEqual(Settings.from_dict({"language": "de"}).language, "fr")


if __name__ == "__main__":
    unittest.main()
