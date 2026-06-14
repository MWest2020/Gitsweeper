"""Compose DORA + retro into one team-level deliverable message.

This capability does no analysis of its own: it takes a finished
:class:`~gitsweeper.capabilities.dora_metrics.DoraReport` and
:class:`~gitsweeper.capabilities.retro_signals.RetroReport` and renders them
into a Slack Block Kit payload or a human-readable markdown summary, and can
POST the Block Kit payload to a single incoming webhook.

Two guarantees are encoded here so they cannot regress:

- **Team-level only.** Neither report carries authors, and this module never
  introduces an author, login, or ``@``-mention. References are plain
  ``#<number>`` PR numbers.
- **No implicit egress.** :func:`post_to_webhook` is the only outward-facing
  function; it accepts an injectable ``http_client`` so it can be exercised
  against a fake transport in tests and is never called unless the CLI was
  given ``--post`` together with ``SLACK_WEBHOOK_URL``.

The caller passes ``generated_at`` in ``meta`` — this module never calls
``datetime.now`` so the rendered output is deterministic for a given input.
"""

from __future__ import annotations

import httpx

from gitsweeper.capabilities.dora_metrics import DoraReport
from gitsweeper.capabilities.retro_signals import RetroReport

DEFAULT_TIMEOUT = 30.0


class DeliveryError(RuntimeError):
    """Raised when posting the payload to the webhook fails."""


# --- value formatting -------------------------------------------------------


def _fmt(value: float | None, *, suffix: str = "") -> str:
    """Format an optional metric value; ``None`` renders as an em-dash."""
    if value is None:
        return "—"
    return f"{value:.2f}{suffix}"


def _fmt_pct(value: float | None) -> str:
    if value is None:
        return "—"
    return f"{value * 100:.0f}%"


def _band(band: str | None) -> str:
    return band if band else "—"


def _pr_list(numbers: list[int]) -> str:
    """Render plain PR numbers as ``#1, #2`` — never an author or link."""
    if not numbers:
        return "none"
    return ", ".join(f"#{n}" for n in numbers)


def _pr_count_list(pairs: list[tuple[int, int]]) -> str:
    """Render ``(number, count)`` pairs as ``#1 (3), #2 (2)``."""
    if not pairs:
        return "none"
    return ", ".join(f"#{n} ({count})" for n, count in pairs)


# --- shared content lines ---------------------------------------------------


def _dora_lines(dora: DoraReport) -> list[tuple[str, str]]:
    """The four DORA metrics as (label, value-with-band) pairs."""
    return [
        (
            "Deployment frequency",
            f"{_fmt(dora.deploy_frequency.value, suffix='/day')} "
            f"({_band(dora.deploy_frequency.band)})",
        ),
        (
            "Lead time (median)",
            f"{_fmt(dora.lead_time['median'], suffix='d')} "
            f"({_band(dora.lead_time_band)})",
        ),
        (
            "Change failure rate",
            f"{_fmt_pct(dora.change_failure_rate.value)} "
            f"({_band(dora.change_failure_rate.band)})",
        ),
        (
            "Time to restore (median)",
            f"{_fmt(dora.time_to_restore.value, suffix='d')} "
            f"({_band(dora.time_to_restore.band)})",
        ),
    ]


def _retro_lines(retro: RetroReport) -> list[tuple[str, str]]:
    """The five retro signals as (label, PR-reference) pairs."""
    return [
        ("Stale open PRs", _pr_list(retro.stale_open)),
        ("Long threads", _pr_count_list(retro.long_threads)),
        ("Friction", _pr_count_list(retro.friction)),
        ("Tech debt", _pr_count_list(retro.tech_debt)),
        ("Smooth merges", _pr_list(retro.smooth)),
    ]


# --- Slack Block Kit --------------------------------------------------------


