# FOCL — Code Review: Correzioni Effettuate e In Sospeso

**Data review iniziale:** Aprile 2026
**Versione codice esaminata:** 0.1.0
**Revisore:** Claude (Anthropic) / Fulvio Ieva — TWINAXIS Consulting

---

## Indice

- [Riepilogo stato](#riepilogo-stato)
- [Correzioni effettuate](#correzioni-effettuate)
- [Correzioni in sospeso](#correzioni-in-sospeso)
- [File modificati per sessione](#file-modificati-per-sessione)

---

## Riepilogo stato

| # | Descrizione | Priorità | Stato |
|---|---|---|---|
| 1 | `pyproject.toml` — build-backend errato | 🔴 Critica | ✅ Done |
| 2 | Model ID e parametro `thinking` da verificare | 🔴 Critica | ✅ Done |
| 3 | Watcher — loop infinito su file `.focl` | 🔴 Critica | ✅ Done |
| 4 | Nessuna gestione della context window | 🔴 Critica | ✅ Done |
| 5 | `update()` non fa patch chirurgiche | 🟡 Importante | ⏳ Aperta |
| 6 | Nessun mapping file-sorgente → blocco FOCL | 🟡 Importante | 🔶 Parziale |
| 7 | Watcher può triggerare su `.focl` in loop | 🔴 Critica | ✅ Done (vedi #3) |
| 8 | File skippati per `_MAX_FILE_BYTES` silenzioso | 🟡 Importante | ✅ Done |
| 9 | Nessun test — zero coverage | 🟡 Importante | ✅ Done |
| 10 | Token saving calcolato in byte, non in token | 🟡 Importante | ✅ Done |
| 11 | System prompt hardcoded in `generator.py` | 🟢 Minore | ⏳ Aperta |
| 12 | Nessun comando `focl validate` | 🟢 Minore | ⏳ Aperta |
| 13 | Nessun comando `focl decompile` | 🟢 Minore | ⏳ Aperta |

**Totale: 8 chiuse, 5 aperte (di cui 1 parziale)**

---

## Correzioni effettuate

---

### ✅ #1 — `pyproject.toml`: build-backend errato

**File:** `pyproject.toml`
**Problema:** Il campo `build-backend` puntava a `"setuptools.backends.legacy:build"` che non esiste. `pip install -e .` falliva con un errore di importazione.

**Fix:**
```toml
# Prima (errato)
build-backend = "setuptools.backends.legacy:build"

# Dopo (corretto)
build-backend = "setuptools.build_meta"
```

**Aggiunte contestuali:** `license`, `authors`, `keywords`, `classifiers`, `[project.urls]`, `[project.optional-dependencies] dev` con `pytest`/`ruff`, `[tool.ruff]`.

---

### ✅ #2 — Model ID e parametro `thinking`

**File:** `focl/generator.py`
**Problema:** Dubbio sulla validità di `_MODEL = "claude-opus-4-7"` e del parametro `thinking={"type": "adaptive"}`.

**Risultato dopo verifica:** entrambi sono corretti.
- Il model ID `claude-opus-4-7` è valido per Claude Opus 4.7 (GA dal 16 aprile 2026).
- `{"type": "adaptive"}` è il parametro corretto per il nuovo adaptive thinking di Opus 4.7, che sostituisce il deprecato `budget_tokens`.
- Rimosso l'import unused `Shard` rilevato da ruff (F401).

**Nota:** Opus 4.7 non supporta più `temperature`, `top_p`, `top_k` — il codice non li usa, quindi nessun intervento necessario.

---

### ✅ #3 — Watcher: loop infinito su file `.focl`

**File:** `focl/watcher.py`
**Problema:** Il watcher monitorava tutta la directory root inclusi i file `.focl`. Ogni volta che `focl watch` aggiornava il file `.focl`, Watchdog rilevava la modifica e scatenava un nuovo aggiornamento — loop infinito.

**Fix:** Aggiunto `_SELF_EXTENSIONS = {".focl"}` e filtro esplicito in `_Handler._enqueue()`:
```python
_SELF_EXTENSIONS = {".focl"}

def _enqueue(self, event):
    ...
    if suffix in _SELF_EXTENSIONS:
        return  # never rebuild when .focl itself changes
```

**Aggiunte contestuali:** gestione `on_moved()` per rename/refactoring, ottimizzazione ordine dei check (suffisso prima, parts dopo).

---

### ✅ #4 — Nessuna gestione della context window

**File:** `focl/sharder.py` (nuovo), `focl/generator.py` (aggiornato), `focl/cli.py` (aggiornato)
**Problema:** `build_context()` concatenava tutti i file in un'unica stringa e la inviava in un singolo messaggio API. Su progetti medio-grandi il limite di token veniva superato, causando errori o output degradato.

**Fix — strategia "shard + merge" in due fasi:**

1. **Nuovo modulo `focl/sharder.py`:**
   - `shard_project()` — raggruppa file per directory top-level e applica bin-packing first-fit decreasing rispettando un budget di token per shard (default 80K)
   - `count_tokens()` — usa `client.messages.count_tokens()` per conteggi esatti, con fallback a stima offline (3 chars/token)
   - File che superano il budget da soli → shard singoli con label `:oversize`
   - `build_shard_context()` — costruisce il testo da inviare per ogni shard

2. **`focl/generator.py` aggiornato:**
   - Sotto 60K token stimati → single-call (comportamento precedente)
   - Sopra 60K → compressione shard-by-shard con merge finale
   - Header nel `.focl` con metadata del progetto e separatori per shard
   - System prompt aggiornato: ogni blocco annotato con `# src: path/to/file` per abilitare patch future

3. **`focl/cli.py` aggiornato:**
   - Nuove opzioni `--shard-budget N` e `--exact-tokens` su `init` e `sync`
   - Progress callback in tempo reale (es. "Shard 3/8 [services] — 5 files, 7,401 est. tokens")
   - **Nuovo comando `focl plan`** — anteprima del piano di sharding senza chiamate API

---

### ✅ #8 — File skippati per `_MAX_FILE_BYTES` silenzioso

**File:** `focl/analyzer.py`, `focl/cli.py`
**Problema:** File superiori a 200KB venivano scartati silenziosamente da `_collect_files()`. L'utente non aveva modo di sapere che parte del codebase era stata ignorata.

**Fix in `analyzer.py`:**
- `ProjectInfo` ora ha un campo `skipped_files: list[tuple[Path, str]]`
- `_collect_files()` restituisce `(files, skipped)` invece di solo `files`
- Il motivo dello skip include dimensione in KB: `"exceeds 200 KB limit (312 KB)"`

**Fix in `cli.py`:**
```
FOCL analysing /path/to/project
  Language: java / spring-boot
  Files:    47
  Size:     380 KB
  Skipped:  2 file(s) too large to process:
    • services/GeneratedCode.java — exceeds 200 KB limit (312 KB)
    • legacy/OldService.java — exceeds 200 KB limit (218 KB)
```

---

### ✅ #9 — Nessun test

**File nuovi:** `tests/__init__.py`, `tests/conftest.py`, `tests/test_analyzer.py`, `tests/test_sharder.py`, `tests/test_metrics.py`, `tests/test_watcher.py`, `tests/test_cli.py`
**File nuovo:** `.github/workflows/ci.yml`

**Copertura della suite (52 test, 0 fallimenti):**

| Modulo | Test | Cosa copre |
|---|---|---|
| `test_analyzer.py` | 16 | Language detection, file collection, filtri, `skipped_files`, `build_context` |
| `test_sharder.py` | 13 | Token estimation, bin-packing, rispetto del budget, oversize a due livelli, `build_shard_context` |
| `test_metrics.py` | 8 | Properties di `CompressionMetrics`, `measure()`, `measure_from_paths()`, edge cases zero |
| `test_watcher.py` | 9 | Filtro `.focl`, binari, `node_modules`, `.venv`, directory, debounce coalescing |
| `test_cli.py` | 6 | `--help`, `--version`, `plan`, `stats` con e senza `.focl` |

**GitHub Actions CI (`.github/workflows/ci.yml`):**
- Matrice: Python 3.10 / 3.11 / 3.12 × Ubuntu / macOS / Windows (9 job)
- Job separato per `ruff check`
- Trigger: push su `main`/`dev`, PR verso `main`

**Bug scoperti dai test e corretti:**
- Spring Boot detection: il codice cercava `"spring-boot"` col trattino, documentato e testato esplicitamente
- `node_modules` false positive: i test usavano path assoluti che contenevano `"node_modules"` nel nome del dir pytest — corretti con path relativi
- Oversize a due livelli: chiarita la distinzione tra skip a livello analyzer (>200KB, ora in `skipped_files`) e oversize a livello sharder (<200KB ma >budget shard, ora in `ShardingResult.oversize_files`)

---

### ✅ #10 — Token saving calcolato in byte, non in token

**File nuovo:** `focl/metrics.py`
**File aggiornato:** `focl/cli.py`
**Problema:** Il report finale calcolava `saving = 1 - focl_kb / orig_kb` — un risparmio in byte. Inconsistente con il whitepaper che dichiara risparmi in token.

**Fix — nuovo modulo `focl/metrics.py`:**
- `CompressionMetrics` — dataclass con proprietà per entrambe le metriche (token e byte)
- `measure()` — misura da `ProjectInfo` + stringa FOCL
- `measure_from_paths()` — convenience wrapper da file su disco
- Modalità `exact=True` usa `count_tokens()` API, `exact=False` usa stima offline

**Output aggiornato di `focl init`:**
```
Done — myproject.focl written in 24.3s
  Source tokens:       2,187  (estimated)
  FOCL tokens:           374  (estimated)
  Token ratio:           5.9x
  Token saving:         82.9%
  (Bytes: 38 KB → 7 KB = 83% smaller)
```

**`focl stats` aggiornato** mostra token source/FOCL, ratio e saving in token. Flag `--exact-tokens` disponibile per conteggio via API.

---

## Correzioni in sospeso

---

### ⏳ #5 — `update()` non fa patch chirurgiche

**File:** `focl/generator.py`
**Problema:** La funzione `update()` (usata da `focl watch`) invia a Claude l'intero file `.focl` esistente più i file sorgente cambiati, e chiede di restituire l'intero `.focl` aggiornato. Su file `.focl` grandi:
- Costo alto: si paga la lettura di tutto il `.focl` anche per una modifica piccola
- Rischio drift: il modello può modificare blocchi non richiesti

**Soluzione proposta:**
1. Ogni blocco FOCL ha già `# src: path/to/File.java` grazie all'aggiornamento del system prompt (punto 4)
2. Estrarre i blocchi corrispondenti ai file cambiati tramite parsing del `# src:` header
3. Inviare a Claude solo quei blocchi + i file sorgente modificati
4. Sostituire chirurgicamente i blocchi nel `.focl` completo

**Stima effort:** 4-6 ore. Dipende da #6.

---

### 🔶 #6 — Mapping file-sorgente → blocco FOCL (parziale)

**File:** `focl/generator.py`
**Stato:** Il system prompt ora istruisce il modello ad aggiungere `# src: path/to/File.java` all'inizio di ogni blocco FOCL. Questo è il prerequisito.

**Mancante:** Un parser che legga il `.focl` e costruisca il mapping `{path: blocco}` per abilitare le patch chirurgiche di #5.

**Soluzione proposta:**
```python
def parse_focl_blocks(focl_content: str) -> dict[str, str]:
    """Return {relative_path: block_text} from a .focl file."""
    ...
```

**Stima effort:** 2-3 ore.

---

### ⏳ #11 — System prompt hardcoded in `generator.py`

**File:** `focl/generator.py`
**Problema:** Il system prompt è una stringa letterale nel codice Python. Per iterare sulla grammatica FOCL o per permettere a contributor di proporre varianti, sarebbe meglio averlo in un file separato.

**Soluzione proposta:**
```
focl/prompts/
  generate.md    ← system prompt principale
  update.md      ← system prompt per patch incrementali
```

Caricati con `importlib.resources` per funzionare anche dopo `pip install`.

**Stima effort:** 1-2 ore.

---

### ⏳ #12 — Nessun comando `focl validate`

**File:** `focl/cli.py` (nuovo comando), `focl/validator.py` (nuovo modulo)
**Problema:** Non esiste modo di verificare che un file `.focl` sia ben formato. Utile per CI, per contributor che scrivono FOCL a mano, e per verificare che `focl decompile` produca output valido.

**Soluzione proposta:**
```bash
focl validate myproject.focl
```

Controlla:
- Tutti i blocchi top-level sono tipi riconosciuti (`SERVICE`, `ENTITY`, `CONFIG`, ...)
- Ogni blocco ha l'annotazione `# src:`
- Le primitive usate sono nel set noto (`OWNED_FETCH`, `TRANSITION`, ...)
- Nessun blocco è vuoto
- Il file non contiene markdown o backtick (output non-FOCL)

**Stima effort:** 3-4 ore.

---

### ⏳ #13 — Nessun comando `focl decompile`

**File:** `focl/cli.py` (nuovo comando), `focl/decompiler.py` (nuovo modulo)
**Problema:** FOCL dichiara di essere una compressione lossless, ma non esiste strumento per dimostrarlo. `focl decompile` è la prova definitiva della tesi del progetto.

**Soluzione proposta:**
```bash
focl decompile myproject.focl --lang java --output ./reconstructed/
```

Il modello riceve il `.focl` e ricostruisce il codice sorgente nel linguaggio originale. La qualità si misura:
- Compilazione del codice ricostruito
- Esecuzione dei test del progetto originale sul codice ricostruito
- Confronto token count: sorgente originale vs ricostruito

**Stima effort:** 1 giornata. È anche il benchmark definitivo per il whitepaper.

---

## File modificati per sessione

### Sessione 1 — Fix critici (punti 1, 3)
| File | Tipo | Modifica |
|---|---|---|
| `pyproject.toml` | Fix | build-backend corretto + metadati PyPI |
| `focl/watcher.py` | Fix | Filtro `.focl` + `on_moved()` |

### Sessione 2 — Context window (punto 4)
| File | Tipo | Modifica |
|---|---|---|
| `focl/sharder.py` | Nuovo | Modulo sharding completo |
| `focl/generator.py` | Aggiornato | Strategia single-call vs sharded |
| `focl/cli.py` | Aggiornato | `--shard-budget`, `--exact-tokens`, comando `focl plan` |

### Sessione 3 — Metriche e test (punti 8, 9, 10)
| File | Tipo | Modifica |
|---|---|---|
| `focl/metrics.py` | Nuovo | Metriche token-accurate |
| `focl/analyzer.py` | Aggiornato | `skipped_files` tracking |
| `focl/cli.py` | Aggiornato | Warning file skippati, report in token |
| `focl/generator.py` | Aggiornato | Import unused rimosso (ruff) |
| `tests/__init__.py` | Nuovo | Package marker |
| `tests/conftest.py` | Nuovo | Fixture condivise (4 fixture) |
| `tests/test_analyzer.py` | Nuovo | 16 test su analyzer |
| `tests/test_sharder.py` | Nuovo | 13 test su sharder |
| `tests/test_metrics.py` | Nuovo | 8 test su metrics |
| `tests/test_watcher.py` | Nuovo | 9 test su watcher |
| `tests/test_cli.py` | Nuovo | 6 smoke test su CLI |
| `.github/workflows/ci.yml` | Nuovo | CI matrix 3×3 + ruff |

---

*Documento generato automaticamente — aggiornare ad ogni sessione di review.*
