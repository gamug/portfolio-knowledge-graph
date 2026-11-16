# Agent traceability — block F design (Work item 46, T-900–T-909)

Status: design + implementation for the final delivery `2026-11-17_final`,
configuration `SYSTEM_WITH_HIERARCHY`. This note is the contract for
`src/projection/agents.py` and `cli/load_agents.py`; it supersedes section 7 of
`docs/veto-hierarchy-design.md` for the final delivery. Every deviation from that
section is listed in §9.

## 1. What block F loads

Four independent sources per window, all read-only and never copied:

| Manifest key | File | Shape | Rows in the delivery |
|---|---|---|---|
| `manager_calls_file` | `H1B-A2g-<window>.manager_calls.jsonl` | one A2g call per line | 308 |
| `narrator_file` | `H1B-A2g-<window>.narrator.jsonl` | one text per line | 3,246 |
| `news_actions_file` | `H1B-A2g-<window>.news.json` | one object: actions, dates, fills, levels_v2 | 252 actions, 119 dates |
| `bull_mode_file` | `H1B-A2g-<window>.bull_mode.json` | one object: N11 decisions | 119 decisions |

Windows: `P1, H1, P3, H2, P2, H3, C1`. The loader resolves the paths from
`manifest_final.json` itself (it does not use the shared manifest parser while
PR B is open) and verifies every file twice: against the run's
`files_sha256[key]` and against the delivery root's `SHA256SUMS`. A mismatch is
a hard failure.

The delivery root defaults to
`/workspaces/thesis/knoledge graph/2026-11-17_final` through `KG_DELIVERY_DIR`;
`--dir` overrides it. `--label` is always `final` in the delivery.

## 2. Per-window control counts (manifest and file)

These are the manifest's `control_counts.SYSTEM_WITH_HIERARCHY` values and the
definitions the loader implements. `file` means the loader derives the value
from the four block-F files; `detail` means the value is derived from the
run's `<window>.cartera_v1_3.kg.jsonl` only as a manifest cross-check (block F
does not project that file).

| Window | calls | fallback | repair | narrator | veto | promotion | dates | level C | level D | exits | sector rej. | bull trig. |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| P1 | 4 | 0 | 0 | 253 | 18 | 7 | 10 | 3 | 7 | 2 | 853 | 0 |
| H1 | 57 | 0 | 4 | 268 | 15 | 5 | 13 | 2 | 1 | 0 | 853 | 5 |
| P3 | 15 | 0 | 1 | 131 | 14 | 11 | 10 | 2 | 0 | 0 | 696 | 6 |
| H2 | 4 | 0 | 2 | 86 | 14 | 3 | 7 | 2 | 1 | 1 | 80 | 0 |
| P2 | 5 | 0 | 0 | 87 | 9 | 4 | 8 | 1 | 4 | 0 | 138 | 2 |
| H3 | 67 | 0 | 4 | 345 | 18 | 13 | 13 | 3 | 2 | 1 | 875 | 0 |
| C1 | 156 | 0 | 5 | 2,076 | 79 | 42 | 58 | 12 | 14 | 5 | 3,013 | 15 |
| **Total** | **308** | **0** | **16** | **3,246** | **167** | **85** | **119** | **25** | **29** | **9** | **6,508** | **28** |

Definitions:

- `manager_calls`: JSONL lines in `manager_calls_file`.
- `manager_fallbacks`: calls with `fallback.used_rule == true`.
- `manager_repairs`: calls with `repair_used == true`.
- `narrator_texts`: JSONL lines in `narrator_file`.
- `news_pool_actions`: `actions[]` grouped by `action` (`veto` / `promotion`).
- `news_date_records`: `dates[]` records, one per `decision_date`.
- `news_level_c_decisions`: `levels_v2.decisions[]` with a non-empty
  `c_flags` object or a non-empty `c_flagged` list.
- `news_level_d_decisions`: `levels_v2.decisions[]` with `d_fired == true`.
- `news_exits`: `levels_v2.b_news_exits` (the level-B news exits; the same
  count appears as `trigger == "news_shock"` on `kind == "stop"` detail lines).
- `news_sector_rejections`: sum of `eligible_counts.news_sector` over every
  detail line that carries it. It is stored on the news run record so the
  count is store-verifiable from the block-F graph, but its source is the
  detail file.
