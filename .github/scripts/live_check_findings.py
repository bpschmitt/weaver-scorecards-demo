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
import sys
from collections import Counter

LEVELS = ("violation", "improvement", "information")
ANNOTATION = {"violation": "error", "improvement": "warning"}
MAX_ANNOTATIONS = 10  # GitHub shows only the first 10 per step


def walk_advice(node):
    """Yield (advice, sample_name) for every advice entry in the report."""
    if isinstance(node, dict):
        result = node.get("live_check_result")
        if isinstance(result, dict):
            name = node.get("name") or node.get("metric_name") or node.get("event_name")
            for advice in result.get("all_advice") or []:
                yield advice, name
        for value in node.values():
            yield from walk_advice(value)
    elif isinstance(node, list):
        for item in node:
            yield from walk_advice(item)


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
    # (level, id, message, signal_type) -> count and example sample names
    counts: Counter = Counter()
    samples: dict[tuple, set] = {}
    for advice, name in walk_advice(data.get("samples", [])):
        key = (advice.get("level", "information"), advice.get("id", "?"),
               advice.get("message", ""), advice.get("signal_type") or "")
        counts[key] += 1
        if name:
            samples.setdefault(key, set()).add(name)

    by_level = Counter()
    for (level, *_), n in counts.items():
        by_level[level] += n
    out.append("Findings: " + ", ".join(f"{by_level[lv]} {lv}" for lv in LEVELS))
    out.append("")

    def rows_for(level):
        return sorted(((k, n) for k, n in counts.items() if k[0] == level),
                      key=lambda kn: (kn[0][1], kn[0][2]))

    # information is noise: counted above, not listed.
    for level in LEVELS[:2]:
        rows = rows_for(level)
        if not rows:
            continue
        out += [f"#### {level.capitalize()} ({len(rows)} distinct, {by_level[level]} total)", "",
                "| Advice | Signal | Weaver says | Seen |", "| --- | --- | --- | --- |"]
        out += [f"| `{advice_id}` | {md(signal)} | {md(message)} | {n}x |"
                for (_, advice_id, message, signal), n in rows]
        out.append("")
    if by_level["violation"] == by_level["improvement"] == 0:
        out.append("No violations or improvements. Weaver has no suggestions.")

    # Job log: plain text, violations first, with annotations.
    annotations = 0
    for level in LEVELS[:2]:
        rows = rows_for(level)
        if rows:
            print(f"== {level.upper()} ({by_level[level]}) ==")
        for (lv, advice_id, message, signal), n in rows:
            print(f"[{lv}] {advice_id} ({signal or 'n/a'}, {n}x): {message}")
            if annotations < MAX_ANNOTATIONS:
                print(f"::{ANNOTATION[lv]} title=Weaver {lv}: {escape(advice_id)} "
                      f"({escape(service)})::{escape(message)}")
                annotations += 1
    if by_level["violation"] == by_level["improvement"] == 0:
        print("No violations or improvements.")

    if summary_path:
        with pathlib.Path(summary_path).open("a") as fh:
            fh.write("\n".join(out) + "\n")


if __name__ == "__main__":
    main()
