# English comment review for the bilingual labels (Work item 43, T-755)

**Status: awaiting Reviewer A. No English comment is frozen until every row is approved or changed.**
Source: `schema/labels.ttl`, `schema/rules.ttl`, `schema/tbox.ttl` and
`schema/reference.ttl` at the commit that adds this file.

These are the English drafts translated from the Spanish comments in the schema. The Spanish is the
approved glossary text; the English keeps every number, formula, date and proper name. A row is
approved by writing `approved` in the last column, or changed with
`change requested: <text>`. T-756 copies only approved rows into the schema and runs the final audit.

Rules for this review:

- No Tiingo licence note and no Grossman-Zhou mention.
- `L4_DD` must say **all the reference weights, including the SPY core**, and that the reference is
  the twin arm without GUARD.
- `objective` keeps the Work item 41 facts and the label **Registered optimization class**; the
  external `max_sharpe` note is pending Reviewer A.
- `BREAK_TREND_200` is a flag, never a veto.
- The final store has only `final`; `rule` and `candidate_y2` do not appear.
- The mean-variance base is `MARKOWITZ_MV`; only it may be called "Markowitz base".

### WindowScheme

| id | code / IRI | ES comment | EN draft | Reviewer A decision | Notes |
|---|---|---|---|---|---|
| WIN-01 | P1 (Window_1) | Una ventana del backtest final, nombrada por número de calendario y fechas. | A window of the final backtest, named by calendar number and dates. |  |  |
| WIN-02 | H1 (Window_2) | Una ventana del backtest final, nombrada por número de calendario y fechas. | A window of the final backtest, named by calendar number and dates. |  |  |
| WIN-03 | P3 (Window_3) | Una ventana del backtest final, nombrada por número de calendario y fechas. | A window of the final backtest, named by calendar number and dates. |  |  |
| WIN-04 | H2 (Window_4) | Una ventana del backtest final, nombrada por número de calendario y fechas. | A window of the final backtest, named by calendar number and dates. |  |  |
| WIN-05 | P2 (Window_5) | La quinta ventana neutral; su escenario no está etiquetado. | The neutral fifth window; its scenario is not labelled. |  |  |
| WIN-06 | H3 (Window_6) | Una ventana del backtest final, nombrada por número de calendario y fechas. | A window of the final backtest, named by calendar number and dates. |  |  |

### RunLabelScheme

| id | code / IRI | ES comment | EN draft | Reviewer A decision | Notes |
|---|---|---|---|---|---|
| RUN-01 | final (RunLabel_final) | La entrega final_corregida (code_commit 5958c6b): seis ventanas, todos los resultados dentro de muestra; etiqueta predeterminada para los resultados finales. | The delivery final_corregida (code_commit 5958c6b): six windows, all results in-sample; the default run label for final results. |  |  |

### StrategyScheme

| id | code / IRI | ES comment | EN draft | Reviewer A decision | Notes |
|---|---|---|---|---|---|
| ARM-01 | MARKOWITZ_BASE (Strategy_MinVarianceLedoitWolf) | Cartera de mínima varianza sobre los miembros elegibles del S&P 500, solo largos, máximo 5 % por acción y 30 % por sector, con covarianza con contracción de Ledoit-Wolf; no estima retornos esperados; sin SPY, filtro ni selección. | Minimum-variance portfolio over the eligible S&P 500 members, long-only, at most 5% per stock and 30% per sector, with Ledoit-Wolf shrinkage covariance; it does not estimate expected returns; no SPY, trend filter or selection. |  |  |
| ARM-02 | MARKOWITZ_BASE_GUARD (Strategy_MinVarianceLedoitWolfGuard) | La cartera de mínima varianza (Ledoit-Wolf) con la supervisión GUARD (parada de 21 sesiones por acción y escalamiento por caída). | The Ledoit-Wolf minimum-variance portfolio with GUARD supervision (21-session per-stock stop and drawdown scaling). |  |  |
| ARM-03 | MARKOWITZ_MV (Strategy_MeanVarianceBase) | Solo se cargan resúmenes por ventana y segmento (sin serie diaria, pesos ni alertas); calculada fuera del motor por un simulador independiente validado contra el libro MARKOWITZ_BASE del motor; resultados dentro de muestra; sin GUARD. | Only per-window and segment summaries are loaded (no daily series, weights or alerts); computed outside the engine by an independent simulator validated against the engine MARKOWITZ_BASE book; in-sample; no GUARD. |  |  |
| ARM-04 | TOPN_MV_GUARD_NO_NLP (Strategy_System) | Mandato nominal de 50 % en SPY y 50 % en hasta 30 acciones del grupo de 60 candidatas elegibles (puntajes técnico, de valoración y fundamental con vetos), ponderadas por mínimo CVaR con tope por nombre de 1.5 dividido entre el número de acciones, filtro de tendencia y supervisión GUARD; la composición realizada difiere del mandato nominal. | Nominal mandate of 50% SPY and 50% in up to 30 stocks from the 60-name eligible candidate pool (technical, valuation and fundamental scores with vetoes), weighted by minimum CVaR with a per-name cap of 1.5 divided by the number of stocks, trend filter and GUARD supervision; the realized composition differs from the nominal mandate. |  |  |
| ARM-05 | TOPN_MV_NOGUARD (Strategy_SystemNoGuard) | El Sistema sin la supervisión GUARD. | The System without GUARD supervision. |  |  |

### GuardScheme

