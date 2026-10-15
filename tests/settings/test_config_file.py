"""config.json loading and saving, and the Config tab validation (section 3, OC-07)."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from gitective.review.settings_form import NumberFields, apply_numbers
from gitective.settings import config_file as config
from gitective.settings.config_file import CustomRule, Settings


def fields(**changes: object) -> NumberFields:
    values: dict[str, object] = {"weights": {"ticket": "25", "self_merge": "25", "pipeline": "25", "assignee": "25"},
                                 "green": "100", "orange": "50", "parallel": "6", "sync_minutes": "5"}
    values.update(changes)
    return NumberFields(**values)  # type: ignore[arg-type]


class ConfigFileTests(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
