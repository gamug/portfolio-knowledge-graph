# Project Constitution

Governing principles for `portfolio-knowledge-graph` under a spec-driven ("spec
coding") workflow: specs and plans are written before implementation, and this
document is the fixed reference they must not contradict. A spec or plan that
conflicts with a rule below must change the rule here first (see Governance)
rather than override it silently.

## Technological stock

`portfolio-knowledge-graph` is a design/artifact repo, not a service — there is
no FastAPI/Streamlit component and no resident ML model; every rule below
assumes the stack actually pinned in `pyproject.toml`.

1. **Runtime**: Python `>=3.12`, dependency-managed with `uv` (lockfile
   `uv.lock`, `package = false` since `src/etl/` is put on `sys.path` by
   `cli/build_data_ttl.py` rather than installed as a wheel). Do not add a
   second package manager (pip/poetry/conda) — all installs go through
   `uv sync` / `uv add`.
2. **Ontology tooling**: `rdflib>=7.0` (parse/serialize every `.ttl`/`.trig`
   file as one `rdflib.Dataset`) + `pyshacl>=0.26` (closed-world SHACL
   conformance over that same dataset). These two libraries, plus
   `python-dotenv` for the ETL's `.env`-driven config, are the entire
   ontology-specific dependency surface — there is no triple-store client
   library yet because no triple store is stood up (roadmap step 1, not
   started).
3. **Storage (ETL only)**: SQLite, accessed two-tier (SOURCE `urls.db`
   ATTACHed read-only, `portfolio-nlp`'s RESULTS `nlp.db` read-only) through
   `portfolio_common.news_export.connect_readonly` /
   `fetch_processed_articles` — never a raw `sqlite3.connect()` — git-tag-pinned
   (`portfolio-common @ tag v1.2.0` in `[tool.uv.sources]`) so a DB-engine or
   results-contract change is an explicit, reviewed re-pin, never a floating
   version. This repo owns no SQL of its own for that join; see
   `docs/portfolio-common-v1-migration-plan.md` for the decision history and
   `docs/portfolio-common-v1.2-engine-agnostic.md` for the current state.
4. **Raw price/tick data never enters the ontology or the ETL output**
   (`07-ontology-topology.md`'s explicit warning) — only derived,
   bounded-window `PriceObservation` summaries are in scope for a future
   projection. Don't add a full OHLCV panel class to `tbox.ttl` or a raw-bar
   field to `src/etl/`.
5. **Licensing**: this repo has no ML model checkpoints of its own to vet —
   it only ever reads `portfolio-nlp`'s already-published RESULTS rows. Flag
   anything copyleft or usage-restricted in the PR that adds a new dependency
   regardless.
6. **Adopting a new library/framework is a constitution-level change**: add it
   to `pyproject.toml` with a rationale in the PR, and if it changes a rule
   above, amend this section (see Governance). Standing up a triple store
   (GraphDB/Fuseki), an OWL reasoner, or a SPARQL client library is the
   biggest such change on this repo's horizon — it needs its own spec/plan
   before it lands, not an incidental dependency add.

## Project structure

1. **`schema/` is the authoritative ontology bundle** — `tbox.ttl` (OWL
   classes/properties/cardinality), `shapes.ttl` (SHACL node shapes, kept
   deliberately separate from `tbox.ttl` — open-world inference vs.
   closed-world validation, don't collapse one into the other), `reference.ttl`
   (GICS taxonomy + worked-example individuals + `MetricType` vocabulary),
   `rules.ttl` (the veto catalog as `RuleClause` trees), `instances.trig`
   (the multi-named-graph worked-example ABox). `schema/README.md` is the
   authoritative map of this directory — read it, and its "implementation
   addendum," before editing any file in it. `schema/protege-view.ttl` is
   **generated** (a flattened plain-Turtle bundle for Protégé); never hand-edit
   it.
2. **New ontology terms are placed in the taxonomy, not left flat** — a new
   class belongs under whichever of the 13 backbone classes matches its
   *property shape*, not its theme (`06-ontology-definition.md` §1.2).
   `ObservationSnapshot`, `EvidenceSource`, and `RuleOperand` are ordinary
   superclasses; don't reintroduce an `owl:unionOf` pattern for a future
   shared-property case.
3. **`src/etl/` is the one real importable package**, flat except for
   `common/` (dependency-free helpers: GICS rollup, provenance-ID formatting,
   the provisional severity/G1–G3 formulas, Turtle-literal helpers).
   `cli/build_data_ttl.py` is the single entrypoint — it prepends `src/` to
   `sys.path` before importing; copy that bootstrap pattern for any new
   entrypoint rather than inventing a second one (an installed console
   script, a second `sys.path` hack inside a module).
4. **The five numbered docs (`06`–`10`) plus `critique-and-evolution.md` are
   the formal specification**, each a companion to its neighbors, not
   standalone — a class defined in `06` gets its storage location assigned in
   `07` and its writer assigned in `08`. A design gap discovered only while
   populating real data (not anticipated by `06`/`07`) gets flagged inline at
   the point it surfaces, then summarized in `schema/README.md` — the same
   pattern already used for the `CategoricalComparison`/`GraphPredicate` leaf
   types, the raw-vs-normalized comparison convention, and the two additional
   named-graph placements. Don't silently special-case a new one in a single
   file instead.
5. **Docs live under `docs/`**, one topic per file (migration/coordination
   notes named by topic, e.g. `portfolio-common-v1-migration-plan.md`,
   `portfolio-common-v1.2-engine-agnostic.md`). A spec-kit artifact (this
   constitution, `SPEC.md`, `PLAN.md`, `TASKS.md`) goes under `.specify/`.
6. **Config lives where its tool expects it**: Ruff → `.code_quality/ruff.toml`
   (a root `ruff.toml` pointer, if one exists, only `extend`s it); Mypy →
   `.code_quality/mypy.ini`. Don't fork a second config file for a tool that
   already has one.
7. **Environment**: `.env` (git-ignored) holds the ETL's `KG_*` variables
   (`KG_URLS_DB`, `KG_RESULTS_DB`, `KG_SCHEMA_DIR`, `KG_DATA_TTL`,
   `KG_SP500_SOURCE_URL`, `KG_SAMPLE_NEWS_ROWS`); `.env.example` is the
   committed template — keep it in sync with every env var a new ETL feature
   reads. `src/etl/config.py`'s `load_dotenv()` at import is the single place
   `.env` gets loaded.
8. **IRI namespace**: everything hangs off `https://thesis.local/kg/portfolio#`
   (prefix `:`) across every `schema/*.ttl`/`.trig` file and everything
   `src/etl/` emits — keep new terms in that namespace unless deliberately
   aligning to an external vocabulary (FIBO via `rdfs:seeAlso`, GICS sectors/
   industries as `skos:Concept`s).

## Ontology design invariants

*(the modeling equivalent of "AI behavior" for a repo with no resident ML
model — these are the conventions a spec/plan/PR must not silently violate.)*

1. **Immutable observations, not mutable attributes.** `ScoreSnapshot`
   individuals (and every other `ObservationSnapshot` subclass) are never
   updated in place — a new measurement is a new individual. This is the
   audit-trail principle inherited from the source v1 design (§3A); don't
   model a new metric as a node property that gets overwritten.
2. **Valid-time via `validFrom`/`validTo`**, absence of `validTo` means "still
   active" (`UniverseMembership`, `PortfolioPosition`, `RuleDefinition`) —
   closed by writing `validTo` on the old record, never by deleting it.
3. **N-ary relations are reified as classes**, not modeled as a direct
   property, whenever the relationship itself carries data (dates, a
   provenance ID) — `UniverseMembership` reifying `Asset`-in-`Universe`-with-
   dates rather than a bare `hasUniverse` property is the template.
4. **The `RuleClause` tree, not an infix string.** Every confluent veto rule
   is an explicit `AND(primary_signal, OR(secondary_signals))` tree
   (`ThresholdComparison` / `CategoricalComparison` / `GraphPredicate` leaves)
   — this exists specifically to make v1's unparenthesized ∧/∨ precedence
   ambiguity structurally impossible. A new rule follows the same pattern;
   never re-introduce a string the ontology or a consumer has to re-parse.
5. **OWL and SHACL are deliberately both present and answer different
   questions.** `tbox.ttl` is open-world (what can be *inferred*);
   `shapes.ttl` is closed-world (what an ingestion pipeline *rejects*). A
   spec/plan that proposes replacing one with the other is proposing a
   constitution amendment, not a routine change.
6. **The raw-vs-normalized comparison convention is explicit, not implicit**:
   `Score*` metrics compare on `normalizedScore`; `Sentiment` compares on
   `rawValue` (`schema/README.md`'s documented gap). A shape or rule touching
   either must respect which one that metric type actually uses.
7. **The ETL's projection is an explicitly-scoped MVP, not the target
   architecture.** `src/etl/` writes one flat, non-partitioned `data.ttl` —
   it does not implement `07-ontology-topology.md`'s named-graph
   partitioning, and any provisional formula it applies without a calibrated
   sign-off (`src/etl/common/severity.py`'s G1–G3, G9) must stay flagged as
   provisional in both the module and `src/etl/README.md`, not presented as
   settled.

## Claude Code / coding-agent conduct

1. **Match existing structure before introducing new structure** — check
   where a file's siblings live and follow that placement/naming (the
   `sys.path` bootstrap, `etl.<module>` imports) rather than a generic
   layout.
2. **This constitution and `.specify/memory/SPEC.md` are the binding
   reference for planning and review** — read both before drafting a
   spec/plan, and resolve any conflict between a request and a stated
   principle or requirement by surfacing it or proposing an amendment, not by
   quietly overriding either. A local, untracked `CLAUDE.md` may carry
   situational/session notes, but it is never authoritative and must not be
   treated as a source of fact for anything either document already states —
   see `SPEC.md` §13 for a concrete case where `CLAUDE.md` was found to lag
   `origin/master` by several merged PRs.
3. **Prefer the smallest change consistent with the existing pattern**; no
   opportunistic refactors, renames, or new abstractions outside what the
   spec/task calls for. In particular: don't renumber an `FR-0xx`/`NR-0xx`/
   `T-0xx` ID, and don't rename a published Claude Artifact's title as a side
   effect of a content update (see item 6 below).
4. **`CLAUDE.md` must always exist on disk and must never be deleted**, even
   though it is intentionally untracked (`.gitignore`), and it must always
   carry a reference to both this constitution
   (`.specify/memory/constitution.md`) and `.specify/memory/SPEC.md`. If
   `CLAUDE.md` is missing at the start of a session, run `/init` to
   regenerate it before doing anything else; if it exists but is missing
   either reference, add it before proceeding.
5. **Ask before expanding scope this constitution doesn't cover** — standing
   up a triple store, adding a new external service, a new heavy dependency,
   or a schema change to the SOURCE/RESULTS contract this repo reads from.
6. **Reconcile the architecture artifacts at the close of every development
   effort** — when a PR/feature/fix is done (merged, or ready to merge),
   update both:
   - the general, system-wide artifact — [Portfolio
     Thesis](https://claude.ai/code/artifact/d3865a63-2894-4e20-b38a-7e50cf0d4040)
     (the six-repo integrated architecture overview); and
   - the repository-specific artifact — [Portfolio Knowledge
     Graph](https://claude.ai/code/artifact/d5d59284-9565-4bf6-8a54-3d2d1549863f)
     (this repo's component flow, gap list, and plan)

   to close whatever gaps the effort closed and reconcile the artifact's
   prose with what the schema/docs/ETL now actually do — an artifact
   describing a gap that was just fixed, or a plan step that was just built,
   is now wrong and must be corrected in the same pass, not left stale.
   **Never** rename either artifact when doing this — **NEVER** change its
   title (the `<title>` tag / the name shown in the artifact gallery).
   Content, diagrams, gap lists, and plans update freely; the name is stable
   forever, independent of content changes. (See `Artifact` tool guidance:
   title changes are an explicit, separate, user-directed action, never a
   side effect of a content update.)

## Executable cmds

Canonical commands — a spec/plan should reference these, not invent new
ad-hoc invocations:

```bash
uv sync                                     # install deps

# Ontology validation (run from schema/) -- the only automated gate today
uv run python -c "
import rdflib
g = rdflib.Dataset()
for f, fmt in [('tbox.ttl','turtle'), ('shapes.ttl','turtle'), ('reference.ttl','turtle'), ('rules.ttl','turtle')]:
    g.parse(f, format=fmt)
g.parse('instances.trig', format='trig')
print('quads:', len(list(g.quads())))
"
uv run pyshacl -s shapes.ttl -m -a -f human tbox.ttl reference.ttl instances.trig

# ETL (needs KG_URLS_DB / KG_RESULTS_DB set, see .env.example)
uv run python cli/build_data_ttl.py --limit 500   # smoke test
uv run python cli/build_data_ttl.py               # full run -> data.ttl (git-ignored)

uv run ruff check .                         # lint (config: .code_quality/ruff.toml)
uv run ruff format --check .                # format check
uv run mypy --config-file=.code_quality/mypy.ini   # types

uv run pre-commit run --all-files           # all of the above hooks, plus hygiene checks
```

1. **There is no CI workflow configured** (`.github/` does not exist) — the
   parse+`pyshacl` check and the lint/type/pre-commit hooks above are run
   manually before a PR. This is a documented gap (`SPEC.md` §9/§14), not an
   oversight to silently work around by inventing a workflow file outside a
   spec/plan for doing so.
2. **Don't hardcode a different Python/uv invocation** (bare `python`,
   `pip install`) in scripts or docs — every command goes through `uv run` so
   it resolves the locked environment.

## Code & Git

1. **Formatting/linting/types are enforced via `pre-commit`**: `ruff-check
   --fix` + `ruff-format` + `mypy` (project venv, whole-graph, via `uv run`
   because `portfolio_common`'s `py.typed` marker needs the installed
   package, not an isolated mirrors-mypy env). A `# noqa` / `# type: ignore`
   needs a comment saying why the finding is wrong for this code, not just
   silence.
2. **Commit messages are Conventional Commits**, enforced by the
   `commitizen` pre-commit/pre-push hook — `type(scope): summary`, matching
   the existing history (`feat(etl): ...`, `refactor(etl): ...`, `docs: ...`,
   `chore(devcontainer): ...`). Reference the PR number in the subject once
   it exists, as the existing log does.
3. **Branch off `master`, never commit to it directly.** `master` is the
   integration branch; feature/fix/docs work happens on a descriptively-named
   branch (`feat/...`, `fix/...`, `docs/...`, `chore/...`, `refactor/...`)
   opened as a PR.
4. **Pre-commit hooks are mandatory, not optional**: `check-yaml`,
   `check-case-conflict`, `debug-statements`, `detect-private-key`,
   `check-merge-conflict`, `check-added-large-files` run alongside
   ruff/mypy/commitizen — install them (`uv run pre-commit install`) rather
   than relying on remembering to run checks manually.
5. **No secrets committed.** `.env` stays git-ignored; `.env.example` holds
   placeholder/path values only; `detect-private-key` is a backstop, not the
   first line of defense.
6. **Leave the working tree checked out on the branch just pushed/PR'd.**
   After opening a PR, don't switch back to `master` — the local checkout
   stays on that branch so the user can review the actual working tree
   immediately. Only move off it (per item 3, always to a fresh branch off
   up-to-date `master`) when starting genuinely new work, or when asked to.

## Governance

This constitution supersedes ad-hoc convention when the two conflict. A spec
or plan may not silently contradict a rule above; instead:

1. Propose the amendment as its own change (state which section, what
   changes, and why).
2. Get it reviewed the same way a code PR would be (this repo's normal
   review path) before relying on it.
3. Bump the version below per semver: **MAJOR** for a removed/redefined
   principle, **MINOR** for a new principle or materially expanded guidance,
   **PATCH** for wording/typo fixes.
4. Record the change under "Last Amended" with the date.

Compliance is expected to be checked the same way a schema-parse/`pyshacl`
gate is — a reviewer (human or agent) rejecting a PR that violates a
principle above should cite the section by name.

**Version**: 1.0.1 | **Ratified**: 2026-09-12 | **Last Amended**: 2026-09-12

<!--
1.0.1 (2026-09-12): PATCH, wording/self-consistency fix only. The "Executable
cmds" rdflib snippet used bare `python -c`, contradicting this section's own
rule 2 (verified to fail without `uv run` in this environment); fixed to
`uv run python -c`. Also reworded "`.github/workflows/` is empty" to
"`.github/` does not exist" (the directory itself is absent, not merely
empty). No principle changed.
-->