| id | code / IRI | ES comment | EN draft | Reviewer A decision | Notes |
|---|---|---|---|---|---|
| GRD-01 | 1 (GuardLayer_1) | Determina la salida de una posición cuando se cumple la regla de capa 1 y permite una reentrada posterior cuando se satisface su condición de recuperación; depende del libro: Basing Points en el Sistema, límite de pérdida de 21 sesiones en el Markowitz con GUARD. | Determines the exit of a position when its layer-1 rule fires and allows a later re-entry when its recovery condition is met; it depends on the book: Basing Points in the System, a 21-session loss limit in the Markowitz book with GUARD. |  |  |
| GRD-02 | 2 (GuardLayer_2) | Recortaría posiciones por noticias negativas; está apagada. | Would trim positions on negative news; it is disabled. |  |  |
| GRD-03 | 3 (GuardLayer_3) | Reduciría la exposición si sube la volatilidad; configurado pero sin activaciones observadas. | Would reduce exposure when volatility rises; configured but no activations were observed. |  |  |
| GRD-04 | 4 (GuardLayer_4) | Multiplica todos los pesos de referencia, incluido el núcleo SPY, por clip(m*(VP - alfa*VPmax)/VP, 0, 1); vale 1 en el máximo y baja con la caída. | Multiplies all the reference weights, including the SPY core, by clip(m*(VP - alpha*VPmax)/VP, 0, 1); it is 1 at the peak and falls with drawdown. |  |  |
| GRD-05 | ACTIVE (AlertState_ACTIVE) | La regla está vigente; puede no aparecer en la corrida final. | The rule is in effect; it may not appear in the final run. |  |  |
| GRD-06 | APPLIED (ActionStatus_APPLIED) | El libro aplicó la acción asociada a la alerta; es una aplicación de una regla del motor, no una orden ejecutada en el mercado. | The book applied the action associated with the alert; it is an engine-rule application, not a market order. |  |  |
| GRD-07 | ARM_DISABLED (ActionStatus_ARM_DISABLED) | El brazo no tiene GUARD; la alerta es solo informativa. | The arm has no GUARD; the alert is informative only. |  |  |
| GRD-08 | COOLDOWN (AlertState_COOLDOWN) | La regla está en un período de enfriamiento; puede no aparecer en la corrida final. | The rule is in a cool-down period; it may not appear in the final run. |  |  |
| GRD-09 | ENTER (AlertState_ENTER) | La regla pasó a estar activa. No es una orden de compra o venta. | The rule became active. It is not a buy or sell order. |  |  |
| GRD-10 | EXIT (AlertState_EXIT) | La regla dejó de estar activa. No es una venta. | The rule stopped being active. It is not a sale. |  |  |
| GRD-11 | GUARD (GuardSupervision) | Reglas que reducen o cierran posiciones entre rebalanceos para limitar pérdidas. | Rules that reduce or close positions between rebalances to limit losses. |  |  |
| GRD-12 | NOT_HELD (ActionStatus_NOT_HELD) | El libro no tenía el activo. | The book did not hold the asset. |  |  |
| GRD-13 | SCALE (AlertState_SCALE) | La exposición total se escaló por las capas 3 o 4. | Total exposure was scaled by layers 3 or 4. |  |  |
| GRD-14 | SUPERSEDED (ActionStatus_SUPERSEDED) | Otra alerta la reemplazó. | Another alert replaced this one. |  |  |

### VetoClassScheme

| id | code / IRI | ES comment | EN draft | Reviewer A decision | Notes |
|---|---|---|---|---|---|
| VCL-01 | HARD (VetoClass_Hard) | Tiene al menos un veto duro y queda excluida del universo elegible mientras la condición esté vigente. | The asset has at least one hard veto and is excluded from the eligible universe while the condition holds. |  |  |
| VCL-02 | INDICATOR (VetoClass_Indicator) | Marca el activo pero no lo excluye ni resta puntos; BREAK_TREND_200 es el único miembro. | Marks the asset but neither excludes it nor subtracts points; BREAK_TREND_200 is the only member. |  |  |
| VCL-03 | SOFT (VetoClass_Soft) | Resta puntos al puntaje combinado; el activo sigue elegible. | Subtracts points from the combined score; the asset remains eligible. |  |  |

### MarkerScheme

| id | code / IRI | ES comment | EN draft | Reviewer A decision | Notes |
|---|---|---|---|---|---|
| MRK-01 | HARD (Marker_HARD) | Marcador de ranking de un veto duro o de un token HARD en el JSON. | The ranking marker for a hard veto or a hard-veto JSON token. |  |  |
| MRK-02 | NO_RISK_MODEL (Marker_NO_RISK_MODEL) | No hay retornos suficientes para el modelo de riesgo; es una causa de inelegibilidad, no un veto del catálogo, y no está cargada como literal en el grafo final. | Not enough returns for the risk model; this is an ineligibility cause, not a catalog veto, and it is not loaded as a literal in the final graph. |  |  |
| MRK-03 | UNPRICED (Marker_UNPRICED) | No hay precios suficientes. | There is not enough price history. |  |  |
| MRK-04 | UNSCORED (Marker_UNSCORED) | El activo nunca tuvo puntaje fundamental; es inelegible, no penalizado. | The asset never had a fundamental score; it is ineligible, not penalized. |  |  |

### ScoreComponentScheme

