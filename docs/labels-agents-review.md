# Block F label review — agent traceability (Work item 46, T-900–T-909)

Status: **pending Reviewer A**. The table lists the code, the Spanish label and the English label of every new class and property. The `domain` column is the shape that uses the property; `shared` means it is used by more than one block-F class (and has no `rdfs:domain`, so it cannot entail one disjoint leaf from another).

## Classes

| Code | ES | EN | Definition (EN) |
|---|---|---|---|
| `:ManagerCall` | Llamada del gestor | Manager Call | One A2g manager call: the stop it answers, the menu alternative chosen, the fallback and repair state, the model and skill hashes and a pointer to the source line. Prompts, raw answers and the whole state are never stored. |
| `:NarratorText` | Texto del narrador | Narrator Text | One narrator text for an event, keyed by (kind, date, asset_id). Model text is marked generated and carries the provenance sentence; template text is marked not generated. |
| `:NewsAction` | Acción de noticias | News Action | One pool action (veto or promotion) for a decision date and asset, with its evidence and the replacement links. Fills confirm the replacement; they do not create a second action. |
| `:NewsEvidence` | Evidencia de noticias | News Evidence | The asset-level evidence of one news action: counts, state, tier cells, test statistics, exact p-value and size fractions as integer numerator/denominator pairs, and a hash plus pointer for the nested base-rate table. |
| `:DateRecord` | Registro de fecha de noticias | News Date Record | One news decision date: coverage, admission and pool counts, pooled and expected fractions, the level-B/C/D state and the filter flags. The nested base-rate and level-C tables are hash plus pointer. |
| `:NewsRunRecord` | Registro de corrida de noticias | News Run Record | One news run per (label, window): mode, alpha, table hash, level-B exits, the detail-derived sector-rejection count and the number of decision dates. |
| `:BullModeRecord` | Registro del modo alcista | Bull Mode Record | One N11 bull-mode record per (label, window): the beta target, z* and formation date, with one decision per date. |
| `:BullModeDecision` | Decisión del modo alcista | Bull Mode Decision | One N11 decision date: evaluable, triggered, z, rung, t1 and the five n11 fields. |

## Properties

