"""
Ejemplo 19 — Skills estándar SKILL.md: una simple y otra real de Anthropic
============================================================================

Caso funcional
--------------
El estándar Agent Skills (https://agentskills.io) define un formato
**de carpeta** para empaquetar conocimiento (instrucciones + assets +
scripts opcionales) que un agente puede cargar y activar. Cada skill
es una carpeta con un `SKILL.md` adentro: frontmatter YAML con
`name` + `description` (+ opcionales) y un body Markdown con las
instrucciones.

En este ejemplo cargamos **dos skills de complejidad muy distinta**
para mostrar el rango del formato:

1. **`politicas_devolucion`** — skill **simple**. Solo `SKILL.md`, sin
   scripts, sin references. Pura "instrucción en formato estándar". Es
   contenido del comercio (local).

2. **`pdf`** — skill **compleja**, traída tal cual del repo oficial
   de Anthropic (https://github.com/anthropics/skills, en
   `skills/pdf`). Carpeta con `SKILL.md` + `LICENSE.txt` +
   `reference.md`. Licencia: ver
   `examples/skill_md_demos/pdf_anthropic/LICENSE.txt`.

   **Nota sobre los `scripts/`** del repo oficial: son **scripts CLI
   standalone** en Python (se ejecutan como `python script.py archivo.pdf`)
   y NO están decorados con `@tool`. La librería registra automáticamente
   solo funciones con metadata de tool, así que aunque bajáramos
   `scripts/`, no quedarían disponibles como tools del agente. Para
   integrarlos haría falta envolverlos manualmente con `@tool` +
   `subprocess`, lo cual queda fuera del alcance pedagógico de este
   ejemplo. Acá probamos lo importante: que el **parser** del estándar
   entiende sin modificación el formato oficial y expone su contenido
   correctamente.

Las dos viven juntas en un manager `caja_skills_documentos` que el
dev puede consultar con `discover()` para ver qué hay. Lo importante:
**lo que ve el dev cuando hace `discover()` es exactamente lo que ve
un agente** cuando lo navega con las nav tools (ejemplo 21).

Qué muestra este ejemplo
------------------------
1. Cargar skills SKILL.md con `load_skills.from_skill_folders` (plural).
2. Compatibilidad con un skill oficial de Anthropic — el parser de la
   librería entiende su formato sin modificación.
3. La metadata (`name`, `description`) del frontmatter es lo que se
   expone en `discover()`. Es **la cabecera** del skill — tiene que
   estar bien escrita porque ahí decide el agente si lo activa.
4. Activación de cada skill: la simple solo inyecta instrucciones; la
   compleja inyecta instrucciones y declararía sus scripts como tools
   si los hubiéramos incluido.

Cómo correr
-----------
    python3 examples/19_skills_estandar_simple_y_compleja.py
"""
import os
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

try:
    from dotenv import load_dotenv
    load_dotenv(_REPO_ROOT / ".env", override=True)
except ImportError:
    pass

from instantneo import AgentCapabilities, InstantNeo


SKILLS_ROOT = _REPO_ROOT / "examples" / "skill_md_demos"


PROVIDER = "openai"
MODEL = "gpt-4.1-mini"
API_KEY = os.environ.get("OPEN_AI_API_KEY")

if not API_KEY:
    print("ERROR: falta OPEN_AI_API_KEY en el entorno.")
    sys.exit(1)


def section(title: str) -> None:
    print()
    print("─" * 64)
    print(title)
    print("─" * 64)


