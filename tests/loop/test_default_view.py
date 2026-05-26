"""
Tests de la vista ``loop_default`` y de ``RenderedPrompt`` (PR 8).

Doc rector: docs/design/loop-design.md líneas 665-842.
"""
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from instantneo.history import History
from instantneo.loop.default_view import (
    RenderedPrompt, loop_default, _markdown_format_default,
)


def _setup_history_with_run(
    *,
    origin="test_loop",
    run_id="run-001",
    max_steps=10,
    user_prompt="¿qué pasa?",
    user_images=None,
    image_detail=None,
    n_steps=0,
):
    """Construye un History simulando lo que el Loop habría hecho.

    n_steps: cuántos steps "completos" simular (con step_start, response,
    step_end). Si 0, solo run_start + prompt.
    """
    h = History()
    h.append(author="orchestrator", type="run_start", content={
        "origin": origin, "run_id": run_id,
        "started_at": "2026-05-11T10:00:00Z",
        "agent": {"name": "agent", "provider": "openai", "model": "gpt-5-mini"},
        "loop":  {"name": origin, "max_steps": max_steps, "view": "loop_default",
                  "stop_signals": [], "stop_tool": None, "debug": False},
    })
    h.append(author="user", type="prompt", content={
        "text": user_prompt, "images": user_images, "image_detail": image_detail,
        "origin": origin, "run_id": run_id,
    })
    for i in range(1, n_steps + 1):
        h.append(author="orchestrator", type="step_start",
                 content={"origin": origin, "run_id": run_id, "step_num": i})
        h.append(author="agent", type="response",
                 content={
                     "text": f"respuesta turno {i}",
                     "reasoning": None,
                     "finish_reason": "stop",
                     "usage": None,
                     "origin": origin, "run_id": run_id, "turn_num": i,
                 })
        h.append(author="orchestrator", type="step_end",
                 content={"origin": origin, "run_id": run_id, "step_num": i,
                          "duration_ms": 100.0})
    return h


# ════════════════════════════════════════════════════════════════════
# RenderedPrompt
# ════════════════════════════════════════════════════════════════════

def test_rendered_prompt_defaults() -> None:
    rp = RenderedPrompt(text="hola")
    assert rp.text == "hola"
    assert rp.images is None
    assert rp.image_detail is None
    assert rp.stop_reason is None


def test_rendered_prompt_with_all_fields() -> None:
    rp = RenderedPrompt(
        text="t", images=["a", "b"], image_detail="high",
        stop_reason="manual",
    )
    assert rp.images == ["a", "b"]
    assert rp.image_detail == "high"
    assert rp.stop_reason == "manual"


# ════════════════════════════════════════════════════════════════════
# loop_default — comportamiento básico
# ════════════════════════════════════════════════════════════════════

def test_loop_default_returns_rendered_prompt() -> None:
    h = _setup_history_with_run()
    rp = loop_default(h)
    assert isinstance(rp, RenderedPrompt)
    assert isinstance(rp.text, str)
    assert rp.images is None  # sin imágenes pasadas
    assert rp.stop_reason is None


def test_loop_default_includes_user_prompt_in_text() -> None:
    h = _setup_history_with_run(user_prompt="explicame X")
    rp = loop_default(h)
    assert "explicame X" in rp.text


def test_loop_default_includes_response_in_text() -> None:
    h = _setup_history_with_run(n_steps=1)
    rp = loop_default(h)
    assert "respuesta turno 1" in rp.text


def test_loop_default_filters_by_current_run_id() -> None:
    """Entries de runs anteriores no aparecen en el render del run actual."""
    h = History()
    # Run 1 — viejo
    h.append(author="orchestrator", type="run_start", content={
        "origin": "loop", "run_id": "OLD-RUN", "started_at": "...",
        "agent": {}, "loop": {},
    })
    h.append(author="user", type="prompt", content={
        "text": "viejo prompt", "origin": "loop", "run_id": "OLD-RUN",
    })
    h.append(author="agent", type="response", content={
        "text": "respuesta vieja", "run_id": "OLD-RUN", "turn_num": 1,
        "origin": "loop",
    })
    # Run 2 — actual
    h.append(author="orchestrator", type="run_start", content={
        "origin": "loop", "run_id": "NEW-RUN", "started_at": "...",
        "agent": {}, "loop": {},
    })
    h.append(author="user", type="prompt", content={
        "text": "nuevo prompt", "origin": "loop", "run_id": "NEW-RUN",
    })

    rp = loop_default(h)
    assert "nuevo prompt" in rp.text
    assert "viejo prompt" not in rp.text
    assert "respuesta vieja" not in rp.text


def test_loop_default_show_all_runs_true_includes_old_entries() -> None:
    h = History()
    h.append(author="orchestrator", type="run_start", content={
        "origin": "loop", "run_id": "OLD", "agent": {}, "loop": {},
    })
    h.append(author="user", type="prompt", content={
        "text": "viejo", "origin": "loop", "run_id": "OLD",
    })
    h.append(author="orchestrator", type="run_start", content={
        "origin": "loop", "run_id": "NEW", "agent": {}, "loop": {},
    })
    h.append(author="user", type="prompt", content={
        "text": "nuevo", "origin": "loop", "run_id": "NEW",
    })

    rp = loop_default(h, show_all_runs=True)
    assert "viejo" in rp.text
    assert "nuevo" in rp.text