| Code | ES | EN | Type | Domain |
|---|---|---|---|---|
| `:agentRecordOfConfiguration` | Registro de configuración | Record of configuration | object | `:shared` |
| `:sourceDocument` | Documento de origen | Source document | datatype | `:shared` |
| `:sourceJsonPointer` | Puntero JSON de origen | Source JSON pointer | datatype | `:shared` |
| `:sourceLineNumber` | Número de línea de origen | Source line number | datatype | `:shared` |
| `:recordSourceSha256` | SHA-256 de origen | Source SHA-256 | datatype | `:shared` |
| `:promptSha256` | SHA-256 del prompt | Prompt SHA-256 | datatype | `:shared` |
| `:validatorPassed` | Validador superado | Validator passed | datatype | `:shared` |
| `:validatorDetail` | Detalle del validador | Validator detail | datatype | `:shared` |
| `:modelRequested` | Modelo solicitado | Model requested | datatype | `:shared` |
| `:modelResolved` | Modelo resuelto | Model resolved | datatype | `:shared` |
| `:providerModelRevision` | Revisión del modelo del proveedor | Provider model revision | datatype | `:shared` |
| `:reasoningEffort` | Esfuerzo de razonamiento | Reasoning effort | datatype | `:shared` |
| `:reasoningEffortUsed` | Se usó esfuerzo de razonamiento | Reasoning effort used | datatype | `:shared` |
| `:newsBaseRatesSha256` | SHA-256 de las tasas base | Base rates SHA-256 | datatype | `:shared` |
| `:newsTestRow` | Fila de prueba de noticias | News test row | datatype | `:shared` |
| `:callIndex` | Índice de llamada | Call index | datatype | `:ManagerCall` |
| `:agentArm` | Brazo del agente | Agent arm | datatype | `:ManagerCall` |
| `:callOfStop` | Llamada de la parada | Call of stop | object | `:ManagerCall` |
| `:callStoppedAssetId` | Id de activo detenido del motor | Stopped engine asset id | datatype | `:ManagerCall` |
| `:answerAsset` | Activo de la respuesta | Answer asset | object | `:ManagerCall` |
| `:answerLabel` | Etiqueta de la respuesta | Answer label | datatype | `:ManagerCall` |
| `:answerSizeFraction` | Fracción de tamaño de la respuesta | Answer size fraction | datatype | `:ManagerCall` |
| `:answerIsCash` | La respuesta es efectivo | Answer is cash | datatype | `:ManagerCall` |
| `:answerIsSpy` | La respuesta es SPY | Answer is SPY | datatype | `:ManagerCall` |
| `:chosenAsset` | Activo elegido | Chosen asset | object | `:ManagerCall` |
| `:chosenSizeFraction` | Fracción de tamaño elegida | Chosen size fraction | datatype | `:ManagerCall` |
| `:fallbackUsedRule` | El respaldo usó la regla | Fallback used rule | datatype | `:ManagerCall` |
| `:fallbackUsedCash` | El respaldo usó efectivo | Fallback used cash | datatype | `:ManagerCall` |
| `:fallbackCause` | Causa del respaldo | Fallback cause | datatype | `:ManagerCall` |
| `:fallbackDetail` | Detalle del respaldo | Fallback detail | datatype | `:ManagerCall` |
| `:repairUsed` | Se usó reparación | Repair used | datatype | `:ManagerCall` |
| `:repairCause` | Causa de la reparación | Repair cause | datatype | `:ManagerCall` |
| `:repairDetail` | Detalle de la reparación | Repair detail | datatype | `:ManagerCall` |
| `:promptTemplateSha256` | SHA-256 de la plantilla del prompt | Prompt template SHA-256 | datatype | `:ManagerCall` |
| `:systemPromptSha256` | SHA-256 del prompt de sistema | System prompt SHA-256 | datatype | `:ManagerCall` |
| `:userPromptSha256` | SHA-256 del prompt de usuario | User prompt SHA-256 | datatype | `:ManagerCall` |
| `:firstRawAnswerSha256` | SHA-256 de la primera respuesta cruda | First raw answer SHA-256 | datatype | `:ManagerCall` |
| `:rawAnswerSha256` | SHA-256 de la respuesta cruda | Raw answer SHA-256 | datatype | `:ManagerCall` |
| `:rawMessageSha256` | SHA-256 del mensaje crudo | Raw message SHA-256 | datatype | `:ManagerCall` |
| `:toolOutputsSha256` | SHA-256 de las salidas de herramientas | Tool outputs SHA-256 | datatype | `:ManagerCall` |
| `:shuffleSeed` | Semilla de mezcla | Shuffle seed | datatype | `:ManagerCall` |
| `:toolOrder` | Orden de herramientas | Tool order | datatype | `:ManagerCall` |
| `:finishReason` | Razón de finalización | Finish reason | datatype | `:ManagerCall` |
| `:turnCount` | Número de turnos | Turn count | datatype | `:ManagerCall` |
| `:attemptCount` | Número de intentos | Attempt count | datatype | `:ManagerCall` |
| `:usageInputTokens` | Tokens de entrada usados | Usage input tokens | datatype | `:ManagerCall` |
| `:usageOutputTokens` | Tokens de salida usados | Usage output tokens | datatype | `:ManagerCall` |
| `:usageTotalTokens` | Tokens totales usados | Usage total tokens | datatype | `:ManagerCall` |
| `:validatorCause` | Causa del validador | Validator cause | datatype | `:ManagerCall` |
| `:firstValidatorPassed` | Primer validador superado | First validator passed | datatype | `:ManagerCall` |
| `:firstValidatorCause` | Causa del primer validador | First validator cause | datatype | `:ManagerCall` |
| `:skillPath` | Ruta de la skill | Skill path | datatype | `:ManagerCall` |
| `:skillFileSha256` | SHA-256 del archivo de la skill | Skill file SHA-256 | datatype | `:ManagerCall` |
| `:skillPolicySha256` | SHA-256 de la política de la skill | Skill policy SHA-256 | datatype | `:ManagerCall` |
| `:narratorKind` | Tipo de narrador | Narrator kind | datatype | `:NarratorText` |
| `:narratorText` | Texto del narrador | Narrator text | datatype | `:NarratorText` |
| `:narratorSource` | Origen del narrador | Narrator source | datatype | `:NarratorText` |
| `:narratorOfStop` | Narrador de la parada | Narrator of stop | object | `:NarratorText` |
| `:sourceKind` | Tipo de origen | Source kind | datatype | `:NarratorText` |
| `:sourceDate` | Fecha de origen | Source date | datatype | `:NarratorText` |
| `:sourceAssetId` | Id de activo de origen | Source asset id | datatype | `:NarratorText` |
| `:sourceEventLine` | Línea del evento de origen | Source event line | datatype | `:NarratorText` |
| `:templateSha256` | SHA-256 de la plantilla | Template SHA-256 | datatype | `:NarratorText` |
| `:omittedField` | Campo omitido | Omitted field | datatype | `:NarratorText` |
| `:newsActionKind` | Tipo de acción de noticias | News action kind | datatype | `:NewsAction` |
| `:newsActionAsset` | Activo de la acción de noticias | News action asset | object | `:NewsAction` |
| `:newsActionTicker` | Ticker de la acción de noticias | News action ticker | datatype | `:NewsAction` |
| `:newsActionOfDateRecord` | Registro de fecha de la acción | News action date record | object | `:NewsAction` |
| `:newsActionOfRun` | Corrida de la acción de noticias | News action run | object | `:NewsAction` |
| `:newsReplacesAsset` | Activo reemplazado | Replaces asset | object | `:NewsAction` |
| `:newsReplacedByAsset` | Activo que la reemplaza | Replaced by asset | object | `:NewsAction` |
| `:newsActionEvidence` | Evidencia de la acción de noticias | News action evidence | object | `:NewsAction` |
| `:newsActionFilled` | Acción de noticias ejecutada | News action filled | datatype | `:NewsAction` |
| `:newsActionFillAsset` | Activo del fill de noticias | News action fill asset | object | `:NewsAction` |
| `:newsEvidenceOfAction` | Acción de la evidencia | News evidence action | object | `:NewsEvidence` |
| `:newsEvidenceAsset` | Activo de la evidencia | News evidence asset | object | `:NewsEvidence` |
| `:newsEvidenceTicker` | Ticker de la evidencia | News evidence ticker | datatype | `:NewsEvidence` |
| `:newsEvidenceState` | Estado de la evidencia | News evidence state | datatype | `:NewsEvidence` |
| `:newsN` | Noticias n | News n | datatype | `:NewsEvidence` |
| `:newsA` | Noticias a | News a | datatype | `:NewsEvidence` |
| `:newsB` | Noticias b | News b | datatype | `:NewsEvidence` |
| `:newsCovered` | Noticias cubiertas | News covered | datatype | `:NewsEvidence` |
| `:meanProbabilityMargin` | Margen medio de probabilidad | Mean probability margin | datatype | `:NewsEvidence` |
| `:newsNegativeTier1` | Negativas nivel 1 | Negative tier 1 | datatype | `:NewsEvidence` |
| `:newsNegativeTier2` | Negativas nivel 2 | Negative tier 2 | datatype | `:NewsEvidence` |
| `:newsNeutralTier1` | Neutras nivel 1 | Neutral tier 1 | datatype | `:NewsEvidence` |
| `:newsNeutralTier2` | Neutras nivel 2 | Neutral tier 2 | datatype | `:NewsEvidence` |
| `:newsPositiveTier1` | Positivas nivel 1 | Positive tier 1 | datatype | `:NewsEvidence` |
| `:newsPositiveTier2` | Positivas nivel 2 | Positive tier 2 | datatype | `:NewsEvidence` |
| `:newsStatisticNegative` | Estadístico negativo | Test statistic negative | datatype | `:NewsEvidence` |
| `:newsStatisticPositive` | Estadístico positivo | Test statistic positive | datatype | `:NewsEvidence` |
| `:newsCriticalNegative` | Crítico negativo | Critical negative | datatype | `:NewsEvidence` |
| `:newsCriticalPositive` | Crítico positivo | Critical positive | datatype | `:NewsEvidence` |
| `:newsPNegativeNumerator` | Numerador del valor p negativo | p-value negative numerator | datatype | `:NewsEvidence` |
| `:newsPNegativeDenominator` | Denominador del valor p negativo | p-value negative denominator | datatype | `:NewsEvidence` |
| `:newsPPositiveNumerator` | Numerador del valor p positivo | p-value positive numerator | datatype | `:NewsEvidence` |
| `:newsPPositiveDenominator` | Denominador del valor p positivo | p-value positive denominator | datatype | `:NewsEvidence` |
| `:newsSizeNegativeNumerator` | Numerador del tamaño negativo | Size negative numerator | datatype | `:NewsEvidence` |
| `:newsSizeNegativeDenominator` | Denominador del tamaño negativo | Size negative denominator | datatype | `:NewsEvidence` |
| `:newsSizePositiveNumerator` | Numerador del tamaño positivo | Size positive numerator | datatype | `:NewsEvidence` |
| `:newsSizePositiveDenominator` | Denominador del tamaño positivo | Size positive denominator | datatype | `:NewsEvidence` |
| `:newsConflict` | Conflicto de noticias | News conflict | datatype | `:NewsEvidence` |
| `:newsPromotionCandidate` | Candidata a promoción | Promotion candidate | datatype | `:NewsEvidence` |
| `:newsVetoCandidate` | Candidata a veto | Veto candidate | datatype | `:NewsEvidence` |
| `:newsTestSha256` | SHA-256 de la prueba de noticias | News test SHA-256 | datatype | `:NewsEvidence` |
| `:newsTestPointer` | Puntero de la prueba de noticias | News test pointer | datatype | `:NewsEvidence` |
| `:dateRecordDate` | Fecha del registro | Date record date | datatype | `:DateRecord` |
| `:dateRecordOfRun` | Corrida del registro de fecha | Date record run | object | `:DateRecord` |
| `:dateRecordOfBullDecision` | Decisión alcista del registro | Date record bull decision | object | `:DateRecord` |
| `:coverageFirst` | Primera cobertura | Coverage first | datatype | `:DateRecord` |
| `:coverageLast` | Última cobertura | Coverage last | datatype | `:DateRecord` |
| `:hasTemporalCoverage` | Tiene cobertura temporal | Has temporal coverage | datatype | `:DateRecord` |
| `:admittedCount` | Conteo admitido | Admitted count | datatype | `:DateRecord` |
| `:admittedInBaseWindow` | Admitidas en la ventana base | Admitted in base window | datatype | `:DateRecord` |
| `:admittedInEvidenceWindow` | Admitidas en la ventana de evidencia | Admitted in evidence window | datatype | `:DateRecord` |
| `:completePool` | Pool completo | Complete pool | datatype | `:DateRecord` |
| `:sentimentChecked` | Sentimiento revisado | Sentiment checked | datatype | `:DateRecord` |
| `:sentimentCheckedKnown` | Sentimiento revisado conocido | Sentiment checked known | datatype | `:DateRecord` |
| `:missingBodyHash` | Hash de cuerpo faltante | Missing body hash | datatype | `:DateRecord` |
| `:undatedCount` | Conteo sin fecha | Undated count | datatype | `:DateRecord` |
| `:untickeredCount` | Conteo sin ticker | Untickered count | datatype | `:DateRecord` |
| `:droppedCondition` | Condición descartada | Dropped condition | datatype | `:DateRecord` |
| `:surplusPromotionCount` | Conteo de promociones excedentes | Surplus promotion count | datatype | `:DateRecord` |
| `:rejectedDuplicate` | Rechazadas duplicadas | Rejected duplicate | datatype | `:DateRecord` |
| `:baseRatePooledNegativeNumerator` | Numerador negativo agrupado | Pooled negative numerator | datatype | `:DateRecord` |
| `:baseRatePooledNegativeDenominator` | Denominador negativo agrupado | Pooled negative denominator | datatype | `:DateRecord` |
| `:baseRatePooledPositiveNumerator` | Numerador positivo agrupado | Pooled positive numerator | datatype | `:DateRecord` |
| `:baseRatePooledPositiveDenominator` | Denominador positivo agrupado | Pooled positive denominator | datatype | `:DateRecord` |
| `:baseRateTotalRows` | Filas totales de tasas base | Base-rate total rows | datatype | `:DateRecord` |
| `:baseRateSignalPossible` | Señal de tasa base posible | Base-rate signal possible | datatype | `:DateRecord` |
| `:expectedTotalNumerator` | Numerador total esperado | Expected total numerator | datatype | `:DateRecord` |
| `:expectedTotalDenominator` | Denominador total esperado | Expected total denominator | datatype | `:DateRecord` |
| `:expectedNegativeNumerator` | Numerador negativo esperado | Expected negative numerator | datatype | `:DateRecord` |
| `:expectedNegativeDenominator` | Denominador negativo esperado | Expected negative denominator | datatype | `:DateRecord` |
| `:expectedPositiveNumerator` | Numerador positivo esperado | Expected positive numerator | datatype | `:DateRecord` |
| `:expectedPositiveDenominator` | Denominador positivo esperado | Expected positive denominator | datatype | `:DateRecord` |
| `:expectedLowerBound` | Cota inferior esperada | Expected lower bound | datatype | `:DateRecord` |
| `:expectedTests` | Pruebas esperadas | Expected tests | datatype | `:DateRecord` |
| `:levelBThreshold` | Umbral del nivel B | Level B threshold | datatype | `:DateRecord` |
| `:levelCDecision` | Nivel C marcado | Level C flagged | datatype | `:DateRecord` |
| `:levelCFlaggedCount` | Conteo marcado del nivel C | Level C flagged count | datatype | `:DateRecord` |
| `:levelDFired` | Nivel D disparado | Level D fired | datatype | `:DateRecord` |
| `:levelDTone21` | Tono del nivel D a 21 | Level D tone 21 | datatype | `:DateRecord` |
| `:levelDP20` | Nivel D p20 | Level D p20 | datatype | `:DateRecord` |
| `:filterPriceFlag` | Flag de filtro de precio | Filter price flag | datatype | `:DateRecord` |
| `:filterNewsFlag` | Flag de filtro de noticias | Filter news flag | datatype | `:DateRecord` |
| `:newsLevelCDecisionsSha256` | SHA-256 de las decisiones del nivel C | Level C decisions SHA-256 | datatype | `:DateRecord` |
| `:dateRecordAction` | Acción del registro de fecha | Date record action | object | `:DateRecord` |
| `:newsMode` | Modo de noticias | News mode | datatype | `:NewsRunRecord` |
| `:newsAlpha` | Alfa de noticias | News alpha | datatype | `:NewsRunRecord` |
| `:newsTableSha256` | SHA-256 de la tabla de noticias | News table SHA-256 | datatype | `:NewsRunRecord` |
| `:newsExits` | Salidas por noticias | News exits | datatype | `:NewsRunRecord` |
| `:newsSectorRejections` | Rechazos por sector de noticias | News sector rejections | datatype | `:NewsRunRecord` |
| `:newsDateCount` | Conteo de fechas de noticias | News date count | datatype | `:NewsRunRecord` |
| `:newsRunSessions` | Sesiones de la corrida de noticias | News run sessions | datatype | `:NewsRunRecord` |
| `:bullModeName` | Modo alcista | Bull mode | datatype | `:BullModeRecord` |
| `:bullBetaTarget` | Meta de beta alcista | Bull beta target | datatype | `:BullModeRecord` |
| `:bullZStar` | z* alcista | Bull z* | datatype | `:BullModeRecord` |
| `:bullFormationDate` | Fecha de formación alcista | Bull formation date | datatype | `:BullModeRecord` |
| `:bullTriggeredCount` | Conteo de disparos alcistas | Bull triggered count | datatype | `:BullModeRecord` |
| `:bullDecision` | Decisión alcista | Bull decision | object | `:BullModeRecord` |
| `:bullDecisionDate` | Fecha de la decisión alcista | Bull decision date | datatype | `:BullModeDecision` |
| `:bullDecisionOfRecord` | Registro de la decisión alcista | Bull decision record | object | `:BullModeDecision` |
| `:bullEvaluable` | Alcista evaluable | Bull evaluable | datatype | `:BullModeDecision` |
| `:bullTriggered` | Alcista disparado | Bull triggered | datatype | `:BullModeDecision` |
| `:bullZ` | z alcista | Bull z | datatype | `:BullModeDecision` |
| `:bullRung` | Peldaño alcista | Bull rung | datatype | `:BullModeDecision` |
| `:bullT1` | t1 alcista | Bull t1 | datatype | `:BullModeDecision` |
| `:bullSignalCount` | Conteo de señales alcistas | Bull signal count | datatype | `:BullModeDecision` |
| `:bullN11BetaSat` | Beta sat N11 | N11 beta sat | datatype | `:BullModeDecision` |
| `:bullN11CoreWeight` | Peso del núcleo N11 | N11 core weight | datatype | `:BullModeDecision` |
| `:bullN11Evaluable` | N11 evaluable | N11 evaluable | datatype | `:BullModeDecision` |
| `:bullN11ExAnteBeta` | Beta ex-ante N11 | N11 ex-ante beta | datatype | `:BullModeDecision` |
| `:newsItem` | Noticia | News item | object | `:NewsEvidence` |