- `bull_triggered`: `decisions[]` with `triggered == true`.

The loader fails on a manifest-versus-file mismatch. A manifest-versus-store
mismatch is a failure in `--check-store` when the graph exists; an absent graph
prints `not store-verifiable` and does not fail.

## 3. Graph names

One graph per file, because the reviewer accepted that any piece may be loaded
later (“se agrega más adelante”):

```
urn:graph:derived:backtest:agents:{label}:{window}:manager_calls
urn:graph:derived:backtest:agents:{label}:{window}:narrator
urn:graph:derived:backtest:agents:{label}:{window}:news
urn:graph:derived:backtest:agents:{label}:{window}:bull_mode
```

`label` is the manifest label (`final`); `window` is the run window. The gate
gets one new append-only target pattern for `agents`. The graphs are separate
streams and never merged: a missing graph is a piece not loaded yet, not a
failed delivery.

## 4. Identifiers

All IRIs are in `https://thesis.local/kg/portfolio#`.

| Individual | IRI rule | Key |
|---|---|---|
| `:ManagerCall` | `ManagerCall_{label}_{window}_{call_index}` | `call_index` local to the run |
| `:NarratorText` | `NarratorText_{label}_{window}_{kind}_{date}_{asset_id}` | `(kind, date, asset_id)` |
| `:NewsAction` | `NewsAction_{label}_{window}_{date}_{asset_id}_{action}` | `(decision_date, asset_id, action)` |
| `:NewsEvidence` | `NewsEvidence_{label}_{window}_{date}_{asset_id}` | one per action's `evidence` |
| `:DateRecord` | `DateRecord_{label}_{window}_{date}` | `decision_date` |
| `:NewsRunRecord` | `NewsRun_{label}_{window}` | one per run |
| `:BullModeRecord` | `BullMode_{label}_{window}` | one per run |
| `:BullModeDecision` | `BullModeDecision_{label}_{window}_{date}` | decision date |

`:ManagerCall :callOfStop` uses the existing stop IRI
`Stop_{label}_{window}_system_with_hierarchy_{date}_{stopped_asset_id}`, so the
call joins the detail graph without copying it. A manager stop always matches a
`kind == "stop"` detail line (checked by the loader). `:NarratorText` links to
the same stop for `kind == "stop"`; the other kinds keep their source literals.

Engine asset ids are mapped to tickers with the news file's own
`canonical_tickers` table (ticker -> engine id), reversed. That table covers
every id used by the manager and narrator files in all seven windows. Asset
links are written as `:TICKER` (the existing `:Asset` IRI convention); a
ticker absent from the map stops the load instead of being dropped silently.

## 5. What is stored, and what is pointer-only

Typed core fields only. Never stored:

- full prompts (`system_prompt`, `user_prompt`, `turns[].prompt`),
- raw answers (`first_raw_answer`, `raw_answer`, `raw_message`,
  `turns[].raw_answer`, `turns[].raw_message`),
- the whole `state`/`label_maps`/`tools` objects,
- large nested tables: `base_rates.tiers`, `c_thresholds`, per-date `pool`,
  `window`, `base_window`, `benchmark` tables.

For each omitted object the loader stores a SHA-256 and a pointer:

- `:sourceDocument` — delivery-relative path;
- `:sourceLineNumber` — JSONL line (1-based) for manager/narrator;
- `:sourceEventLine` — the event line the narrator recorded in `source_line`;
- `:sourceJsonPointer` — RFC 6901 JSON pointer for one object in a JSON file;
- `:recordSourceSha256` — the file hash accepted from `SHA256SUMS`;
- `:newsBaseRatesSha256`, `:newsTestSha256`, `:newsLevelCDecisionsSha256` — the
  hashes of the omitted nested tables.

Prompts and answers are hashed by the loader (`SHA-256` of the exact UTF-8
string) so the record can be audited against the source file without storing
the text. The source-provided `prompt_sha256`, `prompt_template_sha256`,
`tool_outputs_sha256` and skill hashes are stored verbatim.