| id | code / IRI | ES comment | EN draft | Reviewer A decision | Notes |
|---|---|---|---|---|---|
| SCR-01 | FUNDAMENTAL (ScoreComponent_FUNDAMENTAL) | Se calcula por informe financiero trimestral. | Computed from each quarterly financial report. |  |  |
| SCR-02 | SECTOR (ScoreComponent_SECTOR) | Puntaje técnico bruto de la acción menos el promedio de su sector GICS en la fecha; diagnóstico, no entra en el puntaje combinado. | The asset technical raw score minus its GICS sector mean on the date; a diagnostic, not part of the combined score. |  |  |
| SCR-03 | TECHNICAL (ScoreComponent_TECHNICAL) | Tendencia y momentum de precios. | Price trend and momentum. |  |  |
| SCR-04 | VALORIZATION (ScoreComponent_VALORIZATION) | Múltiplos de valoración. | Valuation multiples. |  |  |

### RankScheme

| id | code / IRI | ES comment | EN draft | Reviewer A decision | Notes |
|---|---|---|---|---|---|
| RNK-01 | rank (RankColumn_Raw) | Orden por puntaje combinado sobre todos los miembros clasificados de la fecha, incluidas las vetadas. | Order by combined score over every classified member of the date, including vetoed names. |  |  |
| RNK-02 | rank_e (RankColumn_Eligible) | Orden por puntaje combinado solo entre elegibles; no está cargada como columna en el grafo final, así que nunca debe estimarse ni sustituirse. | Order by combined score among eligible names only; not loaded as a column in the final graph, so it must never be estimated or substituted. |  |  |

### ConfigScheme

| id | code / IRI | ES comment | EN draft | Reviewer A decision | Notes |
|---|---|---|---|---|---|
| CFG-01 | blend (Config_blend) | Interno; ocultar en respuestas ordinarias. | Internal; hide in ordinary answers. |  |  |
| CFG-02 | core_weight (Config_core_weight) | Núcleo SPY nominal del 50 %. | Nominal 50% SPY core. |  |  |
| CFG-03 | cost_bps (Config_cost_bps) | 10 puntos básicos, aplicados a la suma de los cambios absolutos de peso en acciones. | 10 basis points, applied to the sum of absolute equity-weight changes. |  |  |
| CFG-04 | cov_estimator (Config_cov_estimator) | Covarianza Ledoit-Wolf con correlación constante. | Ledoit-Wolf constant-correlation covariance. |  |  |
| CFG-05 | cvar_scenarios (Config_cvar_scenarios) | El modelo de riesgo guarda retornos logarítmicos; el optimizador los convierte a simples. | The risk model stores log returns; the optimizer converts them to simple returns. |  |  |
| CFG-06 | exclude_hard_vetoed (Config_exclude_hard_vetoed) | Vale 0 también en el Sistema porque el modelo compartido incluye los vetados; el Sistema excluye los vetos duros antes, en la preselección. Nunca decir que el Sistema no excluye empresas con veto duro. | It is 0 also in the System because the shared model includes vetoed names; the System excludes hard vetoes earlier, in the preselection. Never say the System does not exclude hard-vetoed companies. |  |  |
| CFG-07 | filter_exit (Config_filter_exit) | Con SPY por debajo de su media de 210 sesiones, cada peso objetivo se multiplica por (1 - filter_exit); 0.5 mueve la mitad de la exposición a efectivo. | With SPY below its 210-session mean, each target weight is multiplied by (1 - filter_exit); 0.5 moves half the exposure to cash. |  |  |
| CFG-08 | lookback (Config_lookback) | 756 sesiones de retorno. | 756 return sessions. |  |  |
| CFG-09 | min_history (Config_min_history) | 740 sesiones de retorno. | 740 return sessions. |  |  |
| CFG-10 | min_var (Config_objective_min_var) | Etiqueta fija que el motor escribe para cada brazo optimizado; NO es la función objetivo de ponderación del satélite (usar satellite_weighting, mincvar en el Sistema). La confirmación de upstream está pendiente. | The fixed label the engine writes for every optimized arm; it is NOT the satellite weighting objective (use satellite_weighting, mincvar in the System). Upstream confirmation is pending. |  |  |
| CFG-11 | news_db (Config_news_db) | Interno; ocultar en respuestas ordinarias. | Internal; hide in ordinary answers. |  |  |
| CFG-12 | news_model (Config_news_model) | Interno; ocultar en respuestas ordinarias. | Internal; hide in ordinary answers. |  |  |
| CFG-13 | pool_m (Config_pool_m) | 60 nombres. | 60 names. |  |  |
| CFG-14 | returns_members (Config_returns_members) | El panel antiguo as-of usaba los miembros al final de la ventana. | The old as-of panel used the members at the end of the window. |  |  |
| CFG-15 | rp (Config_rp) | Interno; ocultar en respuestas ordinarias. | Internal; hide in ordinary answers. |  |  |
| CFG-16 | satellite_weighting (Config_satellite_weighting) | Ponderación efectiva del satélite (mincvar en el Sistema); no es objective. | The effective satellite weighting (mincvar in the System); it is not objective. |  |  |
| CFG-17 | shadow_from (Config_shadow_from) | Interno; ocultar en respuestas ordinarias. | Internal; hide in ordinary answers. |  |  |
| CFG-18 | stop_rule (Config_stop_rule) | Basing Points variante 4 para la capa 1 del Sistema. | Basing Points variant 4 for the System layer 1. |  |  |
| CFG-19 | tilt (Config_tilt) | Interno; ocultar en respuestas ordinarias. | Internal; hide in ordinary answers. |  |  |
| CFG-20 | top_n (Config_top_n) | 30; no es el número real mantenido. | 30; it is not the number actually held. |  |  |
| CFG-21 | trend_filter (Config_trend_filter) | Se evalúa en la fecha de decisión y rige hasta la siguiente; afecta al núcleo y al satélite del Sistema, no a toda estrategia. | Evaluated at the decision date and in force until the next one; it affects the System core and satellite, not every strategy. |  |  |
| CFG-22 | vol_target (Config_vol_target) | Configurado; la capa no tuvo actividad. | Configured; the layer had no activity. |  |  |