def build_blockkit(
    dora_report: DoraReport, retro_report: RetroReport, meta: dict
) -> dict:
    """Render the two reports as a Slack Block Kit message dict.

    Structure: a ``header`` (``DORA + retro — {repo}``), a ``section`` (mrkdwn)
    with the four DORA metrics and their bands, a ``section`` with the five
    retro signals referencing PRs as plain ``#<number>``, a ``divider``, and a
    ``context`` block naming repo / window / generated-at. Only standard core
    blocks are used. ``meta`` supplies ``repo``, ``window``, and
    ``generated_at`` — this function never calls ``datetime.now``.

    The result is a plain JSON-serializable dict and carries no author.
    """
    repo = meta.get("repo", dora_report.repo)

    if dora_report.merged_total == 0:
        dora_text = (
            "*DORA*\nNo merged PRs in the window — no DORA metrics to report."
        )
    else:
        dora_text = "*DORA*\n" + "\n".join(
            f"• {label}: {value}" for label, value in _dora_lines(dora_report)
        )

    has_signals = any(
        [
            retro_report.stale_open,
            retro_report.long_threads,
            retro_report.friction,
            retro_report.tech_debt,
            retro_report.smooth,
        ]
    )
    if not has_signals:
        retro_text = "*Retro signals*\nNo retro signals in the window."
    else:
        retro_text = "*Retro signals*\n" + "\n".join(
            f"• {label}: {value}" for label, value in _retro_lines(retro_report)
        )

    context_text = (
        f"repo: {repo}  |  window: {meta.get('window', 'all time')}  |  "
        f"generated: {meta.get('generated_at', '—')}"
    )

    return {
        "blocks": [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": f"DORA + retro — {repo}",
                },
            },
            {
                "type": "section",
                "text": {"type": "mrkdwn", "text": dora_text},
            },
            {
                "type": "section",
                "text": {"type": "mrkdwn", "text": retro_text},
            },
            {"type": "divider"},
            {
                "type": "context",
                "elements": [{"type": "mrkdwn", "text": context_text}],
            },
        ]
    }


# --- markdown ---------------------------------------------------------------


def build_markdown(
    dora_report: DoraReport, retro_report: RetroReport, meta: dict
) -> str:
    """Render the same team-level data as a human-readable markdown summary."""
    repo = meta.get("repo", dora_report.repo)
    window = meta.get("window", "all time")
    generated_at = meta.get("generated_at", "—")

    lines: list[str] = [f"# DORA + retro — {repo}", ""]

    lines.append("## DORA")
    if dora_report.merged_total == 0:
        lines.append("No merged PRs in the window — no DORA metrics to report.")
    else:
        for label, value in _dora_lines(dora_report):
            lines.append(f"- **{label}:** {value}")
    lines.append("")

    lines.append("## Retro signals")
    has_signals = any(
        [
            retro_report.stale_open,
            retro_report.long_threads,
            retro_report.friction,
            retro_report.tech_debt,
            retro_report.smooth,
        ]
    )
    if not has_signals:
        lines.append("No retro signals in the window.")
    else:
        for label, value in _retro_lines(retro_report):
            lines.append(f"- **{label}:** {value}")
    lines.append("")

    lines.append(f"_repo: {repo} | window: {window} | generated: {generated_at}_")
    return "\n".join(lines) + "\n"


# --- egress -----------------------------------------------------------------


def post_to_webhook(
    url: str, payload: dict, *, http_client: httpx.Client | None = None
) -> None:
    """POST ``payload`` as JSON to a Slack incoming webhook.

    ``http_client`` may be injected so tests exercise this path against a fake
    transport rather than a live channel. Raises :class:`DeliveryError` on any
    non-2xx response or transport error. The URL is never logged or echoed.
    """
    client = http_client or httpx.Client(timeout=DEFAULT_TIMEOUT)
    try:
        try:
            response = client.post(url, json=payload)
        except httpx.HTTPError as exc:
            raise DeliveryError(f"failed to POST to the Slack webhook: {exc}") from exc
        if not (200 <= response.status_code < 300):
            raise DeliveryError(
                f"Slack webhook returned {response.status_code}: "
                f"{response.text[:300]}"
            )
    finally:
        if http_client is None:
            client.close()


__all__ = [
    "DeliveryError",
    "build_blockkit",
    "build_markdown",
    "post_to_webhook",
]
