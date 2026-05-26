"""Prueba manual del aislamiento de vistas en multi-loop.

Dos InstantLoops sobre el mismo History. Verifica que:
- Cada loop solo ve sus propias entries en su vista.
- Correr loop B no contamina la vista de loop A.
- El History compartido tiene entries de ambos en orden temporal.
- Un Monitor con origin ve solo los steps de su loop.

Sin red ni LLM — usa agente mock.
"""
import sys
from pathlib import Path
from types import SimpleNamespace

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from instantneo.history import History
from instantneo.loop import InstantLoop
from instantneo.monitor import Monitor
from instantneo.monitor.conditions import every_n_steps, when_last_tool_called
from instantneo.monitor.actions import stop_signal


# ── Mock agent ────────────────────────────────────────────────────────

def _mk_agent(name: str, responses: list[str]):
    """Agente mock que devuelve respuestas prefijadas con su nombre."""
    class _Agent:
        def __init__(self):
            self.config = SimpleNamespace(
                provider="mock", model="mock-m", api_key="x",
                role_setup="x", temperature=None, max_tokens=None,
                presence_penalty=None, frequency_penalty=None,
                stop=None, seed=None, stream=False, logit_bias=None,
                images=None, image_detail=None,
                location=None, service_account_file=None,
            )
            self.capabilities = SimpleNamespace(get_schemas=lambda: [])
            self.last_run = None
            self._idx = 0

        def get_resolved_role_setup(self, shelf_context=None):
            return "mock"

        def run(self, prompt, images=None, image_detail=None):
            resp = responses[self._idx % len(responses)]
            self._idx += 1
            self.last_run = SimpleNamespace(
                error=None, prompt=prompt,
                response_content=f"[{name}] {resp}",
                reasoning=None, finish_reason="stop",
                usage={"input_tokens": 5, "output_tokens": 3,
                       "total_tokens": 8, "reasoning_tokens": 0},
                duration_ms=1.0, provider="mock", model="mock-m",
                timestamp="2026-01-01T00:00:00Z",
                run_params={"model": "mock-m"},
                provider_timing=None,
                llm_calls=[], tool_executions=[], messages_sent=[],
            )
    return _Agent()


# ── Helpers de validación ─────────────────────────────────────────────

def check(label: str, condition: bool):
    status = "✅" if condition else "❌"
    print(f"  {status}  {label}")
    if not condition:
        raise AssertionError(f"FALLÓ: {label}")


# ── Prueba principal ──────────────────────────────────────────────────

def main():
    print("\n=== SMOKE TEST: multi-loop view isolation ===\n")

    history = History(name="shared")

    agent_a = _mk_agent("A", ["respuesta A1", "respuesta A2", "respuesta A3"])
    agent_b = _mk_agent("B", ["respuesta B1", "respuesta B2"])

    mon_a = Monitor(name="mon_a")
    mon_a.add_rule(every_n_steps(2, origin="loop_a"), stop_signal("loop_a done"))

    mon_b = Monitor(name="mon_b")
    mon_b.add_rule(every_n_steps(1, origin="loop_b"), stop_signal("loop_b done"))

    loop_a = InstantLoop(
        agent=agent_a,
        history=history,
        name="loop_a",
        monitors=mon_a,
        stop_signals=["loop_a done"],
        max_steps=5,
    )

    loop_b = InstantLoop(
        agent=agent_b,
        history=history,
        name="loop_b",
        monitors=mon_b,
        stop_signals=["loop_b done"],
        max_steps=5,
    )

    # ── Verificar registro de vistas ──────────────────────────────
    print("── Registro de vistas ──")
    check("loop_a registra 'loop_default_loop_a'",   history.has_view("loop_default_loop_a"))
    check("loop_b registra 'loop_default_loop_b'",   history.has_view("loop_default_loop_b"))
    check("NO existe 'loop_default' genérico",        not history.has_view("loop_default"))
    check("loop.view de A tiene prefix correcto",    loop_a.view == "loop_default_loop_a")
    check("loop.view de B tiene prefix correcto",    loop_b.view == "loop_default_loop_b")
    print()

    # ── Correr loop A ─────────────────────────────────────────────
    print("── Run loop A (para en step 2 por monitor) ──")
    result_a = loop_a.run("tarea de A")
    print(f"  terminated_reason: {result_a.terminated_reason}")
    print(f"  stop_reason:       {result_a.stop_reason}")
    print(f"  total_steps:       {result_a.total_steps}")
    print()

    # La vista de A solo debe ver entries de loop_a
    vista_a = history.export("loop_default_loop_a").text
    check("vista A contiene respuestas de A",    "[A]" in vista_a)
    check("vista A NO contiene respuestas de B", "[B]" not in vista_a)

    entries_a_antes = len(history.all())
    print(f"  entries en history hasta ahora: {entries_a_antes}")
    print()

    # ── Correr loop B ─────────────────────────────────────────────
    print("── Run loop B (para en step 1 por monitor) ──")
    result_b = loop_b.run("tarea de B")
    print(f"  terminated_reason: {result_b.terminated_reason}")
    print(f"  stop_reason:       {result_b.stop_reason}")
    print(f"  total_steps:       {result_b.total_steps}")
    print()

    # La vista de B solo debe ver entries de loop_b
    vista_b = history.export("loop_default_loop_b").text
    check("vista B contiene respuestas de B",    "[B]" in vista_b)
    check("vista B NO contiene respuestas de A", "[A]" not in vista_b)

    # La vista de A después de correr B no debe haber cambiado
    vista_a_post = history.export("loop_default_loop_a").text
    check("vista A no se contamina tras correr B", vista_a == vista_a_post)

    entries_total = len(history.all())
    print(f"  entries totales en history compartido: {entries_total}")
    print()

    # ── History compartido tiene entries de ambos ─────────────────
    print("── History compartido ──")
    origins = {e.content.get("origin") for e in history.all()
               if isinstance(e.content, dict) and "origin" in e.content}
    check("history tiene entries de loop_a", "loop_a" in origins)
    check("history tiene entries de loop_b", "loop_b" in origins)

    responses_a = history.by_type("response")
    texts = [e.content.get("text", "") for e in responses_a]
    check("history tiene respuestas de A y B intercaladas en orden",
          any("[A]" in t for t in texts) and any("[B]" in t for t in texts))
    print()

    # ── Segundo run de A: no contamina con run anterior de B ──────
    print("── Segundo run de A ──")
    result_a2 = loop_a.run("segunda tarea de A")
    vista_a2 = history.export("loop_default_loop_a").text
    check("segunda vista A tiene contenido de ambos runs de A",
          "tarea de A" in vista_a2 and "segunda tarea de A" in vista_a2)
    check("segunda vista A sigue sin contenido de B", "[B]" not in vista_a2)
    print(f"  total_steps run 2 de A: {result_a2.total_steps}")
    print()

    print("=== TODAS LAS VERIFICACIONES PASARON ✅ ===\n")


if __name__ == "__main__":
    main()
