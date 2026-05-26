"""
Tests de ``instantneo.history.history``: Entry y History.

Cubre PR 2 del meta-plan v2 — capa History standalone (sin bridge,
sin Monitor, sin vistas built-in). El método ``append_from_run`` se
agrega en PR 5 junto con el bridge.

Dual-mode (igual que tests/test_imports.py):
- pytest-compatible: ``pytest tests/history/``.
- runnable standalone: ``python3 tests/history/test_history.py``.

Inserta la raíz del worktree en sys.path para asegurar importar el
``instantneo`` local y no la versión instalada en site-packages.
"""

import dataclasses
import json
import sys
import time
from datetime import datetime
from pathlib import Path

# Importar el `instantneo` local de este worktree.
_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from instantneo.history import Entry, History


# ════════════════════════════════════════════════════════════════════
# Tests sobre Entry
# ════════════════════════════════════════════════════════════════════

def test_entry_is_frozen() -> None:
    """Una Entry creada no puede modificar sus campos."""
    e = Entry(id=1, author="u", timestamp=1.0, type="t", content={}, refs=())
    try:
        e.id = 99  # type: ignore[misc]
    except dataclasses.FrozenInstanceError:
        return
    raise AssertionError("Entry debería rechazar mutación de campos (frozen=True)")


def test_entry_default_refs_is_empty_tuple() -> None:
    """Si no se pasa refs, queda como tuple vacía."""
    e = Entry(id=1, author="u", timestamp=1.0, type="t", content={})
    assert e.refs == ()
    assert isinstance(e.refs, tuple)


def test_entry_default_content_is_empty_dict() -> None:
    """Si no se pasa content, queda como dict vacío (no None)."""
    e = Entry(id=1, author="u", timestamp=1.0, type="t")
    assert e.content == {}


def test_entry_to_dict_is_json_safe() -> None:
    """``Entry.to_dict()`` produce un dict que json.dumps acepta sin errores."""
    e = Entry(
        id=42, author="user", timestamp=1234.5,
        type="message", content={"text": "hola", "n": 7}, refs=(1, 2),
    )
    d = e.to_dict()
    # json.dumps no debe fallar
    json.dumps(d)
    # refs como list, no tuple
    assert d["refs"] == [1, 2]
    assert isinstance(d["refs"], list)
    # campos básicos preservados
    assert d["id"] == 42
    assert d["author"] == "user"
    assert d["timestamp"] == 1234.5
    assert d["type"] == "message"
    assert d["content"] == {"text": "hola", "n": 7}


def test_entry_to_dict_handles_non_json_safe_content() -> None:
    """Si content contiene tipos no-JSON-safe (datetime, etc.), to_dict
    no levanta excepción; serializa defensivamente vía str."""
    e = Entry(
        id=1, author="u", timestamp=1.0, type="t",
        content={"when": datetime(2024, 1, 15, 12, 0, 0)},
    )
    d = e.to_dict()
    # No debe levantar
    s = json.dumps(d)
    # Y debe contener una representación stringificada del datetime
    assert "2024-01-15" in s


# ════════════════════════════════════════════════════════════════════
# Tests sobre History.__init__
# ════════════════════════════════════════════════════════════════════

def test_constructor_default_no_name() -> None:
    """``History()`` funciona; name queda en None."""
    h = History()
    assert h.name is None


def test_constructor_with_name() -> None:
    """``History(name='x')`` guarda el nombre."""
    h = History(name="main")
    assert h.name == "main"


def test_constructor_starts_empty() -> None:
    """``History().all()`` es lista vacía al inicio."""
    h = History()
    assert h.all() == []


def test_constructor_next_id_starts_at_1() -> None:
    """La primera entry tiene id == 1."""
    h = History()
    e = h.append(author="u", type="t", content={})
    assert e.id == 1


# ════════════════════════════════════════════════════════════════════
# Tests sobre History.append
# ════════════════════════════════════════════════════════════════════

def test_append_assigns_id_and_timestamp() -> None:
    """append() retorna Entry con id auto-asignado y timestamp > 0."""
    h = History()
    e = h.append(author="u", type="t", content={"k": "v"})
    assert e.id == 1
    assert e.timestamp > 0
    assert e.author == "u"
    assert e.type == "t"
    assert e.content == {"k": "v"}


def test_append_returns_created_entry() -> None:
    """La entry retornada es la misma que está en history.all()[-1]."""
    h = History()
    e = h.append(author="u", type="t", content={})
    last = h.all()[-1]
    assert e is last or e == last