def main() -> None:
    # ────────────────────────────────────────────────────────────────
    # Construimos un capability que actúa como "caja de skills"
    # ────────────────────────────────────────────────────────────────
    # `from_skill_folders` (plural) escanea un directorio y carga TODAS
    # las subcarpetas que tengan un SKILL.md adentro. Es la forma
    # ergonómica de levantar una "biblioteca de skills" sin tener que
    # listarlas una por una. Internamente usa `from_skill_folder`
    # (singular) por cada match.
    caja_skills_documentos = AgentCapabilities(
        name="caja_skills_documentos",
        description="Skills documentales del comercio (devoluciones + procesamiento de PDFs).",
    )

    cargadas = caja_skills_documentos.load_skills.from_skill_folders(str(SKILLS_ROOT))
    section("SKILLS DETECTADAS")
    print(f"  carpeta scaneada : {SKILLS_ROOT}")
    print(f"  cargadas         : {cargadas}")

    # ────────────────────────────────────────────────────────────────
    # Filtrar lo del ejemplo 18 que ya está bajo `skill_md_demos/`
    # ────────────────────────────────────────────────────────────────
    # `clasificar_gasto/` vive en la misma carpeta porque la usa el
    # ejemplo 18. Para este ejemplo nos quedamos solo con las dos que
    # queremos exhibir: la simple y la oficial.
    nombres_objetivo = {"politicas_devolucion", "pdf"}
    for nombre in list(caja_skills_documentos.skill_folders.keys()):
        if nombre not in nombres_objetivo:
            del caja_skills_documentos.skill_folders[nombre]

    print(f"  filtradas para el ejemplo : {list(caja_skills_documentos.skill_folders.keys())}")
    assert set(caja_skills_documentos.skill_folders.keys()) == nombres_objetivo

    # ────────────────────────────────────────────────────────────────
    # Lo que el dev/agente ve con discover()
    # ────────────────────────────────────────────────────────────────
    # Frontmatter de cada SKILL.md → metadata que entra al discover.
    # Si el `description` está mal escrito, el agente no va a saber
    # cuándo activar la skill. Lo aclaramos textualmente al dev.
    section("DISCOVER — vista lateral de las dos skills")
    for item in caja_skills_documentos.discover():
        print(f"\n  [{item.get('type')}] {item.get('name')}")
        print(f"     description: {item.get('description', '')[:120]}")

    # ────────────────────────────────────────────────────────────────
    # SKILL SIMPLE — solo SKILL.md, sin scripts
    # ────────────────────────────────────────────────────────────────
    # `politicas_devolucion` no tiene `scripts/`. Activarla solo
    # inyecta el body del SKILL.md como contexto del item activo.
    # No suma tools nuevas al registry.
    section("ACTIVAR `politicas_devolucion` (skill simple)")
    res_simple = caja_skills_documentos.activate("politicas_devolucion")
    print(f"  nombre activado : {res_simple['name']}")
    print(f"  tipo            : {res_simple['type']}")
    print(f"  files (vacíos)  : {res_simple['files']}")
    print(f"  scripts cargados: {res_simple['skills_loaded']}")
    print(f"\n  instructions (primeras líneas):")
    instr = res_simple['instructions']
    print("\n".join("    " + ln for ln in instr.splitlines()[:6]))

    assert res_simple["skills_loaded"] == []
    assert "Política de devoluciones" in instr

    # ────────────────────────────────────────────────────────────────
    # SKILL COMPLEJA — formato oficial de Anthropic
    # ────────────────────────────────────────────────────────────────
    # Activarla nos da:
    # - los files de la carpeta (LICENSE.txt + reference.md)
    # - el body completo de su SKILL.md como contexto
    # No bajamos scripts/ entonces no se cargan tools. La librería
    # detectaría y registraría los scripts automáticamente si los
    # hubiéramos incluido.
    section("ACTIVAR `pdf` (skill oficial de Anthropic)")
    res_compleja = caja_skills_documentos.activate("pdf")
    print(f"  nombre activado : {res_compleja['name']}")
    print(f"  files de la carpeta:")
    for f in res_compleja['files']:
        print(f"    - {f}")
    print(f"  scripts cargados: {res_compleja['skills_loaded']}")
    print(f"\n  instructions (primeras líneas):")
    instr_pdf = res_compleja['instructions']
    print("\n".join("    " + ln for ln in instr_pdf.splitlines()[:6]))

    # Verificamos que la librería entiende el formato oficial:
    assert res_compleja["type"] == "skill_folder"
    assert "PDF" in instr_pdf
    assert "reference.md" in res_compleja["files"]
    assert "LICENSE.txt" in res_compleja["files"]

    # ────────────────────────────────────────────────────────────────
    # Nivel 3 del progressive disclosure — leer un file específico
    # ────────────────────────────────────────────────────────────────
    # `AgentSkill.get_file(...)` accede a un archivo de la carpeta on
    # demand. Esto permite que el agente lea references o assets sin
    # que se inyecten todos en el system prompt. (En el ejemplo 21 lo
    # vemos vía la nav tool `get_reference`.)
    section("NIVEL 3 — lectura on-demand de `reference.md` del skill pdf")
    pdf_skill = caja_skills_documentos.skill_folders["pdf"]
    ref_md = pdf_skill.get_file("reference.md")
    print(f"  reference.md leído: {len(ref_md) if ref_md else 0} chars")
    print(f"  primeras 3 líneas:")
    if ref_md:
        for ln in ref_md.splitlines()[:3]:
            print(f"    {ln}")
    assert ref_md and len(ref_md) > 100

    # ────────────────────────────────────────────────────────────────
    # Lo que ve un agente: el active context combina ambas skills
    # ────────────────────────────────────────────────────────────────
    # `get_active_context()` concatena los `context` de los items
    # actualmente activos. Es lo que el dev pasaría como
    # `shelf_context` al `agente.run(...)` para que vea las skills
    # activadas.
    section("ACTIVE CONTEXT DEL CAPABILITY (lo que recibiría el agente)")
    active = caja_skills_documentos.get_active_context()
    print(f"  longitud total: {len(active)} chars")
    print(f"  preview:")
    print("\n".join("    " + ln for ln in active.splitlines()[:10]))
    assert "politicas_devolucion" in active
    assert "pdf" in active

    # ────────────────────────────────────────────────────────────────
    # Demo final: agente que recibe el manager y RESPONDE usando las
    # skills activadas (sin invocar tools, solo conocimiento)
    # ────────────────────────────────────────────────────────────────
    # Construimos un agente al que le pasamos `caja_skills_documentos`
    # y, vía `shelf_context` en el run, le inyectamos el contenido de
    # las skills activadas. El agente usa ese conocimiento para
    # responder una consulta de devolución del cliente.
    agente = InstantNeo(
        provider=PROVIDER, model=MODEL, api_key=API_KEY,
        role_setup="Eres asistente de atención del comercio. Aplicá las políticas vigentes.",
        max_tokens=400,
    )

    section("CONSULTA AL AGENTE — usa las políticas activas")
    respuesta = agente.run(
        "Un cliente pide devolver un mate con grabado personalizado "
        "que compró hace 5 días. ¿Cuál es la decisión y por qué?",
        shelf_context=active,
    )
    texto = respuesta.get("text") if isinstance(respuesta, dict) else str(respuesta)
    print(texto)

    # Verificamos que el agente aplicó la regla "productos personalizados → no admiten devolución"
    assert texto and any(p in texto.lower() for p in ["personalizad", "no admite", "no se admite", "rechazado"])

    print("\n✅ Ejemplo 19 completado correctamente.")


if __name__ == "__main__":
    main()
