# ADR 0004 · El playground es un puerto a JavaScript, sin backend

- Estado: aceptada (se registra el 2026-11-19) · Código: `demo/demo.js`

## Contexto
El playground debe dejar probar las 8 reglas sin instalar nada. treasuryforge resolvió lo mismo con una API en
Render que corre el motor real; aquí se eligió otra cosa.

## Decisión
`demo/` es una página estática (HTML + CSS + JS sin dependencias) con un puerto manual de
`PolicyEngine.evaluate`: mismas reglas, mismo orden y mismos prefijos `DENY:`. Se despliega en Vercel desde la
carpeta `demo/`.

## Alternativas
- Llamar a una API con la biblioteca real (como treasuryforge): cero desviación, pero un servicio que mantener y
  que se duerme en el plan gratuito.
- Pyodide (Python en el navegador): sin desviación, pero varios MB de descarga para una página de demostración.

## Consecuencias
- El puerto puede desviarse del original. Hoy coincide en lógica; difiere sólo en formato (el límite de tasa
  imprime `60s` donde Python imprime `60.0s`). Mitigación: el humo post-despliegue verifica que el script
  servido conserve los prefijos, y el runbook exige cambiar ambos en el mismo PR.
- Pendiente (N08b): una prueba de paridad que corra los mismos escenarios en Python y en JS.