def test_append_increments_id() -> None:
    """Dos appends consecutivos producen ids 1 y 2."""
    h = History()
    a = h.append(author="u", type="t", content={})
    b = h.append(author="u", type="t", content={})
    assert a.id == 1
    assert b.id == 2


def test_append_accepts_timestamp_override() -> None:
    """append(timestamp=X) preserva ese timestamp en la entry."""
    h = History()
    e = h.append(author="u", type="t", content={}, timestamp=1234.5)
    assert e.timestamp == 1234.5


def test_append_default_refs_empty_tuple() -> None:
    """Sin pasar refs, la entry queda con refs=()."""
    h = History()
    e = h.append(author="u", type="t", content={})
    assert e.refs == ()
    assert isinstance(e.refs, tuple)


def test_append_with_refs() -> None:
    """Pasar refs=(1,2) los preserva como tuple."""
    h = History()
    h.append(author="u", type="t", content={})
    h.append(author="u", type="t", content={})
    e = h.append(author="u", type="t", content={}, refs=(1, 2))
    assert e.refs == (1, 2)
    assert isinstance(e.refs, tuple)


def test_append_refs_passed_as_list_converted_to_tuple() -> None:
    """append acepta refs como list por DX, pero la entry los guarda como tuple."""
    h = History()
    h.append(author="u", type="t", content={})
    e = h.append(author="u", type="t", content={}, refs=[1])  # type: ignore[arg-type]
    assert e.refs == (1,)
    assert isinstance(e.refs, tuple)


def test_append_does_not_validate_type_or_content() -> None:
    """El History NO valida type ni content. Cualquier string y cualquier dict."""
    h = History()
    # type raro, content con tipos exóticos: debe aceptarse sin error.
    h.append(author="anyone", type="@!#$%^&*()", content={"obj": set([1, 2])})


# ════════════════════════════════════════════════════════════════════
# Tests sobre get, all, by_author, by_type
# ════════════════════════════════════════════════════════════════════

def test_get_returns_entry_by_id() -> None:
    """get(id) devuelve la entry correcta."""
    h = History()
    h.append(author="u", type="t", content={"n": 1})
    h.append(author="u", type="t", content={"n": 2})
    e = h.get(2)
    assert e.id == 2
    assert e.content == {"n": 2}


def test_get_raises_on_missing() -> None:
    """get(id_inexistente) levanta KeyError."""
    h = History()
    h.append(author="u", type="t", content={})
    try:
        h.get(999)
    except KeyError:
        return
    raise AssertionError("get(999) debió levantar KeyError")


def test_all_chronological_by_id() -> None:
    """all() retorna entries en orden de id ascendente."""
    h = History()
    for i in range(5):
        h.append(author="u", type="t", content={"i": i})
    ids = [e.id for e in h.all()]
    assert ids == [1, 2, 3, 4, 5]


def test_all_returns_a_copy() -> None:
    """Mutar el resultado de all() no afecta el History interno."""
    h = History()
    h.append(author="u", type="t", content={})
    lst = h.all()
    lst.append("garbage")  # type: ignore[arg-type]
    assert len(h.all()) == 1


def test_by_author_matches() -> None:
    """by_author filtra correctamente."""
    h = History()
    h.append(author="A", type="t", content={})
    h.append(author="B", type="t", content={})
    h.append(author="A", type="t", content={})
    result = h.by_author("A")
    assert len(result) == 2
    assert all(e.author == "A" for e in result)


def test_by_author_empty_when_no_match() -> None:
    """by_author sin match devuelve lista vacía."""
    h = History()
    h.append(author="A", type="t", content={})
    assert h.by_author("Z") == []


def test_by_type_matches() -> None:
    """by_type filtra correctamente."""
    h = History()
    h.append(author="u", type="message", content={})
    h.append(author="u", type="note", content={})
    h.append(author="u", type="message", content={})
    result = h.by_type("message")
    assert len(result) == 2
    assert all(e.type == "message" for e in result)


def test_by_type_empty_when_no_match() -> None:
    """by_type sin match devuelve lista vacía."""
    h = History()
    h.append(author="u", type="message", content={})
    assert h.by_type("noexiste") == []


# ════════════════════════════════════════════════════════════════════
# Tests sobre views
# ════════════════════════════════════════════════════════════════════

def test_view_decorator_registers_function() -> None:
    """@history.view('v') registra la función."""
    h = History()

    @h.view("v")
    def my_view(history):
        return len(history.all())

    assert h.has_view("v")
    assert "v" in h.list_views()


