# FOCL plugin evals

Does reading a codebase through the FOCL map actually help Claude? This suite
answers it with `claude plugin eval`: every case runs **with** the plugin (MCP
tools, skill, `focl-explorer` subagent) and **without** it (plain
`Read`/`Grep`/`Glob` on the sources), and compares answer quality and cost.

## Layout

| Path | What |
|---|---|
| `fixtures/shop/` | A small fictional shop backend (10 files, ~8 KB) plus its pre-generated, hash-stamped `shop.focl`. |
| `_scaffold/copy-shop.sh` | Copies the fixture into each run's empty workspace (each case's `scaffold.sh` execs it). |
| `<case>/case.yaml` | Prompt, limits and graders. |
| `summarize.py` | Splits cost / turns / duration **per arm** — the built-in report has one COST column per case. |

| Case | Question type | Graders |
|---|---|---|
| `ownership-check` | "Where is X enforced?" — one module | regex (file, error code) + LLM (no-leak semantics) |
| `cancel-rules` | Business rule + side effects over 3 modules | LLM ×2 |
| `support-refund` | Authorization interaction across 2 modules (support role still hits the owner check) | LLM + regex |
| `integrations` | Architecture overview: every external system and its config | LLM ×2 + regex |

Each case also has `used-focl-map` (`arm: with-only`, not scored): did the
with-plugin run call any `mcp__plugin_focl_focl__*` tool?

## Running

Needs the `focl` CLI with the MCP extra (`pip install -e ".[mcp]"`) — the
plugin's **real** `focl mcp` server answers the tool calls, over the real map.

```bash
cd plugin
claude plugin eval . --model sonnet --scaffold --trust-plugin \
  --allow-real-servers --allow-tools "mcp__plugin_focl_focl__*" \
  --max-cost-usd 4 -j 4 --no-publish --threshold 0
python evals/summarize.py evals/results/<timestamp>/aggregate-result.json
```

`--scaffold` runs the case scripts (they only copy the fixture);
`--allow-real-servers` starts `focl mcp` as you, outside the eval sandbox.
4 cases × 3 runs × 2 arms ≈ **$1** at list price with Sonnet.

Regenerate the fixture map after editing the fixture (the hashes must match):
`cd fixtures/shop && focl sync . --provider claude-code` (or any provider).

## First results (2026-11-09, Sonnet, claude 2.1.319)

```
CASE              ARM      SCORE   COST $  TURNS
cancel-rules      with      1.00   0.0405    3.0
cancel-rules      without   1.00   0.0376    3.0
integrations      with      1.00   0.0481    5.0
integrations      without   1.00   0.0497    5.7
ownership-check   with      1.00   0.0445    5.0
ownership-check   without   1.00   0.0453    5.0
support-refund    with      1.00   0.0448    4.7
support-refund    without   1.00   0.0396    3.3

OVERALL  score 1.00 / 1.00   cost per run $0.0445 vs $0.0430 (+3%)   turns 4.4 vs 4.2
```

What this says — and doesn't:

- **Quality is unchanged** (1.00 in both arms): the map didn't make answers
  worse, including the cross-module `support-refund` reasoning.
- **No saving at this size.** On an ~8 KB project reading the sources is
  already cheap, and the plugin adds fixed overhead (skill + tool
  descriptions). The map's case is large codebases, which this fixture does
  not represent — a bigger fixture is the next step.
- **The skill doesn't always fire.** In `integrations` the with-plugin runs
  never used the map (`used-focl-map` failed 3/3): Claude went straight to
  Grep/Read. In eval runs there is no `CLAUDE.md` pointer (project config is
  never loaded), so the skill description is the only nudge.
- **Baseline caveat:** the scaffold can't tell which arm it runs in, so
  `shop.focl` is in the no-plugin workspace too. In the traces inspected the
  baseline never read it, but a run that does would blur the comparison.
