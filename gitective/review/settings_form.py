"""Validation of the Config tab before saving (OC-07): regexes, weights, thresholds and ranges."""

from __future__ import annotations

from dataclasses import dataclass

from gitective.shared.i18n import t
from gitective.review.rules import validate_regex
from gitective.settings.config_file import PARALLEL_RANGE, REFRESH_RANGE, Settings


@dataclass(frozen=True)
class NumberFields:
    """Numbers as typed in the form (a comma is accepted as decimal separator)."""

    weights: dict[str, str]
    green: str
    orange: str
    parallel: str
    sync_minutes: str
    dead_branch_days: str = "30"


def _number(text: str) -> float:
    return float(text.strip().replace(",", "."))


def _whole(text: str, bounds: tuple[int, int]) -> int | None:
    text = text.strip()
    if not text.isdigit() or not bounds[0] <= int(text) <= bounds[1]:
        return None
    return int(text)


def apply_numbers(settings: Settings, fields: NumberFields) -> str:
    """Check the regexes and store the typed numbers in `settings`; return an error message, "" when valid.

    Nothing must be saved when a message is returned.
    """
    checks = [(t("Regex de la règle « {name} »", name=r.name), r.pattern) for r in settings.rules]
    checks += [(t("Regex du lien ticket"), settings.link_regex), (t("Regex du n° de ticket"), settings.ticket_regex),
               (t("Regex d'exclusion des branches"), settings.branch_exclude_regex)]
    for label, pattern in checks:
        error = validate_regex(pattern)
        if error:
            return t("{label} invalide : {error}. Enregistrement annulé.", label=label, error=error)
    try:
        settings.weights = {c: _number(v) for c, v in fields.weights.items()}
        settings.green_threshold = _number(fields.green)
        settings.orange_threshold = _number(fields.orange)
    except ValueError:
        return t("Pondérations et seuils : saisissez des nombres.")
    # RC-06 only counts when it is ticked.
    counted = [w for c, w in settings.weights.items() if c != "assignee" or settings.assignee_rule]
    all_weights = [*counted, *(r.weight for r in settings.active_rules)]
    if any(w < 0 for w in all_weights) or sum(all_weights) <= 0:
        return t("Pondérations : valeurs positives avec un total supérieur à 0.")
    if not 0 <= settings.orange_threshold <= settings.green_threshold <= 100:
        return t("Seuils : il faut 0 ≤ orange ≤ vert ≤ 100.")
    parallel = _whole(fields.parallel, PARALLEL_RANGE)
    if parallel is None:
        return t("Requêtes simultanées : un nombre entier entre {low} et {high}.", low=PARALLEL_RANGE[0], high=PARALLEL_RANGE[1])
    minutes = _whole(fields.sync_minutes, REFRESH_RANGE)
    if minutes is None:
        return t("Synchronisation automatique : un nombre de minutes entre {low} et {high}.", low=REFRESH_RANGE[0],
                 high=REFRESH_RANGE[1])
    dead_days = _whole(fields.dead_branch_days, (1, 100_000))
    if dead_days is None:
        return t("Branche morte : un nombre entier de jours, au moins 1.")
    settings.parallel_requests, settings.sync_minutes, settings.dead_branch_days = parallel, minutes, dead_days
    return ""
