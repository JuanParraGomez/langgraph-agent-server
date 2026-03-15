# Agent observability guardrails

Estas reglas son obligatorias para cualquier agente/IA que modifique este repositorio.

1. Toda ejecución de grafo o workflow debe pasar por `app/observability/langsmith_setup.py`, usando `invoke_graph_traced(...)`.
2. Toda llamada directa al proveedor OpenAI SDK debe usar `get_wrapped_openai_client(...)` para que la traza quede en LangSmith.
3. No desactivar `LANGSMITH_TRACING` ni `LANGSMITH_ENFORCE` en despliegues reales.
4. No guardar `LANGSMITH_API_KEY` en archivos versionados.
5. Si agregas nuevos entrypoints (API, worker, CLI), instrumenta esos entrypoints antes de mergear.