# ════════════════════════════════════════════════════════════════════
# Image policies
# ════════════════════════════════════════════════════════════════════

def test_loop_default_image_policy_every_turn() -> None:
    h = _setup_history_with_run(
        user_images=[{"source": "img.jpg"}],
        image_detail="high",
    )
    rp = loop_default(h, image_policy="every_turn")
    assert rp.images == ["img.jpg"]
    assert rp.image_detail == "high"


def test_loop_default_image_policy_none() -> None:
    h = _setup_history_with_run(
        user_images=[{"source": "img.jpg"}],
        image_detail="high",
    )
    rp = loop_default(h, image_policy="none")
    assert rp.images is None
    assert rp.image_detail is None


def test_loop_default_image_policy_first_only_in_first_render() -> None:
    """En el primer render del run (antes de que el Loop appendee
    step_start del step 1), first_only DEBE incluir la imagen: la vista
    se evalúa para preparar el step 1 que está por ejecutarse."""
    h = _setup_history_with_run(
        user_images=[{"source": "img.jpg"}],
        image_detail="low",
        n_steps=0,
    )
    rp = loop_default(h, image_policy="first_only")
    assert rp.images == ["img.jpg"]


def test_loop_default_image_policy_first_only_excludes_after_first_step() -> None:
    """Después de ejecutado el step 1 (cuando ya hay step_start del
    step 1 en el History), la vista se evalúa para preparar el step 2.
    first_only NO debe incluir la imagen en ese render."""
    h = _setup_history_with_run(
        user_images=[{"source": "img.jpg"}],
        image_detail="low",
        n_steps=0,
    )
    h.append(author="orchestrator", type="step_start",
             content={"origin": "test_loop", "run_id": "run-001", "step_num": 1})
    rp = loop_default(h, image_policy="first_only")
    assert rp.images is None


def test_loop_default_no_images_in_prompt_returns_none() -> None:
    h = _setup_history_with_run()  # sin imagen
    rp = loop_default(h, image_policy="every_turn")
    assert rp.images is None


# ════════════════════════════════════════════════════════════════════
# _markdown_format_default — header de turnos
# ════════════════════════════════════════════════════════════════════

def test_markdown_format_includes_turn_header() -> None:
    h = _setup_history_with_run(n_steps=2)
    rp = loop_default(h)
    assert "Turno 1" in rp.text
    assert "Turno 2" in rp.text


def test_markdown_format_includes_max_steps_in_header() -> None:
    h = _setup_history_with_run(max_steps=15)
    rp = loop_default(h)
    assert "de 15" in rp.text


def test_markdown_format_no_max_when_zero() -> None:
    """max_steps=0 (sin cap) NO menciona 'de N'."""
    h = _setup_history_with_run(max_steps=0)
    rp = loop_default(h)
    assert "Estás en el turno" in rp.text
    # No debería incluir "de 0" o "de ?"
    assert "de 0" not in rp.text


def test_markdown_format_renders_image_refs_textually() -> None:
    h = _setup_history_with_run(
        user_images=[{"source": "https://example.com/cat.jpg"}],
    )
    rp = loop_default(h)
    # Las imágenes aparecen como referencias textuales en el markdown
    assert "imágenes adjuntas" in rp.text
    assert "cat.jpg" in rp.text


# ════════════════════════════════════════════════════════════════════
# Runner
# ════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    tests = [
        ("rendered_prompt_defaults",                   test_rendered_prompt_defaults),
        ("rendered_prompt_with_all_fields",            test_rendered_prompt_with_all_fields),
        ("loop_default_returns_rendered_prompt",       test_loop_default_returns_rendered_prompt),
        ("loop_default_includes_user_prompt_in_text",  test_loop_default_includes_user_prompt_in_text),
        ("loop_default_includes_response_in_text",     test_loop_default_includes_response_in_text),
        ("loop_default_filters_by_current_run_id",     test_loop_default_filters_by_current_run_id),
        ("loop_default_show_all_runs_true_includes_old_entries", test_loop_default_show_all_runs_true_includes_old_entries),
        ("loop_default_image_policy_every_turn",       test_loop_default_image_policy_every_turn),
        ("loop_default_image_policy_none",             test_loop_default_image_policy_none),
        ("loop_default_image_policy_first_only_in_first_render",
         test_loop_default_image_policy_first_only_in_first_render),
        ("loop_default_image_policy_first_only_excludes_after_first_step",
         test_loop_default_image_policy_first_only_excludes_after_first_step),
        ("loop_default_no_images_in_prompt_returns_none", test_loop_default_no_images_in_prompt_returns_none),
        ("markdown_format_includes_turn_header",       test_markdown_format_includes_turn_header),
        ("markdown_format_includes_max_steps_in_header", test_markdown_format_includes_max_steps_in_header),
        ("markdown_format_no_max_when_zero",           test_markdown_format_no_max_when_zero),
        ("markdown_format_renders_image_refs_textually", test_markdown_format_renders_image_refs_textually),
    ]
    failures = []
    for name, fn in tests:
        try:
            fn()
            print(f"  PASS  {name}")
        except Exception as e:
            failures.append((name, e))
            print(f"  FAIL  {name}: {type(e).__name__}: {e}")
    print()
    total = len(tests)
    print(f"PASS: {total - len(failures)} / {total}")
    if failures:
        sys.exit(1)
