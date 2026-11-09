---
description: Refresh the compressed FOCL map — only the stale modules by default — and report what changed.
allowed-tools: Bash
---

Refresh the `.focl` map in the project root.

1. By default run `focl sync --changed`. It regenerates only the modules whose
   source changed, was deleted, or is new (one model call per changed file),
   leaving the rest of the map untouched. Report how many modules were
   regenerated, dropped, and left untouched.
2. If it reports **"Nothing to do"**, say the map is already up to date.
3. If it fails because the map **has no per-module hashes**, or the user asked
   for a **full** regeneration, run `focl sync` instead and report the token
   savings it prints (source tokens → FOCL tokens, percentage saved).
4. If no `.focl` exists yet, run `focl init .`.

To preview without calling the API, `focl sync --changed --dry-run` lists the
stale modules.
