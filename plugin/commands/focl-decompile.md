---
description: Reconstruct source code from the FOCL map (round-trip) into a directory.
allowed-tools: Bash
---

Reconstruct the original source from the compressed FOCL map by running
`focl decompile .` in the project root (output goes to `./<project>-decompiled/`).

If the user named a target directory or language, pass `--output <dir>` and/or
`--lang <language>`. After it finishes, report how many files were written and
where.
