#!/usr/bin/env bash
# Prueba de humo post-despliegue del playground. Sale con 0 sólo si la página carga lo que necesita.
#
#   herramientas/humo.sh https://agentguard-amber.vercel.app
#   herramientas/humo.sh <url-de-una-preview>
set -euo pipefail
url=${1:?uso: humo.sh <url>}
url=${url%/}

obtener() { curl -fsS -m 20 --retry 3 --retry-delay 2 "$url$1"; }

exige() {  # exige <texto> <cuerpo> <qué>
  if ! grep -q -- "$1" <<< "$2"; then
    echo "humo: FALLA · $3 (no aparece «$1»)" >&2
    exit 1
  fi
  echo "humo: ok · $3"
}

html=$(obtener /)
exige "<title>agentguard" "$html" "la página del playground carga"
exige "demo.js" "$html" "la página referencia su script"
js=$(obtener /demo.js)            # se despliega la carpeta demo/: sus archivos quedan en la raíz
exige "function evaluate" "$js" "el script con el motor de reglas se sirve"
exige "DENY:kill_switch active" "$js" "el script conserva los prefijos DENY de la biblioteca"
echo "humo: $url · TODO OK"