### ProcessScheme

| id | code / IRI | ES comment | EN draft | Reviewer A decision | Notes |
|---|---|---|---|---|---|
| PRC-01 | BENCHMARK (Process_BENCHMARK) | Estrategia de comparación; ver el vocabulario de estrategias. | A comparison strategy; see the strategy vocabulary. |  |  |
| PRC-02 | CANDIDATE_POOL (Process_CANDIDATE_POOL) | En el Sistema y las variantes multifactoriales, las 60 mejores por posición entre elegibles; no es el número de acciones finalmente mantenidas. | In the System and the multifactor variants, the top 60 by eligible rank; it is not the number of stocks finally held. |  |  |
| PRC-03 | CONCEPTUAL_ANSWER (Process_CONCEPTUAL_ANSWER) | Una definición o explicación no necesita ventana, corrida ni regla de conteo. | A definition or explanation needs no window, run or counting rule. |  |  |
| PRC-04 | CORE_SATELLITE_CASH (Process_CORE_SATELLITE_CASH) | En el Sistema, núcleo SPY nominal del 50 % y satélite del 50 %; la exposición realizada puede diferir. | In the System, the nominal 50% SPY core and 50% satellite; the realized exposure can differ. |  |  |
| PRC-05 | COUNTING_RULE (Process_COUNTING_RULE) | Filas con fecha dentro de los límites de la ventana; las alertas del día de formación y los vetos del calentamiento se reportan aparte y se incluyen cuando se da el total de la ventana. | Rows whose date lies inside the window date range; formation-day alerts and warm-up vetoes are reported separately and included when a window total is given. |  |  |
| PRC-06 | CVAR_95 (Process_CVAR_95) | Pérdida media condicionada a estar en el 5 % de los peores retornos de la serie evaluada; indicar la frecuencia y la convención de signo. | Mean loss conditional on being in the worst 5% of the evaluated returns; state the return frequency and sign convention. |  |  |
| PRC-07 | DATA_NATURE (Process_DATA_NATURE) | Observado, calculado o derivado; una dimensión distinta del estado del dato. | Observed, calculated or derived; a different dimension from the data state. |  |  |
| PRC-08 | DATA_STATE (Process_DATA_STATE) | Disponible, no disponible, insuficiente, desactualizado o provisional. | Available, unavailable, insufficient, stale or provisional. |  |  |
| PRC-09 | DSR_PBO (Process_DSR_PBO) | Diagnósticos de selección y sobreajuste; no son pruebas de superioridad entre estrategias ni criterios automáticos de aceptación. | Selection and overfitting diagnostics; not superiority tests between strategies and not automatic acceptance criteria. |  |  |
| PRC-10 | ELIGIBLE_UNIVERSE (Process_ELIGIBLE_UNIVERSE) | Miembros del índice en la fecha que cumplen la disponibilidad de puntaje, precios y cobertura del modelo de riesgo y no tienen veto duro (vetoed = 0); elegible no significa que llegue a la cartera final. | Members on the date that have score, prices and risk-model coverage and no hard veto (vetoed = 0); eligibility does not mean the asset reaches the final book. |  |  |
| PRC-11 | FORMATION_DAY_ALERT (Process_FORMATION_DAY_ALERT) | Alerta de capa 1 fechada en la última sesión antes de la ventana; reportarla aparte de las alertas dentro de la ventana. | A layer-1 alert dated on the last session before the window; report it separately from the in-window alerts. |  |  |
| PRC-12 | GROSS_NET (Process_GROSS_NET) | El retorno neto descuenta los costos de transacción. | Net return subtracts transaction costs. |  |  |
| PRC-13 | IN_SAMPLE (Process_IN_SAMPLE) | Resultado de una ventana que se vio antes de elegir la configuración final. | A result from a window that was seen before the final configuration was chosen. |  |  |
| PRC-14 | MAX_SATELLITE (Process_MAX_SATELLITE) | Hasta 30; el número real de posiciones es menor. | At most 30; the actual number of positions is lower. |  |  |
| PRC-15 | MDD (Process_MDD) | Mayor caída porcentual desde un máximo acumulado hasta el mínimo posterior antes de recuperar ese máximo; no es una pérdida diaria. | Largest percentage fall from a running peak to the later trough before recovering that peak; not a daily loss. |  |  |
| PRC-16 | NOMINAL_REALIZED (Process_NOMINAL_REALIZED) | Nominal es la que declara la configuración; realizada es la que resulta tras el filtro de tendencia, el optimizador y GUARD. | Nominal is what the configuration declares; realized is what results after the trend filter, the optimizer and GUARD. |  |  |
| PRC-17 | NOT_IN_KNOWLEDGE_BASE (Process_NOT_IN_KNOWLEDGE_BASE) | El dato no está disponible en el grafo usado para la respuesta; no significa que no exista en el proyecto. | The data is not available in the graph used for the answer; it does not mean the data does not exist in the project. |  |  |
| PRC-18 | OPERATIONS_NOT_ORDERS (Process_OPERATIONS_NOT_ORDERS) | Los estados y alertas no son órdenes de compra o venta; un cambio de peso por sí solo no demuestra una operación. | States and alerts are not buy or sell orders; a weight change alone does not prove a trade. |  |  |
| PRC-19 | OUT_OF_SAMPLE (Process_OUT_OF_SAMPLE) | Resultado de datos no vistos antes de elegir la configuración; la configuración final no tiene ninguno. | A result from data not seen before the configuration was chosen; the final configuration has none. |  |  |
| PRC-20 | PIT_UNIVERSE (Process_PIT_UNIVERSE) | Los miembros del S&P 500 se reconstruyen según su pertenencia en cada fecha, no según los componentes actuales. | S&P 500 members reconstructed by their membership on each date, not the current constituents. |  |  |
| PRC-21 | SCHEDULED_REBALANCE (Process_SCHEDULED_REBALANCE) | Cada 21 sesiones los libros del motor recalculan la selección y los pesos y operan la diferencia; es distinto de los ajustes diarios de GUARD. | Every 21 sessions the engine books recompute selection and weights and trade the difference; this is distinct from GUARD daily adjustments. |  |  |
| PRC-22 | SCORE_NOT_WEIGHT (Process_SCORE_NOT_WEIGHT) | El puntaje determina el grupo de candidatas; los pesos vienen del optimizador y de satellite_weighting, no del puntaje ni de objective. | The score determines the candidate pool; the weights come from the optimizer and satellite_weighting, not from the score or objective. |  |  |
| PRC-23 | SELECTION (Process_SELECTION) | En las estrategias multifactoriales, los puntajes y los vetos determinan el grupo de candidatas; los Markowitz de comparación parten de los miembros elegibles sin esa selección. | In the multifactor strategies, scores and vetoes determine the candidate pool; the Markowitz comparison books start from eligible members without that selection. |  |  |
| PRC-24 | SHARPE (Process_SHARPE) | Media del retorno en exceso sobre su desviación estándar; indicar si está anualizado. | Mean excess return over its standard deviation; state whether it is annualized. |  |  |
| PRC-25 | TRADING_DAY (Process_TRADING_DAY) | Sesión con rotación mayor que cero. | A session with turnover greater than zero. |  |  |
| PRC-26 | TRANSACTION_COSTS (Process_TRANSACTION_COSTS) | Puntos básicos de la rotación (10 en las corridas principales). | Basis points of turnover (10 in the main runs). |  |  |
| PRC-27 | TURNOVER (Process_TURNOVER) | Suma completa de los cambios absolutos de peso en acciones, sin dividir entre dos; el efectivo no cuenta; es la base del costo. | Full sum of absolute equity-weight changes, not divided by two; cash does not count; it is the cost base. |  |  |
| PRC-28 | WARMUP_VETO (Process_WARMUP_VETO) | Veto fechado antes de la ventana porque el libro arranca sus ciclos 12 pasos antes; reportarlo aparte. | A veto dated before the window because the book starts its cycles 12 steps earlier; report it separately. |  |  |
| PRC-29 | WEIGHTING (Process_WEIGHTING) | En el Sistema el satélite se pondera por mínimo CVaR bajo sus topes; las demás estrategias usan el método de su configuración (p. ej. mínima varianza). | In the System the satellite is weighted by minimum CVaR under its caps; the other strategies use their configured method (e.g. minimum variance). |  |  |

