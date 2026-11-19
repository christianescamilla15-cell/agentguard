# Arquitectura · agentguard

Modelo C4: contexto → contenedores → componentes. Los diagramas son texto (Mermaid), se versionan con el código
y nombran módulos que existen. Decisiones en [`docs/adr/`](../adr/); reglas con sus pruebas en
[`docs/reglas.md`](../reglas.md).

## 1. Contexto

agentguard no es un servicio: es una biblioteca que vive **dentro** del proceso de quien la integra, entre el
agente que propone acciones y el ejecutor que las corre.

```mermaid
C4Context
  title Contexto · agentguard
  Person(dev, "Integrador", "Configura los límites y conecta agente, política y ejecutor")
  Person(visitante, "Visitante", "Prueba las 8 reglas en el playground")
  System_Ext(agente, "Agente (LLM, planificador)", "Propone acciones; puede alucinar o ser manipulado")
  System(ag, "agentguard", "8 reglas duras + estado con cierre; responde ALLOW o DENY:<regla>")
  System_Ext(ejecutor, "Ejecutor de herramientas", "Corre sólo lo aprobado (APIs, archivos, pagos)")
  System_Ext(almacen, "Almacén del integrador", "Donde se persiste snapshot() para sobrevivir a una caída")
  Rel(agente, ag, "ProposedAction")
  Rel(ag, ejecutor, "Sólo si ALLOW")
  Rel(dev, ag, "PolicyConfig")
  Rel(ag, almacen, "snapshot() / restore()")
  Rel(visitante, ag, "Usa el playground", "HTTPS")
```

## 2. Contenedores

```mermaid
C4Container
  title Contenedores · agentguard
  Person(dev, "Integrador")
  Person(visitante, "Visitante")
  System_Boundary(b, "agentguard") {
    Container(lib, "Biblioteca agentguard", "Python 3.10+ · sin dependencias", "src/agentguard: PolicyConfig, PolicyEngine, ProposedAction, Verdict")
    Container(ejemplo, "Ejemplo", "Python", "examples/llm_tool_call_guard.py: envuelve las llamadas de un agente ficticio; su salida es archivo dorado")
    Container(playground, "Playground", "HTML + CSS + JS · Vercel", "demo/: puerto a JS de policy.py que corre en el navegador, sin backend")
  }
  Rel(dev, lib, "pip install (desde GitHub)")
  Rel(ejemplo, lib, "Importa")
  Rel(visitante, playground, "Usa", "HTTPS")
  Rel(playground, lib, "Replica las mismas 8 reglas y prefijos (puerto manual)")
```

## 3. Componentes de la biblioteca

```mermaid
C4Component
  title Componentes · biblioteca agentguard
  Container_Boundary(l, "src/agentguard") {
    Component(tipos, "ProposedAction · Verdict", "types.py · dataclasses congeladas", "Lo que el agente propone (no confiable) y la decisión")
    Component(config, "PolicyConfig", "policy.py · dataclass congelada", "Límites inmutables: herramientas, topes, ventanas, freno, datos frescos")
    Component(motor, "PolicyEngine.evaluate", "policy.py", "Las 8 reglas en orden; la primera violada nombra la negación")
    Component(registro, "PolicyEngine.register_action", "policy.py", "Debita SÓLO lo ejecutado: tasa, gasto por ventana, gasto total, presupuesto")
    Component(estado, "snapshot / restore", "policy.py", "Estado con cierre serializable: freno, ventanas, gasto, presupuesto")
  }
  Rel(motor, tipos, "lee ProposedAction, devuelve Verdict")
  Rel(motor, config, "aplica")
  Rel(registro, estado, "actualiza")
  Rel(motor, estado, "lee")
```
