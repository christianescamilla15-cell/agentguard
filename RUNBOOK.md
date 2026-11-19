# Runbook · agentguard

agentguard es una **biblioteca**: no hay un servicio que operar. Lo único desplegado es el *playground* del
navegador (`demo/`, un puerto a JavaScript de `policy.py`). Estado verificado el 2026-11-19.

| Qué | Dónde | Cómo se despliega hoy | Humo |
|---|---|---|---|
| Playground (`demo/`) | Vercel, proyecto `agentguard` → https://agentguard-amber.vercel.app | `vercel deploy demo --prod`: la **carpeta `demo/`** es la raíz del despliegue (origen «cli»; el proyecto **no** está conectado a Git). Último despliegue a producción: 21-jun-2026; sus 3 archivos de la página coinciden byte a byte con `demo/` de `main` | `herramientas/humo.sh https://agentguard-amber.vercel.app` → OK el 2026-11-19 |
| Paquete de Python | **no publicado** en PyPI (el nombre `agentguard` no existe allí) | se instala desde GitHub: `pip install git+https://github.com/christianescamilla15-cell/agentguard` | el job `paquete` del CI construye la rueda, la instala en un entorno limpio y corre el ejemplo |

Notas verificadas:

- `agentguard.vercel.app` **no** es de este proyecto (responde 402 `DEPLOYMENT_DISABLED`); el dominio propio es
  `agentguard-amber.vercel.app`.
- El despliegue de producción llevaba una `vercel.json` (cabeceras `nosniff` y `Referrer-Policy`) que no estaba en
  el repo; ahora está versionada en `demo/vercel.json`. La `vercel.json` de la raíz no es la que se usa: con ella,
  `/` reescribiría a `/demo/index.html` pero los recursos relativos (`./demo.js`) darían 404.

## Desplegar

1. Todo cambio entra por PR a `main` con los checks requeridos en verde (`ci`, `seguridad`). Un check «skipped»
   cuenta como rojo: ningún job se salta en un PR.
2. Playground:

   ```bash
   vercel deploy demo                         # preview: imprime la URL de la vista previa
   herramientas/humo.sh <url-de-la-preview>   # debe salir con 0
   vercel promote <url-de-la-preview>         # pasa la preview a producción
   herramientas/humo.sh https://agentguard-amber.vercel.app
   ```

3. Si cambia `src/agentguard/policy.py`, el puerto `demo/demo.js` debe cambiar en el mismo PR (mismas 8 reglas, mismo
   orden, mismos prefijos `DENY:`); el humo verifica que el script servido conserve los prefijos.

## Revertir

> **No ensayado todavía.** Esta revisión no despliega nada (regla del programa); el primer ensayo se anotará aquí
> con su fecha.

1. `vercel rollback` (vuelve al despliegue de producción anterior) o `vercel promote <url-anterior>`.
2. `herramientas/humo.sh https://agentguard-amber.vercel.app` sobre la versión restaurada.

## Diagnóstico

| Síntoma | Causa probable | Qué hacer |
|---|---|---|
| El playground carga sin estilos o sin botones | se desplegó la raíz del repo en vez de `demo/` | volver a desplegar con `vercel deploy demo` |
| El playground permite algo que la biblioteca niega | el puerto JS se desvió de `policy.py` | comparar `evaluate()` de `demo/demo.js` con `PolicyEngine.evaluate()` y corregir en el mismo PR |
| CI `pruebas`: falla `test_readme_output_block_matches_the_golden_file` | el README dejó de reflejar lo que imprime el ejemplo | regenerar `tests/golden/llm_tool_call_guard.txt` sólo si el cambio de comportamiento es intencional, y actualizar el bloque «Output» |
| Después de reiniciar, el freno vuelve a permitir | el integrador no persistió `snapshot()` o lo escribió sin atomicidad | persistir tras cada `register_action()` con escritura atómica (`os.replace`) y `restore()` al arrancar |
