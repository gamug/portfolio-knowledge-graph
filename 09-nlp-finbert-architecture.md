# NLP Architecture — FinBERT Pipeline

Companion to `08-agent-architecture.md`'s Semantic Agent, which calls this pipeline as a tool.
Fills the currently-empty `news-nlp/` repo (today it's just a copied `data/` directory — no code)
with the sentiment/evidence-extraction service that v1 §2B assigns to the Semantic Agent, and that
`06-ontology-definition.md`'s `ScoreSnapshot(agentOrigin='SEMANTIC')` and `RiskEvent` classes exist
to receive.

## Where it lives, and what feeds it

Two inputs, both already-clean structured text (no HTML/boilerplate to strip — that work is
already done upstream):

1. `news-crawler`'s `articles.body_text` — 2,289/2,289 rows already extracted and classified
   (`fetch_status='ok'`) in the sample corpus; scales automatically as `news-collector`/
   `news-crawler` cover more of the S&P 500.
2. A new EDGAR section extractor's output — Item 1A (Risk Factors), Item 3 (Legal Proceedings),
   DEF 14A director lists (v1 §2B) — built on `edgar_tool.py` (roadmap step 4).

## Model choice — and what FinBERT does *not* cover

**FinBERT (recommend `yiyanghkust/finbert-tone` as primary)** provides sentence/paragraph-level
**3-way tone classification (positive/negative/neutral) only** — it was fine-tuned on analyst
reports and earnings-call transcripts, which sit distributionally closer to 10-K risk-factors
prose and financial news than the general-domain `ProsusAI/finbert` alternative (worth keeping as
a cross-check, not a replacement). This has to be stated plainly because FinBERT alone leaves two
gaps unfilled:

- **No entity recognition.** FinBERT does not extract company/person mentions. A dedicated NER
  pass runs per chunk to (a) confirm a chunk is actually about the target `Asset` — a
  disambiguation signal, not just a keyword match — and (b) extract `Executive` name mentions from
  DEF 14A sections, feeding both `Executive` individuals and the entity-resolution service
  (roadmap step 7) that `VETO_RED_01` depends on. See the dedicated section below — this was
  originally scoped as generic spaCy NER; a concrete piece of financial-domain prior art changes
  that recommendation.
- **No event/category classification.** Turning a negative-tone chunk into a `RiskEvent.category`
  (`LEGAL`/`FINANCIAL`/`MARKET`/`NETWORK`) and `RiskEvent.severity` needs its own step — see below.

## Named entity recognition — MRC-style, informed by FinBERT-MRC

The original scope for this section was generic spaCy NER (`en_core_web_trf`), justified only as
"a separate model, since FinBERT doesn't do this." **[FinBERT-MRC](https://github.com/zyz0000/FinBERT-MRC)**
(MIT license) is concrete financial-domain prior art for a better-grounded architecture — but it
needs to be adopted as a *pattern*, not a *checkpoint*, and it's worth being precise about exactly
which part transfers and which doesn't, since "FinBERT" is being used as a name for several
unrelated models across this document already.

**What FinBERT-MRC actually is** (confirmed by inspecting the repo directly, since its README is
minimal): NER reformulated as machine reading comprehension (MRC) — the architecture from the
"unified MRC framework for NER" line of work. For each entity type, a natural-language query
describing that type (e.g. "找出价格" — "find the price") is concatenated with the input text, and
the model predicts start/end token-span positions that answer it, rather than doing per-token
BIO-tag classification. It fine-tunes a **Chinese** BERT-base encoder (`FinBERT/config.json`:
`vocab_size: 21128`, the standard `bert-base-chinese` vocabulary — a different, unrelated "FinBERT"
from `ProsusAI/finbert` or `yiyanghkust/finbert-tone` above) on **ChiFinAnn**, a Chinese corporate-
announcement dataset, against 10 entity types read out of `data/mid_data/ent2id.json`: `Price`,
`Shares`, `Institution`, `Company`, `StockAbbr`, `StockCode`, `Date`, `Ratio`, `EquityHolder`,
`Pledgee`.

**What transfers to this pipeline, and what doesn't:**

| | Transfers? | Why |
|---|---|---|
| The checkpoint/weights | **No** | Chinese-vocabulary encoder — cannot tokenize English SEC-filing or news text meaningfully. |
| The training data (ChiFinAnn) | **No** | Chinese corporate announcements, not English 10-K/10-Q/DEF 14A or English financial news. |
| The MRC query-and-span architecture | **Yes** | Language-independent. Query-per-entity-type span extraction handles overlapping/adjacent entities better than BIO tagging — directly relevant here, since financial text routinely nests entities (e.g. "Apple Inc. (NASDAQ: AAPL)" has `Company` and `StockCode` spans immediately adjacent). |
| The entity taxonomy, adapted | **Partially** | See table below — most of FinBERT-MRC's 10 types map cleanly onto what this pipeline needs; one doesn't. |
| The codebase (`preprocess/processor.py`, `utils/trainer.py`, query-construction logic) | **Yes, as a reference implementation** | MIT-licensed — safe to fork/adapt as a starting point for an English equivalent rather than building the MRC-NER training loop from zero. |

**Adapted entity taxonomy for this pipeline** (English, SEC/news-oriented, each mapped to why it
matters here — not a blind copy of the Chinese set):

| Entity type | Adapted from | Feeds |
|---|---|---|
| `Company` | `Company` | Confirms a chunk is actually about the target `Asset` (the disambiguation signal above). |
| `TickerSymbol` | `StockAbbr` + `StockCode` merged | English filings/news use one ticker convention, not separate abbreviation/code fields. |
| `ExecutiveName` | *(new — not in the Chinese set)* | `Executive` individuals + entity resolution — the highest-priority addition, since `VETO_RED_01` depends on it directly. |
| `Date` | `Date` | Event/filing dating, cross-checked against `SECFiling.filingDate`/`NewsArticle.publishedDate`. |
| `MonetaryAmount` | `Price` | Settlement amounts, fines, revenue figures inside risk-factor prose. |
| `ShareCount` | `Shares` | Buybacks, dilution, insider-transaction mentions. |
| `FinancialRatio` | `Ratio` | E.g. "debt-to-equity of 1.2" inside narrative text. |
| `EquityHolder` | `EquityHolder` | Ownership disclosures, activist-investor mentions. |
| `Institution` | `Institution` | Regulators/auditors/banks named in a `RiskEvent` (e.g. "SEC investigation" → `Institution` = SEC), useful context for the category classifier below. |
| `Pledgee` | `Pledgee` | **Deprioritized, not dropped** — share-pledge disclosure is a far bigger norm in Chinese equity markets than U.S. ones, though Rule 144/insider-pledge disclosures do occasionally appear in English filings; worth revisiting once the core 8 types are working, not before. |

**What building this needs that FinBERT-MRC doesn't supply:** an English base encoder (one of the
sentiment FinBERT variants above, or a general English BERT, fine-tuned into the MRC-NER shape)
and a labeled English financial-NER dataset to fine-tune against — no labeled data exists yet in
this project. **FiNER-139** (SEC XBRL-tag-derived financial NER, Loukas et al.) is a public
candidate worth evaluating for this if it's still accessible/maintained — not confirmed fit for
purpose in this session, flagged as a next step rather than adopted outright. Until that fine-tune
exists, the pragmatic v1 fallback is still a general English NER model (e.g. spaCy
`en_core_web_trf`) run per chunk — worse precision on financial-specific spans, but zero additional
training data required, which is why it was the original v1 scope. The MRC architecture is the
v2 target once a labeled set exists, not a blocker on shipping v1.

## Long-document chunking

10-K Item 1A sections routinely run 15–40 pages, far past FinBERT's 512-token window. Chunking is
**paragraph-level**, split along the section's own structural boundaries (bullet/paragraph breaks
from the extracted text) rather than a fixed character window, so each chunk stays a coherent
unit; any chunk still exceeding 512 tokens after tokenization is truncated with the event logged,
so a chunker that's truncating too often shows up as a monitorable rate rather than silent data
loss.