def test_view_decorator_returns_original_function() -> None:
    """El decorator devuelve la función original, no envuelta, sigue invocable directamente."""
    h = History()

    @h.view("v")
    def my_view(history):
        return "ok"

    # Llamar directo a my_view debe funcionar igual.
    assert my_view(h) == "ok"


def test_add_view_imperative_equivalent() -> None:
    """add_view(name, fn) produce el mismo efecto que el decorator."""
    h = History()

    def my_view(history):
        return "imperative"

    h.add_view("v", my_view)
    assert h.export("v") == "imperative"


def test_add_view_overrides_existing() -> None:
    """add_view sobreescribe sin error si el nombre ya existía."""
    h = History()
    h.add_view("v", lambda hist: "first")
    h.add_view("v", lambda hist: "second")
    assert h.export("v") == "second"


def test_export_runs_function_with_history() -> None:
    """export(name) invoca la función registrada pasándole el history."""
    h = History()
    h.append(author="u", type="t", content={"text": "hola"})

    @h.view("counter")
    def counter(history):
        return len(history.all())

    assert h.export("counter") == 1


def test_export_raises_on_unknown_view() -> None:
    """export de vista no registrada levanta KeyError."""
    h = History()
    try:
        h.export("noexiste")
    except KeyError:
        return
    raise AssertionError("export('noexiste') debió levantar KeyError")


def test_list_views_empty_initially() -> None:
    """list_views() es lista vacía al crear el History."""
    assert History().list_views() == []


def test_list_views_after_registration() -> None:
    """list_views() refleja los nombres registrados."""
    h = History()
    h.add_view("a", lambda hist: 1)
    h.add_view("b", lambda hist: 2)
    names = h.list_views()
    assert set(names) == {"a", "b"}


def test_has_view_true_after_register() -> None:
    """has_view(name) es True después de registrar."""
    h = History()
    h.add_view("v", lambda hist: 0)
    assert h.has_view("v") is True


def test_has_view_false_initially() -> None:
    """has_view(name) es False antes de registrar."""
    assert History().has_view("v") is False


# ════════════════════════════════════════════════════════════════════
# Tests sobre serialización
# ════════════════════════════════════════════════════════════════════

def test_to_dicts_returns_list_of_dicts() -> None:
    """to_dicts() devuelve list[dict], uno por entry."""
    h = History()
    h.append(author="u", type="t", content={"k": "v"})
    h.append(author="u", type="t", content={})
    out = h.to_dicts()
    assert isinstance(out, list)
    assert len(out) == 2
    assert all(isinstance(d, dict) for d in out)
    # Cada dict tiene las keys esperadas
    expected_keys = {"id", "author", "timestamp", "type", "content", "refs"}
    for d in out:
        assert expected_keys.issubset(d.keys())


def test_to_dicts_refs_as_list() -> None:
    """En la salida, refs es list (no tuple — JSON-safe)."""
    h = History()
    h.append(author="u", type="t", content={})
    h.append(author="u", type="t", content={}, refs=(1,))
    out = h.to_dicts()
    assert out[1]["refs"] == [1]
    assert isinstance(out[1]["refs"], list)


def test_to_json_is_valid_json() -> None:
    """to_json() produce JSON parseable."""
    h = History()
    h.append(author="u", type="t", content={"n": 1})
    h.append(author="u", type="t", content={"n": 2})
    s = h.to_json()
    parsed = json.loads(s)
    assert isinstance(parsed, list)
    assert len(parsed) == 2


def test_to_json_roundtrip() -> None:
    """to_json -> from_dicts(json.loads) preserva entries."""
    h1 = History()
    h1.append(author="user", type="msg", content={"text": "hi"}, timestamp=1000.0)
    h1.append(author="agent", type="reply", content={"text": "hello"}, refs=(1,), timestamp=1001.0)

    s = h1.to_json()
    h2 = History.from_dicts(json.loads(s))

    assert len(h2.all()) == 2
    a, b = h2.all()
    assert a.id == 1 and a.author == "user" and a.timestamp == 1000.0
    assert b.id == 2 and b.author == "agent" and b.refs == (1,)
    assert isinstance(b.refs, tuple)


def test_from_dicts_restores_refs_as_tuple() -> None:
    """En el roundtrip, refs vuelve a ser tuple (no list)."""
    h = History()
    h.append(author="u", type="t", content={})
    h.append(author="u", type="t", content={}, refs=(1,))
    h2 = History.from_dicts(h.to_dicts())
    for entry in h2.all():
        assert isinstance(entry.refs, tuple)