### Rule individuals (`schema/rules.ttl`)

| id | code / IRI | ES comment | EN draft | Reviewer A decision | Notes |
|---|---|---|---|---|---|
| RUL-01 | BREAK_TREND_200 (VETO) | Solo indicador: cierre más de 5 % por debajo de su media simple de 200 sesiones. Marca la acción pero no la excluye ni resta puntos; nunca decir que fue vetada. | Flag only: close more than 5% below its 200-session simple moving average. It marks the name but neither excludes it nor subtracts points; never say it was vetoed. |  |  |
| RUL-02 | CRASH_Z_SCORE (VETO) | HARD temporal: z = (ret_5d - 5*mu_60d)/(sigma_60d*sqrt(5)) inferior a -2,5 y la misma prueba contra la mediana sectorial del retorno de 5 días inferior a -2,5, con la sigma de 60 sesiones de la propia acción. Misma persistencia de 10 sesiones que VOLATILITY_SHOCK; evaluada upstream. | Temporary HARD: z = (ret_5d - 5*mu_60d)/(sigma_60d*sqrt(5)) below -2.5 and the same test against the sector median 5-day return below -2.5, with the asset's own 60-session sigma. Same 10-session persistence as VOLATILITY_SHOCK; evaluated upstream. |  |  |
| RUL-03 | DATA_QUALITY (VETO) | Una verificación dura de calidad de datos de la Ronda 1 falló en el último informe del activo; la evidencia es la fila data_quality_issue. | A HARD Ring-1 data-quality gate fired on the asset's latest filing; the evidence is the data_quality_issue row. |  |  |
| RUL-04 | EARNINGS_MISSING (VETO) | Existe puntaje fundamental, pero el último informe tiene más de 400 días. Un activo que nunca tuvo puntaje fundamental es inelegible upstream, no vetado por esta regla. | A fundamental score exists but its latest filing is older than 400 days. An asset that never had a fundamental score is ineligible upstream, not vetoed by this rule. |  |  |
| RUL-05 | L1_BP_REENTRY (GUARD) | En una fecha de decisión, una acción detenida por L1_BP_STOP que sigue seleccionada reentra con una máquina Basing Points nueva. | At a decision date, a name stopped by L1_BP_STOP that is still selected re-enters with a fresh Basing Points machine. |  |  |
| RUL-06 | L1_BP_STOP (GUARD) | Capa 1 del Sistema: una acción del satélite pasa a efectivo cuando su cierre cae por debajo de su stop Basing Points creciente (último mínimo Basing Point por (1 - d), con d de la tabla de distancias de Edwards y la beta de 252 sesiones); la acción queda fuera hasta la siguiente fecha de decisión. | Layer 1 of the System: a satellite name goes to cash when its close falls below its rising Basing Points stop (latest Basing Point low times (1 - d), with d from Edwards' Table of Stop Distances and the 252-session beta); the name stays out until the next decision date. |  |  |
| RUL-07 | L1_REENTRY (GUARD) | Tras una salida por L1_STOP_LOSS, la acción reentra cuando su retorno de 1 sesión es al menos 0,0108. | After an L1_STOP_LOSS cut, the name re-enters when its 1-session return is at least 0.0108. |  |  |
| RUL-08 | L1_STOP_LOSS (GUARD) | Capa 1 del libro Markowitz de mínima varianza con GUARD, no una regla del Sistema: una acción mantenida pasa a efectivo cuando su retorno simple acumulado de 5 sesiones es inferior a -0,1229; reentra con la condición de recuperación. | Layer 1 of the Markowitz minimum-variance book with GUARD, not a System rule: a held name is cut to cash when its cumulative 5-session simple return is below -0.1229; the name re-enters on the recovery condition. |  |  |
| RUL-09 | L2_NEWS (GUARD) | Recortaría posiciones por noticias negativas; deshabilitada en el backtest final 2022-2025 porque el conjunto de entrenamiento de FinBERT abarca 2022-2026 (look-ahead). | Would trim positions on negative news; disabled in the final 2022-2025 backtest because the FinBERT training pool spans 2022-2026 (look-ahead). |  |  |
| RUL-10 | L3_VOL (GUARD) | La capa 3 escala la exposición total por s_sigma = min(1, 0,2455 / sigma_hat_21), donde sigma_hat_21 es la volatilidad anualizada ex-ante a 21 sesiones de los pesos de referencia; configurada, pero sin activaciones en las corridas evaluadas. | Layer 3 scales total exposure by s_sigma = min(1, 0.2455 / sigma_hat_21), where sigma_hat_21 is the ex-ante 21-session annualized volatility of the reference weights; configured, but no activations were observed in the evaluated runs. |  |  |
| RUL-11 | L4_DD (GUARD) | La capa 4 multiplica todos los pesos de referencia, incluido el núcleo SPY, por s_DD = clip(m*(W_t - alfa*M_t)/W_t, 0, 1), con m = 2,5467 y alfa = 0,6073; W_t es el valor del portafolio y M_t su máximo acumulado. Vale 1 en el máximo, baja cuando el valor cae por debajo y llega a 0 con una caída de ≈ 39,3 %. La referencia que recibe GUARD es el objetivo del brazo gemelo sin GUARD. | Layer 4 multiplies all the reference weights, including the SPY core, by s_DD = clip(m*(W_t - alpha*M_t)/W_t, 0, 1), with m = 2.5467 and alpha = 0.6073; W_t is portfolio NAV and M_t its running peak. It is 1 at the peak, falls as NAV drops below it, and reaches 0 at a drawdown of about 39.3%. The reference GUARD receives is the target of the twin arm without GUARD. |  |  |
| RUL-12 | LEVERAGE_EXTREME (VETO) | Deuda/patrimonio > 3 con patrimonio positivo; con patrimonio no positivo, EBITDA <= 0 con deuda neta, deuda neta/EBITDA > 5 o cobertura de intereses < 1,5. No aplica a empresas financieras. | Debt/equity above 3 with positive equity; with non-positive equity, EBITDA <= 0 with net debt, net debt/EBITDA > 5 or interest coverage < 1.5. Does not apply to financial firms. |  |  |
| RUL-13 | LIQUIDITY_DISTRESS (VETO) | Reemplazada el 2026-10-10: razón corriente inferior a 1,0 por sí sola. Se conserva cerrada con validTo para que un período abierto antes de esa fecha resuelva a la definición vigente. | Superseded on 2026-10-10: current ratio below 1.0 alone. Kept closed with validTo so a stint raised before that date resolves to the definition in force. |  |  |
| RUL-14 | LIQUIDITY_DISTRESS (VETO) | Razón corriente < 1,0 y (cobertura de intereses < 1,5 o margen de flujo operativo < 0). No aplica a financieras ni a utilities reguladas; "no se pudo determinar" es un estado de evaluación upstream y el período sigue abierto. | Current ratio below 1.0 and (interest coverage below 1.5 or operating cash-flow margin below 0). Does not apply to financial firms or regulated utilities; "could not tell" is an upstream evaluation state and the stint stays open. |  |  |
| RUL-15 | NEGATIVE_FCF (VETO) | Margen de flujo de caja libre de los últimos doce meses menor que cero. No aplica a utilities reguladas ni a REIT. | Trailing-twelve-month free-cash-flow margin below zero. Does not apply to regulated utilities or equity REITs. |  |  |
| RUL-16 | PRICE_CRASH (VETO) | Caída máxima de 90 días peor que -35 %. max_drawdown_90d es una métrica derivada de precios calculada upstream. | 90-day maximum drawdown worse than -35%. max_drawdown_90d is a price-derived metric computed upstream. |  |  |
| RUL-17 | UTILITY_CASH_COVERAGE (VETO) | Aplica solo a utilities reguladas: flujo operativo medio de tres años antes de capital de trabajo dividido por la deuda total inferior al 5 %. HARD. | Applies only to regulated utilities: 3-year average operating cash flow before working capital divided by total debt below 5%. HARD. |  |  |
| RUL-25 | VOLATILITY_SHOCK (VETO) | HARD temporal: la volatilidad de retornos logarítmicos de 5 sesiones dividida por una base de 60 sesiones que termina 5 sesiones antes es mayor que 2,5 y mayor que 2,5 veces la mediana sectorial de ese día (menos de 5 nombres: mediana de la sección transversal). Se abre por 10 sesiones y se renueva si la condición persiste; evaluada upstream. | Temporary HARD: 5-session log-return volatility divided by a 60-session baseline ending 5 sessions earlier is above 2.5 and above 2.5 times the sector median that day (fewer than 5 names: the cross-section median). Opens for 10 sessions and renews if the condition persists; evaluated upstream. |  |  |

### Schema classes and properties (`schema/tbox.ttl`, T-754 set)

| id | code / IRI | ES comment | EN draft | Reviewer A decision | Notes |
|---|---|---|---|---|---|
| TRM-01 | GuardAction | Efecto de una alerta de GUARD sobre un libro para la sesión siguiente. | The effect of one GUARD alert on one book for the next session. |  |  |
| TRM-02 | GuardAlert | Alerta diaria de una capa de GUARD para un activo, con su regla, valor, umbral y estado. | One GUARD layer daily alert for one asset, with its rule, value, threshold and state. |  |  |
| TRM-03 | StrategyBook | Brazo experimental de una corrida de backtest en una ventana; un conjunto nombrado de tenencias. | One experimental arm of one backtest run in one window; a named pool of holdings. |  |  |
| TRM-04 | Veto | Período de veto de un activo: las reglas activadas y el intervalo raisedOn..clearedOn. | A veto stint for one asset: the rules that fired and the interval raisedOn..clearedOn. |  |  |
| TRM-05 | attractivenessScore | blended_score de upstream / 100; mayor es más atractivo; puede ser negativo tras penalizaciones suaves. El puntaje no es el peso. | Upstream blended_score / 100; higher is more attractive; it can be negative after soft penalties. The score is not the weight. |  |  |
| TRM-06 | bookWeightingRule | scheme_id de upstream: la regla que convierte el ranking en pesos del libro (por ejemplo score_proportional o score_tilt). Pertenece al esquema de atractivo, no a la cartera, y no es satellite_weighting. | Upstream scheme_id: the rule that turns the ranking into book weights (for example score_proportional or score_tilt). It belongs to the attractiveness score scheme, not to the portfolio, and is not satellite_weighting. |  |  |
| TRM-07 | cashFraction | Fracción del objetivo Top-N movida a efectivo por el filtro de tendencia en esta decisión, mantenida hasta la siguiente fecha de decisión. | Fraction of the Top-N target moved to cash by the trend filter at this decision, held until the next decision date. |  |  |
| TRM-08 | componentValue | Valor que un componente de peso efectivo tuvo para este activo en esta corrida del ciclo, 0-100. | The value one effective-weight component had for this asset in this cycle run, 0-100. |  |  |
| TRM-09 | costReturn | Costo por sesión como fracción de retorno. | Per-session cost as a return fraction. |  |  |
| TRM-10 | dateFrom | Primera fecha de sesión del segmento. | First session date of the segment. |  |  |
| TRM-11 | dateTo | Última fecha de sesión del segmento. | Last session date of the segment. |  |  |
| TRM-12 | exPostSharpe | Media del retorno en exceso sobre su desviación estándar, anualizada; indicar la convención al informarlo. | Mean excess return over its standard deviation, annualized; state the convention when reporting it. |  |  |
| TRM-13 | excludeHardVetoed | Vale 0 también en el Sistema porque el modelo compartido incluye los vetados; el Sistema excluye los vetos duros antes, en la preselección. Nunca decir que el Sistema no excluye empresas con veto duro. | It is 0 also in the System because the shared model includes vetoed names; the System excludes hard vetoes earlier, in the preselection. Never say the System does not exclude hard-vetoed companies. |  |  |
| TRM-14 | grossReturn | Retorno diario del libro antes de costos de transacción. | Daily book return before transaction costs. |  |  |
| TRM-15 | maxDrawdown | Mayor caída desde un máximo acumulado hasta el mínimo posterior antes de recuperar el máximo; no es una pérdida diaria. | Largest fall from a running peak to the later trough before recovering the peak; not a daily loss. |  |  |
| TRM-16 | maxNameWeight | Fracción del libro; por ejemplo 0,05 = 5 %. | Fraction of the book; for example 0.05 = 5%. |  |  |
| TRM-17 | maxSectorWeight | Fracción del libro; por ejemplo 0,30 = 30 %. | Fraction of the book; for example 0.30 = 30%. |  |  |
| TRM-18 | nGuardActions | Cuenta las acciones que GUARD ejecuta sobre el libro. En un libro sin GUARD, 0 significa no aplicable, no que GUARD no actuó (MARKOWITZ_BASE, TOPN_MV_NOGUARD y MARKOWITZ_MV). | Counts the actions GUARD executes on the book. In a book without GUARD, 0 means not applicable, not that GUARD did not act (MARKOWITZ_BASE, TOPN_MV_NOGUARD and MARKOWITZ_MV). |  |  |
| TRM-19 | nRebalances | Número de decisiones de la ventana cuya fecha de ejecución cae dentro del segmento. | Number of the window decisions whose execution date falls inside the segment. |  |  |
| TRM-20 | nSessions | Número de sesiones del segmento. | Number of sessions in the segment. |  |  |
| TRM-21 | netReturn | Retorno diario del libro después de costos de transacción. | Daily book return after transaction costs. |  |  |
| TRM-22 | objective | v_book.objective, la etiqueta strategy_book.objective de upstream, abierta y leída verbatim. La función _insert_books de upstream la escribe como literal fijo por brazo: 'min_var' para todo brazo optimizado y 'equal_weight' para el benchmark SP500_EW_INTERNAL, independientemente de satellite_weighting de la corrida. El config_final.md de la entrega describe un paso de optimización de mínima varianza que mantiene como máximo 30 nombres, seguido de una ponderación por mínimo CVaR de esos nombres, así que el literal 'min_var' NO es la función objetivo de ponderación de los libros TOPN_MV_* y no debe presentarse como tal. La confirmación del significado completo por el mantenedor de upstream está pendiente. En el libro externo MARKOWITZ_MV el loader escribe 'max_sharpe' como clase registrada (pendiente de Reviewer A); no es un brazo del motor. | v_book.objective, upstream's strategy_book.objective, open and read verbatim. Upstream's _insert_books function writes it as a fixed literal per arm: 'min_var' for every optimized arm and 'equal_weight' for the benchmark SP500_EW_INTERNAL, independent of the run's satellite_weighting. The delivery's config_final.md describes a minimum-variance optimisation step that keeps at most 30 names, followed by minimum-CVaR weighting of those names, so the literal 'min_var' is NOT the weighting objective of the TOPN_MV_* books and must not be presented as such. Confirmation of the full meaning by upstream's maintainer is pending. On the external MARKOWITZ_MV book the loader writes 'max_sharpe' as the registered class (pending Reviewer A); it is not an engine arm. |  |  |
| TRM-23 | rankPosition | Orden por puntaje combinado sobre todos los miembros clasificados de la fecha, incluidas las vetadas. | Order by combined score over all classified members of the date, including vetoed names. |  |  |
| TRM-24 | referenceMaxDrawdown | max_t(1 - NAV_t / max(1, NAV_1..NAV_t)), fracción positiva. | max_t(1 - NAV_t / max(1, NAV_1..NAV_t)), positive fraction. |  |  |
| TRM-25 | referenceName | SPY (retorno total, dividendos reinvertidos) o SP500_EW_INTERNAL. | SPY (total return, dividends reinvested) or SP500_EW_INTERNAL. |  |  |
| TRM-26 | referenceTotalReturn | prod(1 + r_t) - 1 sobre las sesiones del segmento, como fracción. | prod(1 + r_t) - 1 over the segment sessions, as a fraction. |  |  |
| TRM-27 | selectedForBook | Pertenencia al grupo de 60 candidatas, no a los como máximo 30 nombres mantenidos. | Membership of the 60-name candidate pool, not the at most 30 names held. |  |  |
| TRM-28 | softVetoPenalty | Puntos de la mezcla 0-100 de upstream que se cargan una vez por período SOFT activo cuya regla no declara penaltyPoints (15 por defecto); no es una fracción. | Points of the upstream 0-100 blend charged once per active SOFT stint whose rule declares no penaltyPoints (15 by default); not a fraction. |  |  |
| TRM-29 | targetWeight | Peso del ciclo sobre el grupo de 60 candidatas; no es un peso de cartera. | The cycle own weight over the 60-name candidate pool; not a portfolio weight. |  |  |
| TRM-30 | topN | Tamaño del grupo de candidatas (60 en el backtest final), no el máximo de nombres mantenidos. | The size of the candidate pool (60 in the final backtest), not the cap of names actually held. |  |  |
| TRM-31 | totalCostBps | Suma del costo de las sesiones del segmento, en puntos básicos. | Sum of the session cost over the segment, in basis points. |  |  |
| TRM-32 | totalTurnover | Suma de la rotación de las sesiones del segmento. | Sum of the session turnover over the segment. |  |  |
| TRM-33 | trendState | below, at_or_above o not_evaluable; no se publica nivel de precio ni media. | below, at_or_above or not_evaluable; no price level or mean is published. |  |  |
| TRM-34 | turnover | Suma completa de los cambios absolutos de peso en acciones, sin dividir entre dos; el efectivo no cuenta. | Full sum of absolute equity-weight changes, not divided by two; cash does not count. |  |  |

### MetricType concepts (`schema/reference.ttl`)

| id | code / IRI | ES comment | EN draft | Reviewer A decision | Notes |
|---|---|---|---|---|---|
| MT-01 | ScoreCuantitativo | Puntaje de múltiplos de valoración leído del carril VALORIZATION. | Valuation-multiple score read from the VALORIZATION lane. |  |  |
| MT-02 | ScoreFinanciero | Puntaje fundamental del informe trimestral; en este grafo compara por rawValue (0-100). | Fundamental score from the quarterly filing; in this graph it compares on rawValue (0-100). |  |  |
| MT-03 | ScoreTecnico | Puntaje de tendencia y momentum de precios leído del carril TECHNICAL. | Price trend and momentum score read from the TECHNICAL lane. |  |  |
| MT-04 | SectorRelativeMomentum | Puntaje técnico bruto de la acción menos la media de su sector GICS; rawValue en [-100, 100], diagnóstico y no parte del puntaje combinado. | The asset technical raw score minus its GICS sector mean; rawValue in [-100, 100], a diagnostic and not part of the combined score. |  |  |
| MT-05 | Sentiment | Puntaje de sentimiento semántico; compara por rawValue en [-1, 1], no por normalizedScore. | Semantic sentiment score; it compares on rawValue in [-1, 1], not on normalizedScore. |  |  |