## Aggregation policy — two, chosen deliberately for two different jobs

A single document's chunk-level scores are aggregated two different ways, because averaging and
worst-case answer different questions:

- **Mean-pool → `Sentiment` `ScoreSnapshot`.** The general tone metric feeding the veto rules'
  `Sentiment<U` comparisons wants the *overall* tone of the document.
- **Max-severity → `RiskEvent` trigger gate.** One alarming paragraph buried in an otherwise
  routine risk-factors section should not be diluted away by averaging across thirty neutral
  paragraphs — the worst chunk drives whether a `RiskEvent` fires at all.

## RiskEvent classification — v1 rule-based, v2 fine-tuned

**v1 (now):** a keyword/regex layer over chunks that clear the max-severity gate — e.g. "lawsuit",
"litigation", "SEC investigation" → `LEGAL`; "restatement", "material weakness" → `FINANCIAL` —
combined with the FinBERT negative-tone score as the severity gate, not the sole signal.

**v2 (later, ties to evolution layer B10):** once a labeled `RiskEvent` severity dataset
accumulates (from analyst review or the feedback loop), fine-tune a classifier head on FinBERT
embeddings to replace the keyword heuristic directly. The user already has working HF fine-tuning
experience on this machine (`courses/hungging-face-project/mental-disorders-classificator`), so
this is a capability gap of zero, not one — it's sequenced as v2 purely because no labeled dataset
exists yet, not because the skill is missing.

## Output contract — concrete provenance, not a fresh ID scheme

The pipeline writes via SPARQL `INSERT DATA`:

```turtle
:Snap_AAPL_Sent_20260805 a :ScoreSnapshot ;
    :agentOrigin "SEMANTIC" ; :metricType "Sentiment" ;
    :normalizedScore "0.83"^^xsd:decimal ; :timestamp "2026-08-05T09:00:00"^^xsd:dateTime .
    # Corrected 2026-08-23: this example previously showed metricType "NEWS_SENTIMENT_FINBERT",
    # a value never actually used anywhere in schema/rules.ttl or instances.trig -- every real
    # Sentiment ScoreSnapshot uses plain "Sentiment" (now enforced by shapes.ttl's sh:in on
    # metricType, see 06-ontology-definition.md §1.9). Fixed to match the real convention rather
    # than leaving this doc and the schema silently disagreeing with each other.

:Article_AAPL_20260805 a :NewsArticle ;
    :provenanceId "articles:48211" ;   # news-crawler's articles.id, itself FK'd to discovered_urls.id
    :sourceURL "https://finance.yahoo.com/..." .
```

`provenanceId` holds `"articles:<id>"` (or `"discovered_urls:<id>"` for rows not yet through
extraction) directly from the existing `news-collector`/`news-crawler` SQLite pipeline, and an
accession-number-based id for `SECFilingSection`. Joining a graph individual back to its full
fetch/discovery history is a lookup in an existing database, not a new identifier scheme.

---

*Diagram for this document (Exhibit 4) is in the companion Artifact: text → chunk → FinBERT
sentiment + NER (MRC-style, v1 spaCy fallback / v2 fine-tuned) → mean-pool / max-severity
aggregation → graph write.*