def test_from_dicts_sets_next_id_correctly() -> None:
    """Después de from_dicts, el próximo append tiene id = max(ids) + 1."""
    h = History()
    h.append(author="u", type="t", content={})  # id=1
    h.append(author="u", type="t", content={})  # id=2

    h2 = History.from_dicts(h.to_dicts())
    new = h2.append(author="u", type="t", content={})
    assert new.id == 3


def test_from_dicts_empty_starts_at_1() -> None:
    """from_dicts([]) produce History vacío; primer append id=1."""
    h = History.from_dicts([])
    assert h.all() == []
    new = h.append(author="u", type="t", content={})
    assert new.id == 1


def test_from_dicts_preserves_name_if_passed() -> None:
    """from_dicts acepta name kwarg para el History reconstruido."""
    h = History.from_dicts([], name="restored")
    assert h.name == "restored"


# ════════════════════════════════════════════════════════════════════
# Tests sobre reset
# ════════════════════════════════════════════════════════════════════

def test_reset_empties_entries() -> None:
    """Después de reset(), all() es lista vacía."""
    h = History()
    h.append(author="u", type="t", content={})
    h.append(author="u", type="t", content={})
    h.reset()
    assert h.all() == []


def test_reset_resets_id_counter() -> None:
    """Después de reset(), el próximo append tiene id=1."""
    h = History()
    h.append(author="u", type="t", content={})
    h.append(author="u", type="t", content={})
    h.reset()
    new = h.append(author="u", type="t", content={})
    assert new.id == 1


def test_reset_does_not_clear_views() -> None:
    """Las vistas registradas sobreviven al reset (son metadata)."""
    h = History()
    h.add_view("v", lambda hist: "view-ok")
    h.append(author="u", type="t", content={})
    h.reset()
    assert h.has_view("v") is True
    assert h.export("v") == "view-ok"


# ════════════════════════════════════════════════════════════════════
# Tests de "uso integrado" — combinar capacidades en escenarios reales
# ════════════════════════════════════════════════════════════════════

def test_integrated_view_filters_by_type() -> None:
    """Vista realista que filtra entries por type — patrón canónico."""
    h = History()
    h.append(author="user", type="message", content={"text": "hola"})
    h.append(author="agent", type="response", content={"text": "qué tal"})
    h.append(author="orchestrator", type="step_end", content={})

    @h.view("conversation_only")
    def conversation_only(history):
        return [e for e in history.all() if e.type in {"message", "response"}]

    out = h.export("conversation_only")
    assert len(out) == 2
    assert {e.type for e in out} == {"message", "response"}


def test_integrated_refs_query() -> None:
    """Encontrar entries que referencian a una entry específica vía refs."""
    h = History()
    h.append(author="user", type="message", content={"text": "a"})  # id=1
    h.append(author="user", type="message", content={"text": "b"})  # id=2
    h.append(
        author="agent", type="summary",
        content={"text": "resumen"}, refs=(1, 2),
    )  # id=3

    referring_to_1 = [e for e in h.all() if 1 in e.refs]
    assert len(referring_to_1) == 1
    assert referring_to_1[0].id == 3


# ════════════════════════════════════════════════════════════════════
# Tests que DOCUMENTAN comportamientos límite / gotchas
#
# Estos no son "bugs"; son comportamientos del modelo actual que vale
# la pena tener capturados para que cualquier cambio futuro a
# defensive-copy o validación rompa explícitamente uno de estos tests
# (forzando que la decisión sea consciente).
# ════════════════════════════════════════════════════════════════════

def test_content_mutation_visible_in_entry() -> None:
    """Documenta: `frozen=True` no protege mutación del dict `content` adentro.

    El dict que el caller pasa a `append` se guarda por referencia. Mutarlo
    después (o mutar `entry.content` directamente) cambia lo que se ve en
    el History. Esto es Python normal: `frozen=True` solo bloquea
    reasignación de campos, no mutación de valores mutables.

    Si en el futuro queremos endurecer esto (defensive shallow-copy en
    `append`, o wrap en `MappingProxyType`), este test va a fallar y
    obligará a tomar la decisión consciente.
    """
    h = History()
    original = {"k": "valor_inicial"}
    e = h.append(author="u", type="t", content=original)

    # Caso A: mutar el dict ORIGINAL afecta la entry.
    original["k"] = "mutado_desde_fuera"
    assert e.content["k"] == "mutado_desde_fuera"
    assert h.get(1).content["k"] == "mutado_desde_fuera"

    # Caso B: mutar entry.content directamente también funciona.
    e.content["k"] = "mutado_via_entry"
    assert h.get(1).content["k"] == "mutado_via_entry"


