# Seguridad

## Reportar una vulnerabilidad

Escribe a **christianescamilla15@gmail.com** con el asunto «Seguridad: agentguard». Respondo en 72 horas
hábiles y publico el arreglo con su aviso. Por favor no abras un issue público para vulnerabilidades.

Un hallazgo de seguridad aquí es, sobre todo, **una forma de que una acción pase cuando una regla debía negarla**
(o de que el estado con cierre se pierda): eso tiene prioridad sobre cualquier otra cosa.

## Qué revisa cada cambio

| Revisión | Herramienta | Bloquea |
|---|---|---|
| Análisis estático | CodeQL (Python + JS del playground) + Semgrep `p/default` (imagen 1.186.0 fijada por digest) | sí (Semgrep) |
| Tipos | mypy `--strict` | sí |
| Dependencias | Trivy fs sobre `ci/requirements.txt` | sí, en CRITICAL/HIGH con arreglo publicado |
| Configuración e IaC | Trivy config (hoy no hay Dockerfile ni IaC) | sí, en CRITICAL/HIGH |
| Secretos en toda la historia | gitleaks v8.21.2 (imagen fija; el job exige ver «N commits scanned» en la bitácora), CI y pre-commit | sí |
| Datos de terceros | `herramientas/confidencialidad.py` (CI y pre-commit) | sí |
| Inventario de componentes | SBOM (syft, SPDX) | no: se publica con cada versión |

La biblioteca **no tiene dependencias de ejecución**; lo único de terceros que corre es la cadena de
herramientas del CI, fijada con versión exacta en `ci/requirements.txt` (Dependabot propone las subidas con 7 días
de espera). Las acciones de GitHub van fijadas por SHA.

Cada revisión debe probar que analizó algo (archivos o paquetes > 0, `herramientas/verificar_reportes.py`); un
reporte vacío cuenta como fallo.

## Excepciones vigentes

| Excepción | Motivo | Revisar |
|---|---|---|
| `herramientas/verificar_reportes.py` excluido de Semgrep (sólo ese archivo, no la regla) | copia literal de la plantilla; lee con `xml.etree` el JUnit que genera el propio job: entrada propia, no de terceros | si el archivo empieza a leer XML externo |

Las excepciones de Trivy viven en `.trivyignore`, cada una con fecha de vencimiento y motivo (hoy: ninguna).

## Límites conocidos (por diseño)

- La política trata `ProposedAction.args` como opaco: validar los argumentos es responsabilidad de cada herramienta.
- `actor` se registra pero todavía no se usa para separar límites por actor.
- `snapshot()`/`restore()` sólo dan seguridad ante caídas si quien integra persiste el estado de forma atómica
  después de cada `register_action()`.