`:NewsEvidence` stores `n`, `a`, `b`, `state`, `covered`,
`mean_probability_margin`, the six tier cells (`negative/neutral/positive` ×
tier 1/2), the test statistics and critical values, and every exact fraction
as an integer numerator/denominator pair (`p`, `size`; negative and positive).
No p-value or size is ever parsed as a float. `:NewsAction` stores `replaces`
and `replaced_by` as asset links, and a `fills[]` entry is validated to agree
with the matching veto action (`:newsActionFilled true`, fill asset link);
fills do not create a second action individual.

`:DateRecord` stores coverage, admission counts, the pooled and expected
fractions (numerator/denominator), the level-B threshold, the level-C
flagged count and Boolean, `d_fired`, `d_p20`, `d_tone21`, and the
`filter_inputs` flags (`price`, `news`) as Booleans. `price` is a flag, never
a price. `:NewsRunRecord` stores `news_mode`, `news_alpha`, the news table
hash, `b_news_exits`, the detail-derived sector-rejection count and the number
of dates. `:BullModeRecord` stores N11 constants; `:BullModeDecision` stores
one row per decision date (`evaluable`, `triggered`, `z`, `rung`, `t1`, `n`,
and the five `n11` fields).

## 6. Expected sizes

Individuals (exact):

| Window | calls | narrator | actions | evidence | dates | bull decisions |
|---|---:|---:|---:|---:|---:|---:|
| P1 | 4 | 253 | 25 | 25 | 10 | 10 |
| H1 | 57 | 268 | 20 | 20 | 13 | 13 |
| P3 | 15 | 131 | 25 | 25 | 10 | 10 |
| H2 | 4 | 86 | 17 | 17 | 7 | 7 |
| P2 | 5 | 87 | 13 | 13 | 8 | 8 |
| H3 | 67 | 345 | 31 | 31 | 13 | 13 |
| C1 | 156 | 2,076 | 121 | 121 | 58 | 58 |
| **Total** | **308** | **3,246** | **252** | **252** | **119** | **119** |

Triples (measured with `project()` over the real delivery; `:newsItem` included):

| Window | manager_calls | narrator | news | bull_mode | Total |
|---|---:|---:|---:|---:|---:|
| P1 | 208* | 6,138* | 2,179* | 192* | blocked |
| H1 | 2,982 | 6,495 | 2,115 | 255 | 11,847 |
| P3 | 779 | 3,177 | 3,272 | 201 | 7,429 |
| H2 | 218 | 2,095 | 1,615 | 143 | 4,071 |
| P2 | 256 | 2,114 | 1,433 | 160 | 3,963 |
| H3 | 3,491 | 8,363 | 4,048 | 256 | 16,158 |
| C1 | 8,116* | 50,122* | 12,272* | 1,095* | blocked |
| **Five loaded windows** | **7,726** | **22,244** | **12,483** | **1,015** | **43,468** |

\* Manager/narrator/bull-mode triples for P1 and C1 are known, but the news graph cannot be
projected: two REGN test rows (`280187`, `328156`) have no `news_rows.jsonl` row. T-906 refuses to
guess an item kind, so the loader stops before building those two news graphs. The restriction is
the known 92-index-leaver gap; the other five windows load and SHACL-conform. The full delivery is
still below the 400,000-triple bound.

## 7. Loader and CLI

`cli/load_agents.py` follows `cli/load_series.py`:

- dry run by default (manifest + hashes + parse + SHACL, no store contact);
- `--check-store` reads the live store, plans every selected graph through
  `gate.plan`, writes nothing, and compares stored counts when a graph exists;
  it (and `--write`) needs the same label's veto/detail and block-D news graphs already loaded
  (order: schema, universe, veto, news, agents), because the store is the only plan context;
- `--write` plans then appends with `gate.write_batched` and verifies after;
- `--to-production` is required for `--write` to `portfolio`;
- `--window` (repeatable) and `--only` (repeatable:
  `manager_calls`, `narrator`, `news`, `bull_mode`) let the maintainer load
  one piece later without touching the others;
- a timeout or lost answer is `WriteInDoubt`: the loader prints the graph name
  and stops; it never retries blindly.

## 8. Schema and shapes

One clearly marked block at the end of `schema/tbox.ttl` and
`schema/shapes.ttl`:

- classes: `:ManagerCall`, `:NarratorText`, `:NewsAction`, `:NewsEvidence`,
  `:DateRecord`, `:NewsRunRecord`, `:BullModeRecord`, `:BullModeDecision`;
