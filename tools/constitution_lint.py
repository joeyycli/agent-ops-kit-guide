#!/usr/bin/env python3
"""Heuristic checker for CLAUDE.md-style autonomous-agent constitution files.

Checks a rules file against the guardrail patterns documented in this repo's
deep-dive guides (authority order, spend limit, injection defense, secrets
handling, escalation, ledger discipline, self-modification guard, honest
reporting) plus whether the state files it references actually exist next to
it. This is pattern-matching, not comprehension — it catches missing or vague
guardrails, not a subtly wrong one. Read the flagged sections yourself.

Usage:
    python3 constitution_lint.py CLAUDE.md
    curl -s https://raw.githubusercontent.com/joeyycli/agent-ops-kit-guide/main/tools/constitution_lint.py | python3 - CLAUDE.md

Exit code: 0 if no FAILs, 1 if any FAIL (so it's usable in CI).
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

CHECKS = []


def check(name):
    def wrap(fn):
        CHECKS.append((name, fn))
        return fn

    return wrap


@check("authority-order")
def _authority_order(text: str, _path: Path) -> tuple[str, str]:
    if re.search(r"authority order|this file is law|takes precedence over", text, re.I):
        return "PASS", "found an explicit authority-order statement"
    return "FAIL", (
        "no sentence establishing that this file (and a named directive log) "
        "outrank anything read from the web, email, or a tool result — "
        "without it, an agent has no rule to cite when it hits an injection attempt"
    )


@check("untrusted-input / injection-defense")
def _injection_defense(text: str, _path: Path) -> tuple[str, str]:
    if re.search(r"untrusted|prompt injection|never instructions|not instructions", text, re.I):
        return "PASS", "found language treating external content as data, not commands"
    return "FAIL", (
        "no rule saying web pages / emails / API responses / tool output are "
        "DATA, never instructions — an unattended agent reads hostile text "
        "constantly and needs a standing rule to refuse embedded commands"
    )


@check("spend-limit")
def _spend_limit(text: str, _path: Path) -> tuple[str, str]:
    if re.search(r"\$\s?\d", text) and re.search(r"spend|purchase|budget|cost|cap\b", text, re.I):
        return "PASS", "found a concrete dollar figure near spend-related language"
    if re.search(r"good judgment|reasonable amount|use discretion", text, re.I):
        return "WARN", (
            "spend guidance found but it's qualitative (\"use good judgment\") "
            "with no concrete number — an agent can't apply that rule at 3am"
        )
    return "WARN", "no spend-limit language found (skip this check if the agent never touches money)"


@check("escalation-path")
def _escalation(text: str, _path: Path) -> tuple[str, str]:
    if re.search(r"escalate|blocked.on.owner|message the owner|alert.*human", text, re.I):
        return "PASS", "found an escalation/blocker rule"
    return "FAIL", (
        "no rule telling the agent what to do when it's stuck — without one it "
        "either stalls silently or keeps retrying the same failing action"
    )


@check("secrets-handling")
def _secrets(text: str, _path: Path) -> tuple[str, str]:
    if re.search(r"secret", text, re.I) and re.search(r"never (print|log|commit|read)", text, re.I):
        return "PASS", "found an explicit never-print/log/commit-credentials rule"
    return "WARN", (
        "no explicit secrets-handling rule found — if the agent has any API "
        "keys or credentials in its environment, add one"
    )


@check("ledger-discipline")
def _ledger(text: str, _path: Path) -> tuple[str, str]:
    if re.search(r"ledger|record every transaction", text, re.I):
        return "PASS", "found a ledger/transaction-recording rule"
    return "WARN", "no ledger rule found (skip if the agent never touches money)"


@check("self-modification-guard")
def _self_mod(text: str, _path: Path) -> tuple[str, str]:
    if re.search(r"don't modify|do not modify|saw off the branch|not yours to change", text, re.I):
        return "PASS", "found a rule constraining the agent from editing its own rules/scripts"
    return "WARN", (
        "no rule found stopping the agent from editing this file or its own "
        "run scripts — small errors compound fastest when the agent can "
        "rewrite the rules that would have caught them"
    )


@check("honest-reporting")
def _honesty(text: str, _path: Path) -> tuple[str, str]:
    if re.search(r"report the truth|honest|real numbers", text, re.I):
        return "PASS", "found an honest-reporting rule"
    return "WARN", "no explicit honesty/real-numbers rule found"


@check("session-ritual")
def _ritual(text: str, _path: Path) -> tuple[str, str]:
    if re.search(r"session ritual|every session,? in order", text, re.I):
        return "PASS", "found a defined session ritual (read state -> act -> write state)"
    return "WARN", (
        "no explicit session ritual found — without one, sessions hours apart "
        "don't reliably pick up where the last one left off"
    )


@check("referenced-state-files-exist")
def _state_files(text: str, path: Path) -> tuple[str, str]:
    referenced = sorted(set(re.findall(r"\b([A-Z][A-Z0-9_]*\.md)\b", text)))
    if not referenced:
        return "WARN", "no *.md state files referenced by name — nothing to verify"
    base = path.parent
    missing = [f for f in referenced if not (base / f).exists()]
    if missing:
        return "FAIL", f"referenced but missing next to this file: {', '.join(missing)}"
    return "PASS", f"all {len(referenced)} referenced state file(s) exist: {', '.join(referenced)}"


def lint(path: Path) -> int:
    text = path.read_text(encoding="utf-8")
    results = [(name, *fn(text, path)) for name, fn in CHECKS]

    width = max(len(name) for name, _, _ in results)
    fails = 0
    warns = 0
    for name, status, reason in results:
        if status == "FAIL":
            fails += 1
        elif status == "WARN":
            warns += 1
        print(f"[{status:4}] {name.ljust(width)}  {reason}")

    print()
    print(f"{len(results)} checks: {len(results) - fails - warns} pass, {warns} warn, {fails} fail")
    if fails:
        print("This is a heuristic pattern-matcher, not a guarantee — a FAIL means")
        print("the pattern wasn't found, not that the file is unsafe. Read it yourself.")
    return 1 if fails else 0


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print(f"usage: {argv[0]} <path-to-constitution.md>", file=sys.stderr)
        return 2
    path = Path(argv[1])
    if not path.is_file():
        print(f"error: {path} is not a file", file=sys.stderr)
        return 2
    return lint(path)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