def test_from_dicts_with_duplicate_ids_silently_keeps_all() -> None:
    """Documenta: `from_dicts` no valida unicidad de ids.

    Si los dicts de entrada tienen ids repetidos, ambas entries se
    agregan al History. `get(id)` devuelve la PRIMERA en orden de
    aparición (por la búsqueda lineal). El doc no impone esto como
    validación explícita; este test captura el comportamiento actual
    para que cualquier cambio futuro a validación sea consciente.
    """
    h = History.from_dicts([
        {"id": 1, "author": "u", "timestamp": 1.0, "type": "t", "content": {"i": 1}, "refs": []},
        {"id": 1, "author": "u", "timestamp": 2.0, "type": "t", "content": {"i": 2}, "refs": []},
    ])
    # Ambas entries quedan en _entries.
    assert len(h.all()) == 2
    # get(1) devuelve la PRIMERA (scan lineal).
    assert h.get(1).content == {"i": 1}
    # _next_id se ajustó a max(ids)+1 = 2, así que el próximo append
    # tendría id=2 (igual a la segunda existente, lo cual también es
    # un escenario de corrupción potencial).
    new = h.append(author="u", type="t", content={"i": 3})
    assert new.id == 2


def test_multiple_histories_are_isolated() -> None:
    """Dos History independientes no comparten estado.

    Importante porque la convención multi-history es real (un Loop
    puede tener su History, un Pipeline futuro otro distinto, etc.).
    """
    h1 = History(name="a")
    h2 = History(name="b")

    h1.append(author="u", type="t", content={"in": "h1"})
    h2.append(author="u", type="t", content={"in": "h2"})

    assert len(h1.all()) == 1
    assert len(h2.all()) == 1
    assert h1.all()[0].content == {"in": "h1"}
    assert h2.all()[0].content == {"in": "h2"}

    # Ids independientes (no comparten counter)
    assert h1.all()[0].id == 1
    assert h2.all()[0].id == 1

    # Views también independientes
    h1.add_view("v", lambda h: "view_de_h1")
    assert h1.has_view("v") is True
    assert h2.has_view("v") is False


def test_view_function_can_be_registered_on_multiple_histories() -> None:
    """Una función view importable se puede registrar en varios histories.

    Patrón del doc (líneas 167–169): mismas funciones reusables en
    múltiples instancias. Confirma que el History no toma ownership
    de la función ni la "ata" al primer history que la registra.
    """
    def render(history):
        return [e.content for e in history.all()]

    h1 = History()
    h2 = History()
    h1.add_view("render", render)
    h2.add_view("render", render)

    h1.append(author="u", type="t", content={"x": 1})
    h2.append(author="u", type="t", content={"y": 2})

    assert h1.export("render") == [{"x": 1}]
    assert h2.export("render") == [{"y": 2}]


def test_to_dict_does_not_mutate_original_content() -> None:
    """Llamar `to_dict()` no modifica el `content` de la entry original.

    Aun cuando `content` tiene tipos no-JSON-safe y `to_dict()` produce
    una versión stringificada, el `content` original de la entry queda
    intacto. Importante porque las vistas pueden llamar `to_dict()` en
    bucle y no deberían tener efecto lateral.
    """
    from datetime import datetime
    original_dt = datetime(2024, 1, 15, 12, 0, 0)
    h = History()
    e = h.append(author="u", type="t", content={"when": original_dt})

    # Capturar el id() del datetime original
    id_before = id(e.content["when"])
    d = e.to_dict()  # serialización JSON-safe; debería ser una copia

    # to_dict produjo una versión stringificada en el dict resultante
    assert isinstance(d["content"]["when"], str)

    # Pero el content original de la entry NO cambió
    assert isinstance(e.content["when"], datetime)
    assert id(e.content["when"]) == id_before
    assert e.content["when"] == original_dt


