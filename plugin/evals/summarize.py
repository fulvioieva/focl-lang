"""Per-arm summary of a `claude plugin eval` run of the FOCL plugin.

The built-in report shows the score delta (WITH vs W/OUT) but only one COST
column per case. FOCL's claim is "same answers for fewer tokens", so this
splits cost, turns and duration by arm:

    python plugin/evals/summarize.py plugin/evals/results/<timestamp>/aggregate-result.json

(or pass the file written by `--json <path>`). Costs are the eval's list-price
estimate of the agent runs, excluding judge calls; they are not plan usage.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from statistics import mean


def _arm_stats(runs: list[dict]) -> dict:
    ok = [r for r in runs if not r.get("error")]
    pick = ok or runs
    return {
        "runs": len(runs),
        "errors": len(runs) - len(ok),
        "score": mean(r.get("score") or 0 for r in pick) if pick else 0.0,
        "cost": mean(r.get("costUsd") or 0 for r in pick) if pick else 0.0,
        "turns": mean(r.get("turns") or 0 for r in pick) if pick else 0.0,
        "seconds": mean(r.get("durationSeconds") or 0 for r in pick) if pick else 0.0,
    }


def _pct(new: float, old: float) -> str:
    return "  n/a" if not old else f"{(new - old) / old * 100:+5.0f}%"


def summarize(result: dict) -> str:
    header = (f"{'CASE':<18}{'ARM':<8}{'SCORE':>6}{'COST $':>9}{'TURNS':>7}{'SECS':>6}"
              f"{'ERR':>5}")
    lines = [header, "-" * len(header)]
    totals = {"with": [], "without": []}
    for case in result.get("cases", []):
        arms = case.get("arms", {})
        stats = {arm: _arm_stats(arms.get(arm, [])) for arm in ("with", "without")}
        for arm in ("with", "without"):
            s = stats[arm]
            if not s["runs"]:
                continue
            totals[arm].append(s)
            lines.append(f"{case.get('name', '?'):<18}{arm:<8}{s['score']:>6.2f}"
                         f"{s['cost']:>9.4f}{s['turns']:>7.1f}{s['seconds']:>6.0f}"
                         f"{s['errors']:>5}")
        w, wo = stats["with"], stats["without"]
        if w["runs"] and wo["runs"]:
            lines.append(f"{'':<18}{'delta':<8}{w['score'] - wo['score']:>+6.2f}"
                         f"{_pct(w['cost'], wo['cost']):>9}{_pct(w['turns'], wo['turns']):>7}"
                         f"{_pct(w['seconds'], wo['seconds']):>6}")
        lines.append("")

    if totals["with"] and totals["without"]:
        def avg(arm: str, key: str) -> float:
            return mean(s[key] for s in totals[arm])

        lines.append(
            "OVERALL  score with/without: "
            f"{avg('with', 'score'):.2f} / {avg('without', 'score'):.2f}   "
            f"cost per run: ${avg('with', 'cost'):.4f} vs ${avg('without', 'cost'):.4f} "
            f"({_pct(avg('with', 'cost'), avg('without', 'cost')).strip()})   "
            f"turns: {avg('with', 'turns'):.1f} vs {avg('without', 'turns'):.1f}"
        )
    lines.append(f"Total eval cost (incl. judge): ${result.get('costUsd') or 0:.2f}  "
                 f"claude {result.get('claudeVersion', '?')}")
    return "\n".join(lines)


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print(__doc__.strip().splitlines()[0])
        print("usage: python summarize.py <aggregate-result.json>")
        return 2
    result = json.loads(Path(argv[1]).read_text(encoding="utf-8"))
    print(summarize(result))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
