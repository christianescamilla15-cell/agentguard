# Reglas de negocio → pruebas · agentguard

Ésta es la compuerta real del proyecto (más que el % de cobertura, que está en 100 % de líneas y ramas): cada
regla tiene al menos una prueba que falla si la regla se rompe. Formato `archivo::prueba`. Las marcadas
**(nueva)** se agregaron en la revisión del 2026-11-19 (antes había 11 pruebas).

## Las 8 reglas duras (`src/agentguard/policy.py::PolicyEngine.evaluate`)

| # | Regla | Prefijo exacto | Pruebas |
|---|---|---|---|
| — | Se evalúan **en este orden** y la primera violada nombra la negación | — | `tests/test_reglas.py::test_the_8_rules_fire_in_their_documented_order` **(nueva)** · `tests/test_reglas.py::test_each_rule_alone_denies_with_its_exact_prefix` (8 casos) **(nueva)** |
| 1 | Interruptor de paro: niega todo | `DENY:kill_switch` | `tests/test_policy.py::test_kill_switch_denies_everything` |
| 2 | Freno por gasto acumulado: se dispara en `gasto >= max_cost_burn` y se queda disparado | `DENY:circuit_breaker` | `tests/test_policy.py::test_circuit_breaker_trips_and_stays_tripped` · `tests/test_reglas.py::test_breaker_trips_exactly_at_the_burn_limit` **(nueva)** |
| 3 | Contexto viejo: niega si la edad supera `max_staleness_s`; inerte sin presupuesto o sin edad; en el límite se permite | `DENY:stale_context` | `tests/test_policy.py::test_staleness_gate` · `tests/test_reglas.py::test_staleness_gate_is_inert_without_budget_or_age_and_allows_at_the_budget` **(nueva)** |
| 4 | Sólo herramientas de la lista | `DENY:tool` | `tests/test_policy.py::test_allowlist_denies_unknown_tool` |
| 5 | Tope por llamada (en el tope se permite) y piso mínimo opcional | `DENY:cost` · `DENY:min_cost` | `tests/test_policy.py::test_per_call_cap` · `tests/test_reglas.py::test_cost_exactly_at_the_cap_is_allowed` **(nueva)** · `tests/test_reglas.py::test_min_cost_floor_rejects_dust_and_allows_at_the_floor` **(nueva)** |
| 6 | Límite de llamadas por ventana móvil; una llamada exactamente en el corte sale de la ventana | `DENY:rate_limit` | `tests/test_policy.py::test_rate_limit` · `tests/test_reglas.py::test_rate_window_evicts_a_call_exactly_at_the_cutoff` **(nueva)** |
| 7 | Presupuesto de gasto por ventana (en el límite se permite; se recupera; su ventana puede ser distinta) | `DENY:spend_budget` | `tests/test_policy.py::test_spend_budget` · `tests/test_reglas.py::test_spend_budget_allows_exactly_the_budget_and_recovers_after_its_window` **(nueva)** · `tests/test_reglas.py::test_spend_window_can_differ_from_the_rate_window` **(nueva)** |
| 8 | Solvencia contra el presupuesto restante (el de la llamada tiene prioridad; lo ejecutado lo descuenta) | `DENY:insufficient_budget` | `tests/test_policy.py::test_budget_solvency` · `tests/test_reglas.py::test_solvency_uses_the_per_call_budget_and_allows_exactly_the_budget` **(nueva)** · `tests/test_reglas.py::test_executed_actions_debit_the_remaining_budget` **(nueva)** |
| — | Dentro de los límites se permite con razón exacta `ALLOW` | `ALLOW` | `tests/test_policy.py::test_allow_within_limits` |

## Reglas transversales

| Regla | Pruebas |
|---|---|
| La configuración es inmutable: el agente no puede subir sus límites | `tests/test_reglas.py::test_config_is_immutable` **(nueva)** |
| Lo negado no consume nada (tasa, gasto por ventana, freno, presupuesto) | `tests/test_policy.py::test_denied_action_does_not_consume_budget` · `tests/test_reglas.py::test_denied_actions_never_consume_anything` **(nueva)** |
| Un ALLOW nunca rompe un límite prometido, sobre historias arbitrarias | `tests/test_reglas.py::test_an_allow_never_breaks_a_promised_limit` (200 historias con semilla) **(nueva)** |

## Máquina de estados del freno: armado → disparado

| Transición | Pruebas |
|---|---|
| armado → disparado al alcanzar el gasto límite | `tests/test_reglas.py::test_breaker_trips_exactly_at_the_burn_limit` **(nueva)** |
| **Inválida** disparado → armado: ninguna acción, costo cero, otra herramienta, hora lejana, contexto fresco ni presupuesto lo rearma | `tests/test_reglas.py::test_tripped_to_armed_is_an_invalid_transition` **(nueva)** · `tests/test_policy.py::test_circuit_breaker_trips_and_stays_tripped` |
| **Inválida** disparado → armado por reinicio: el estado restaurado mantiene el freno | `tests/test_policy.py::test_snapshot_restore_preserves_tripped_breaker` |
| El freno se re-deriva del gasto aunque la bandera se haya perdido | `tests/test_reglas.py::test_breaker_rederives_from_spend_even_if_the_flag_was_lost` **(nueva)** |

## Estado a prueba de caídas (`snapshot` / `restore`)

| Regla | Pruebas |
|---|---|
| El estado sobrevive a JSON y conserva cada contador (no se ponen en cero las ventanas) | `tests/test_reglas.py::test_snapshot_survives_json_and_restores_every_counter` **(nueva)** |
| Restaurar un estado vacío equivale a un motor nuevo | `tests/test_reglas.py::test_restore_of_an_empty_state_is_a_fresh_engine` **(nueva)** |

## Documentación que no miente (archivo dorado)

| Regla | Pruebas |
|---|---|
| Las decisiones del ejemplo incluido son las del archivo dorado | `tests/test_ejemplo.py::test_example_decisions_match_the_golden_file` **(nueva)** |
| El bloque «Output» del README es exactamente lo que imprime el ejemplo | `tests/test_ejemplo.py::test_readme_output_block_matches_the_golden_file` **(nueva)** — encontró que el README prometía un 4.º ALLOW que el límite de 3 por ventana niega |