## Reused existing properties

These are not redefined in the block; their existing labels are reused. `:generatedByLanguageModel` and `:provenanceNote` widen their domain to a union that includes the new classes, and `:poolSize` keeps its existing no-domain definition.

| Code | ES | EN | Type | Existing domain |
|---|---|---|---|---|
| `:knowledgeDate` |  |  | datatype | `shared` |
| `:windowId` |  |  | datatype | `shared` |
| `:runId` |  |  | datatype | `shared` |
| `:poolSize` | Tamaño del grupo de candidatas | Candidate-pool size | datatype | `shared` |
| `:generatedByLanguageModel` | Generado por un modelo de lenguaje | Generated by language model | datatype | `shared` |
| `:provenanceNote` | Nota de procedencia | Provenance note | datatype | `shared` |

## Review notes

- Every new class is an `:Observation` leaf in a second `owl:AllDisjointClasses` block at the end of `tbox.ttl`; the existing blocks are untouched.

- Every new shape is closed (`sh:closed true`, `rdf:type` ignored) and lists the shared source pointer properties; there is one extra `:AgentRecordNoPriceShape` that refuses `:closePrice`, `:stop`, `:alertValue` and the other price properties on the eight classes.

- `:NewsEvidence` stores exact fractions as integer numerator/denominator pairs and one `:newsItem` link per test row; no p-value or size is stored as a float.

- `:providerModelRevision` is this block’s property; master's `:modelRevision` stays on `:NewsItem`.

