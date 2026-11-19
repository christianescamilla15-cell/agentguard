# ADR 0002 · Una biblioteca sin dependencias, extraída del motor de treasuryforge

- Estado: aceptada (versión 0.1.0; se registra el 2026-11-19) · Código: `src/agentguard/policy.py`, `pyproject.toml`

## Contexto
El patrón «el agente propone, la política dispone» se validó en treasuryforge con intents de trading. Cualquier
agente con herramientas (LLM que llama APIs, gasta dinero o toca archivos) necesita lo mismo, sin el dominio de
mercados.

## Decisión
- Generalizar las 8 reglas a acciones de herramientas: lista de herramientas en vez de símbolos, costo por llamada
  en las unidades del integrador (USD, tokens, llamadas) en vez de nocional, freno por gasto acumulado en vez de
  drawdown, presupuesto restante en vez de saldo de la billetera.
- **Cero dependencias de ejecución** (`dependencies = []`): se audita leyendo dos archivos y no arrastra cadena de
  suministro al proceso del integrador.
- Las negaciones son estructuradas: `DENY:<prefijo> <detalle>` para filtrar bitácoras.
- La API es síncrona y determinista: el tiempo (`now_s`) y la edad del contexto se pueden inyectar.

## Alternativas
- Depender de treasuryforge: arrastra el dominio de trading.
- Un servicio de políticas por HTTP: otro punto de falla y latencia en cada llamada del agente.

## Consecuencias
- El orden de las reglas es contrato y está probado (`tests/test_reglas.py`).
- Los prefijos no son el nombre de la regla en todos los casos (`DENY:tool` = lista de herramientas,
  `DENY:cost` = tope por llamada, `DENY:stale_context` = datos frescos, `DENY:insufficient_budget` = solvencia):
  cambiarlos rompe a quien filtra por ellos, así que están fijados por pruebas.
- El paquete no está publicado en PyPI; se instala desde GitHub.