# ════════════════════════════════════════════════════════════════════
# Runner standalone
# ════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    tests = [
        # Entry
        ("entry_is_frozen",                          test_entry_is_frozen),
        ("entry_default_refs_is_empty_tuple",        test_entry_default_refs_is_empty_tuple),
        ("entry_default_content_is_empty_dict",      test_entry_default_content_is_empty_dict),
        ("entry_to_dict_is_json_safe",               test_entry_to_dict_is_json_safe),
        ("entry_to_dict_handles_non_json_safe_content", test_entry_to_dict_handles_non_json_safe_content),
        # Constructor
        ("constructor_default_no_name",              test_constructor_default_no_name),
        ("constructor_with_name",                    test_constructor_with_name),
        ("constructor_starts_empty",                 test_constructor_starts_empty),
        ("constructor_next_id_starts_at_1",          test_constructor_next_id_starts_at_1),
        # append
        ("append_assigns_id_and_timestamp",          test_append_assigns_id_and_timestamp),
        ("append_returns_created_entry",             test_append_returns_created_entry),
        ("append_increments_id",                     test_append_increments_id),
        ("append_accepts_timestamp_override",        test_append_accepts_timestamp_override),
        ("append_default_refs_empty_tuple",          test_append_default_refs_empty_tuple),
        ("append_with_refs",                         test_append_with_refs),
        ("append_refs_passed_as_list_converted_to_tuple", test_append_refs_passed_as_list_converted_to_tuple),
        ("append_does_not_validate_type_or_content", test_append_does_not_validate_type_or_content),
        # get, all, by_author, by_type
        ("get_returns_entry_by_id",                  test_get_returns_entry_by_id),
        ("get_raises_on_missing",                    test_get_raises_on_missing),
        ("all_chronological_by_id",                  test_all_chronological_by_id),
        ("all_returns_a_copy",                       test_all_returns_a_copy),
        ("by_author_matches",                        test_by_author_matches),
        ("by_author_empty_when_no_match",            test_by_author_empty_when_no_match),
        ("by_type_matches",                          test_by_type_matches),
        ("by_type_empty_when_no_match",              test_by_type_empty_when_no_match),
        # views
        ("view_decorator_registers_function",        test_view_decorator_registers_function),
        ("view_decorator_returns_original_function", test_view_decorator_returns_original_function),
        ("add_view_imperative_equivalent",           test_add_view_imperative_equivalent),
        ("add_view_overrides_existing",              test_add_view_overrides_existing),
        ("export_runs_function_with_history",        test_export_runs_function_with_history),
        ("export_raises_on_unknown_view",            test_export_raises_on_unknown_view),
        ("list_views_empty_initially",               test_list_views_empty_initially),
        ("list_views_after_registration",            test_list_views_after_registration),
        ("has_view_true_after_register",             test_has_view_true_after_register),
        ("has_view_false_initially",                 test_has_view_false_initially),
        # serialización
        ("to_dicts_returns_list_of_dicts",           test_to_dicts_returns_list_of_dicts),
        ("to_dicts_refs_as_list",                    test_to_dicts_refs_as_list),
        ("to_json_is_valid_json",                    test_to_json_is_valid_json),
        ("to_json_roundtrip",                        test_to_json_roundtrip),
        ("from_dicts_restores_refs_as_tuple",        test_from_dicts_restores_refs_as_tuple),
        ("from_dicts_sets_next_id_correctly",        test_from_dicts_sets_next_id_correctly),
        ("from_dicts_empty_starts_at_1",             test_from_dicts_empty_starts_at_1),
        ("from_dicts_preserves_name_if_passed",      test_from_dicts_preserves_name_if_passed),
        # reset
        ("reset_empties_entries",                    test_reset_empties_entries),
        ("reset_resets_id_counter",                  test_reset_resets_id_counter),
        ("reset_does_not_clear_views",               test_reset_does_not_clear_views),
        # integrados
        ("integrated_view_filters_by_type",          test_integrated_view_filters_by_type),
        ("integrated_refs_query",                    test_integrated_refs_query),
        # comportamientos límite documentados
        ("content_mutation_visible_in_entry",        test_content_mutation_visible_in_entry),
        ("from_dicts_with_duplicate_ids_silently_keeps_all", test_from_dicts_with_duplicate_ids_silently_keeps_all),
        ("multiple_histories_are_isolated",          test_multiple_histories_are_isolated),
        ("view_function_can_be_registered_on_multiple_histories", test_view_function_can_be_registered_on_multiple_histories),
        ("to_dict_does_not_mutate_original_content", test_to_dict_does_not_mutate_original_content),
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
    passed = total - len(failures)
    print(f"PASS: {passed} / {total}")
    if failures:
        sys.exit(1)
