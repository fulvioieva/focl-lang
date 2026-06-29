---
description: Regenerate the compressed FOCL map for this project and report the token savings.
allowed-tools: Bash
---

Run `focl sync` in the project root to regenerate the `.focl` map from the
current sources. Then briefly report the token savings shown in the output
(source tokens → FOCL tokens, and the percentage saved).

If the command fails because no `.focl` exists yet, run `focl init .` instead.
