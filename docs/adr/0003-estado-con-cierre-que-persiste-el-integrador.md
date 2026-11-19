# ADR 0003 · Estado con cierre serializable; la persistencia la hace el integrador

- Estado: aceptada (se registra el 2026-11-19) · Código: `PolicyEngine.snapshot/restore/register_action`

## Contexto
Si el freno y las ventanas viven sólo en memoria, una caída y un reinicio **des-disparan** el freno y ponen los
contadores en cero: el agente vuelve a gastar justo cuando no debía (el bug real que encontró treasuryforge).

## Decisión
- El freno es un cierre: armado → disparado es la única transición; no hay API para rearmarlo.
- `snapshot()` devuelve un `dict` serializable a JSON con todo lo que una caída podría borrar (gasto total,
  bandera del freno, ventanas de tasa y de gasto, presupuesto restante); `restore()` lo reconstruye y tolera un
  estado vacío.
- El freno se **re-deriva** del gasto (`spent_total >= max_cost_burn`) en cada evaluación, así que se dispara aunque
  la bandera se haya perdido entre `register_action()` y la escritura del estado.
- Sólo lo ejecutado se debita (`register_action`), nunca lo evaluado.
- La biblioteca no escribe a disco: el integrador decide dónde y cómo persistir (el README muestra la escritura
  atómica).

## Alternativas
- Persistir dentro de la biblioteca: obliga a un formato y a un medio (archivo, base de datos) que no son suyos.

## Consecuencias
- La garantía ante caídas depende de que el integrador persista tras cada `register_action()`; está documentado
  en el README y en `SECURITY.md`.
- Pruebas: `tests/test_reglas.py::test_tripped_to_armed_is_an_invalid_transition`,
  `::test_breaker_rederives_from_spend_even_if_the_flag_was_lost`,
  `::test_snapshot_survives_json_and_restores_every_counter`.