- all eight are `:Observation` leaves and join a second
  `owl:AllDisjointClasses` block at the end of `tbox.ttl` (the existing block is
  untouched to keep the merge small);
- one closed `sh:NodeShape` per class, with required fields, datatypes,
  `sh:in` for closed vocabularies (`source`, `action`, `state`, `t1`) and
  `sh:minCount`/`maxCount` as the source contract requires;
- `:generatedByLanguageModel` and `:provenanceNote` widen their domain to a
  union that includes `:NarratorText` (and `:ManagerCall` for the Boolean), so
  the narrator provenance sentence is the same property the fundamentals
  block uses.

Every model text gets
`“generated by a language model; not a verified fact”` in
`:provenanceNote` (the source text does not contain it). Template text gets
`:generatedByLanguageModel false` and
`“template text; not generated by a language model”`.

## 9. Deviations from `docs/veto-hierarchy-design.md` §7

1. **News file shape.** §7 assumed one `PoolActionRecord` per line. The final
   file is one JSON object with `actions`, `dates`, `fills` and `levels_v2`.
   `:DateRecord` is keyed by `decision_date` and carries the level fields, so
   the level-C/D table does not need a second date class.
2. **`:NewsAction` key.** The action key is
   `(decision_date, asset_id, action)`, as designed; `replaces`/`replaced_by`
   are asset links and `fills[]` is confirmation, not a second action.
3. **`:newsItem` link.** PR D now defines
   `:NewsItem_{item_kind}_{item_id}_{ticker}` and the loader builds the link
   from the delivery's `news_rows.jsonl` through D's `parse_rows` helper.
   The test rows stay as `:newsTestRow "<item_id>:<ticker>"`; every evidence
   individual also carries one `:newsItem` link per test row. A test row with
   no row, or the same `(item_id, ticker)` under two item kinds, stops the
   load. On the real delivery two REGN test rows (280187 and 328156, P1 and
   C1) are absent from the 69,329-row file; they are the known 92-leaver gap
   and P1/C1 cannot load until the delivery supplies them or Reviewer A
   approves a skip.
4. **Manager fields.** The real file has `answer_choice` (not
   `answerChoice`), `fallback.used_rule/used_cash/cause/detail`,
   `repair_used/repair_cause/repair_detail`, `model.requested/resolved/
   revision/reasoning_effort_used`, `first_validator`, `validator`, `usage`,
   `finish_reasons`, `tool_order`, `shuffle_seed`, and the skill hashes. §7's
   `:validatorPassed`/`:validatorCause` are kept for the final validator; the
   first validator gets its own optional properties. Because master's block D
   already defines `:modelRevision` on `:NewsItem`, the manager/narrator field
   is `:providerModelRevision`, not `:modelRevision`, so RDFS+ cannot type a
   `:ManagerCall` as a `:NewsItem`.
5. **Narrator key.** The real key is exactly `(kind, date, asset_id)`; the
   file also carries `source_kind`, `source_date`, `source_asset_id`,
   `source_line`, `omitted_fields`, `prompt_sha256`, `template_sha256`,
   `validator` and a `model` block even for template text. All are stored
   (except the text itself, which is the payload).
6. **Bull mode is new.** §7 does not model it. `:BullModeRecord` and
   `:BullModeDecision` are added; one decision per date, joined to the date
   record by date.
7. **News sector rejections.** The manifest count is not in the news file; it
   is the sum of `eligible_counts.news_sector` in the detail file. The loader
   reads that file only to cross-check and stores the count on
   `:NewsRunRecord`.
8. **Run records.** `:NewsRunRecord` and `:BullModeRecord` are run-level
   individuals (not in §7) so the file-level counts and configuration link
   have a subject.

## 10. Open items

- The loader keeps its own manifest read (it needs the raw per-window file
  aliases) but a test now checks that B's `read_manifest` and this loader
  resolve the same files.
- T-905 is implemented: `verify_store --manifest` calls
  `verify_agent_control_counts` and prints absent graphs as
  `not store-verifiable`.
- T-906 is implemented; the two missing REGN test rows in P1/C1 are a
  delivery-data gap, not a schema gap.
- No GraphDB write is made in this change. The real dry run and the
  `portfolio_test` pre-flight are evidence; the production write is a
  maintainer decision.
