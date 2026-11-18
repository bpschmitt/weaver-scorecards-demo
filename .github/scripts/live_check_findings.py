#!/usr/bin/env python3
"""Print Weaver live-check findings so they are visible in the Actions job.

    live_check_findings.py REPORT_DIR SERVICE FAIL_ON EXIT_CODE

Reads REPORT_DIR/live_check.json and writes:
  - a plain-text list to stdout (job log), violations first
  - Markdown to $GITHUB_STEP_SUMMARY
  - ::error / ::warning annotations for violations / improvements
Never fails the job: the Gate step owns pass/fail.
"""

from __future__ import annotations

import json
import os
import pathlib
import re
import sys
from collections import Counter

LEVELS = ("violation", "improvement", "information")
ANNOTATION = {"violation": "error", "improvement": "warning"}
MAX_ANNOTATIONS = 10  # GitHub shows only the first 10 per step


ANSI = re.compile(r"\x1b\[[0-9;]*m|\\u\{1b\}\[[0-9;]*m")


def label_for(kind: str, sample: dict) -> str:
    """Human name of the signal a finding belongs to."""
    if kind == "resource":
        for attr in sample.get("attributes") or []:
            if attr.get("name") == "service.name":
                return str(attr.get("value"))
        return "(resource)"
    if kind == "log":
        text = sample.get("event_name") or ANSI.sub("", str(sample.get("body") or ""))
        text = re.sub(r'^StringValue\("|"\)$', "", text).strip()
        return (text[:60] + "...") if len(text) > 60 else (text or "(log record)")
    return str(sample.get("name") or f"({kind})")


def walk_advice(node, kind="", label=""):
    """Yield (advice, kind, label) for every advice entry, with its parent signal."""
    if isinstance(node, dict):
        result = node.get("live_check_result")
        if isinstance(result, dict):
            for advice in result.get("all_advice") or []:
                yield advice, kind, label
        for key, value in node.items():
            if key == "span_events" and isinstance(value, list):
                for event in value:
                    yield from walk_advice(event, "span_event", f"{label} > {event.get('name')}")
            else:
                yield from walk_advice(value, kind, label)
    elif isinstance(node, list):
        for item in node:
            yield from walk_advice(item, kind, label)


def walk_samples(samples):
    """Top-level samples are single-key dicts: {"metric": {...}}, {"span": {...}}, ..."""
    for sample in samples:
        for kind, body in sample.items():
            if isinstance(body, dict):
                yield from walk_advice(body, kind, label_for(kind, body))


def escape(text: str) -> str:
    """Escape a value for a GitHub workflow command."""
    return text.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")


def md(text: str) -> str:
    return str(text).replace("|", "\\|").replace("\n", " ")


def main() -> None:
    report_dir, service, fail_on, exit_code = sys.argv[1:5]
    report = pathlib.Path(report_dir) / "live_check.json"
    summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
    out: list[str] = [f"### Live-check: {service} (fail_on={fail_on}, exit code {exit_code})", ""]

    if not report.is_file():
        out.append(f"No report found at `{report}`. See the live-check log artifact.")
        print("\n".join(out))
        if summary_path:
            pathlib.Path(summary_path).open("a").write("\n".join(out) + "\n")
        return

    data = json.loads(report.read_text())
    # (level, id, message, where) -> count; `where` = "<signal kind> <signal name>"
    counts: Counter = Counter()
    for advice, kind, label in walk_samples(data.get("samples", [])):
        where = f"{kind} {label}".strip()
        counts[(advice.get("level", "information"), advice.get("id", "?"),
                advice.get("message", ""), where)] += 1

    by_level = Counter()
    for (level, *_), n in counts.items():
        by_level[level] += n
    out.append("Findings: " + ", ".join(f"{by_level[lv]} {lv}" for lv in LEVELS))
    out.append("")

    def rows_for(level):
        return sorted(((k, n) for k, n in counts.items() if k[0] == level),
                      key=lambda kn: (kn[0][1], kn[0][2], kn[0][3]))

    # information is noise: counted above, not listed.
    for level in LEVELS[:2]:
        rows = rows_for(level)
        if not rows:
            continue
        out += [f"#### {level.capitalize()} ({len(rows)} distinct, {by_level[level]} total)", "",
                "| Advice | Where | Weaver says | Seen |", "| --- | --- | --- | --- |"]
        out += [f"| `{advice_id}` | `{md(where)}` | {md(message)} | {n}x |"
                for (_, advice_id, message, where), n in rows]
        out.append("")
    if by_level["violation"] == by_level["improvement"] == 0:
        out.append("No violations or improvements. Weaver has no suggestions.")

    # Job log: plain text, violations first, with annotations.
    annotations = 0
    for level in LEVELS[:2]:
        rows = rows_for(level)
        if rows:
            print(f"== {level.upper()} ({by_level[level]}) ==")
        for (lv, advice_id, message, where), n in rows:
            print(f"[{lv}] {advice_id} in {where} ({n}x): {message}")
            if annotations < MAX_ANNOTATIONS:
                print(f"::{ANNOTATION[lv]} title=Weaver {lv}: {escape(advice_id)} "
                      f"({escape(service)})::{escape(message)} [{escape(where)}]")
                annotations += 1
    if by_level["violation"] == by_level["improvement"] == 0:
        print("No violations or improvements.")

    if summary_path:
        with pathlib.Path(summary_path).open("a") as fh:
            fh.write("\n".join(out) + "\n")


if __name__ == "__main__":
    main()
