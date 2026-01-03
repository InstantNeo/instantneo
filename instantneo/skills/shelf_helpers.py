# shelf_helpers.py
"""
Helpers para navegación autónoma del shelf.

Provee:
- create_navigation_skills(): Factory para crear skills de navegación
- SHELF_NAVIGATION_PROMPT: Prompt sugerido para agentes autónomos

Uso:
    from instantneo.skills.shelf_helpers import create_navigation_skills, SHELF_NAVIGATION_PROMPT

    shelf = create_my_shelf()
    nav_skills = create_navigation_skills(shelf)

    agent = InstantNeo(
        role_setup=f"Eres un asistente.\\n\\n{SHELF_NAVIGATION_PROMPT}",
        skills=shelf
    )

    for s in nav_skills:
        agent.register_skill(s)
"""

from typing import List, Callable, TYPE_CHECKING
import json

from .skill_decorators import skill

if TYPE_CHECKING:
    from .skill_manager import SkillManager


# ═══════════════════════════════════════════════════════
# PROMPT SUGERIDO PARA NAVEGACIÓN AUTÓNOMA
# ═══════════════════════════════════════════════════════

SHELF_NAVIGATION_PROMPT = """
## Knowledge Shelf

You have access to a knowledge shelf with specialized capabilities and instructions.
When you need knowledge you don't currently have:

1. Use `discover()` to see what's available
2. Use `search(query)` to find specific topics
3. Use `activate(name)` to load the knowledge
4. The activated knowledge will be available in your next response
5. Use `get_reference(item, file)` for detailed documentation

Guidelines:
- Only activate what you need for the current task
- Deactivate knowledge when you're done with it
- Use search before discover if you know what you're looking for
"""


# ═══════════════════════════════════════════════════════
# FACTORY PARA SKILLS DE NAVEGACIÓN
# ═══════════════════════════════════════════════════════

def create_navigation_skills(shelf: "SkillManager") -> List[Callable]:
    """
    Factory que crea skills para navegación autónoma del shelf.

    El desarrollador decide si quiere estas capacidades y cómo registrarlas.

    Args:
        shelf: SkillManager que actúa como shelf

    Returns:
        Lista de funciones @skill para navegación:
        - discover: Ver contenido disponible
        - activate: Activar conocimiento
        - deactivate: Desactivar conocimiento
        - search: Buscar en el shelf
        - get_reference: Obtener archivos de referencia

    Example:
        >>> shelf = create_my_shelf()
        >>> nav_skills = create_navigation_skills(shelf)
        >>> for s in nav_skills:
        ...     agent.register_skill(s)
    """

    @skill(tags=["shelf", "navigation"])
    def discover(path: str = None) -> str:
        """
        Descubre qué conocimiento hay disponible en el shelf.

        Args:
            path: Opcional. Path para explorar sub-categorías
                  (ej: "math-tools/basic-ops"). Si es None,
                  muestra el nivel superior.

        Returns:
            Lista formateada del contenido disponible con tipos y descripciones.
        """
        items = shelf.discover(path)

        if not items:
            location = f"'{path}'" if path else "el shelf"
            return f"No se encontró contenido en {location}."

        lines = []
        for item in items:
            item_type = item.get("type", "unknown")
            name = item.get("name", "?")
            desc = item.get("description", "")[:60]

            # Formatear según tipo
            if item_type == "manager":
                children = item.get("children", [])
                children_str = f" [{', '.join(children[:3])}...]" if children else ""
                lines.append(f"[{item_type}] {name}: {desc}{children_str}")
            else:
                lines.append(f"[{item_type}] {name}: {desc}")

        header = f"Contenido de '{path}':" if path else "Contenido del shelf:"
        return f"{header}\n" + "\n".join(f"  - {line}" for line in lines)

    @skill(tags=["shelf", "navigation"])
    def activate(name: str) -> str:
        """
        Activa conocimiento del shelf para tener acceso a sus instrucciones y herramientas.

        Args:
            name: Nombre del item a activar. Puede ser un path
                  (ej: "tools/pdf-processing") o un nombre simple
                  si es único.

        Returns:
            Confirmación de activación con detalles del item.

        Note:
            Las instrucciones del item activado estarán disponibles
            en tu PRÓXIMO mensaje, no en el actual.
        """
        try:
            result = shelf.activate(name, persistent=True)

            response = [f"Activado: {result['name']} ({result['type']})"]

            if result.get("description"):
                response.append(f"Descripcion: {result['description'][:100]}")

            if result.get("skills_loaded"):
                response.append(f"Herramientas disponibles: {', '.join(result['skills_loaded'])}")

            if result.get("files"):
                files_preview = result["files"][:5]
                response.append(f"Archivos de referencia: {', '.join(files_preview)}")

            response.append("\nEl conocimiento estara disponible en tu proximo mensaje.")

            return "\n".join(response)

        except ValueError as e:
            return f"Error: {e}"
        except Exception as e:
            return f"Error inesperado: {e}"

    @skill(tags=["shelf", "navigation"])
    def deactivate(name: str) -> str:
        """
        Desactiva conocimiento que ya no necesitas.

        Args:
            name: Nombre del item a desactivar.

        Returns:
            Confirmación de desactivación.
        """
        success = shelf.deactivate(name)

        if success:
            return f"Desactivado: '{name}'. Ya no estara en tu contexto."
        else:
            return f"'{name}' no estaba activo."

    @skill(tags=["shelf", "navigation"])
    def search(query: str) -> str:
        """
        Busca conocimiento específico en todo el shelf.

        Args:
            query: Texto a buscar en nombres de items.

        Returns:
            Lista de coincidencias con sus ubicaciones (paths).
        """
        results = shelf.find(query)

        if not results:
            return f"No se encontro nada para '{query}'."

        lines = []
        for r in results:
            lines.append(f"[{r['type']}] {r['name']} @ {r['path']}")

        return f"Resultados para '{query}':\n" + "\n".join(f"  - {line}" for line in lines)

    @skill(tags=["shelf", "navigation"])
    def get_reference(item_name: str, file_path: str) -> str:
        """
        Obtiene un archivo de referencia de un item activado.

        Args:
            item_name: Nombre del item (debe estar activado).
            file_path: Path relativo al archivo dentro del item
                      (ej: "references/API.md", "scripts/utils.py").

        Returns:
            Contenido del archivo o mensaje de error.

        Note:
            El item debe estar activado primero con activate().
        """
        # Verificar si está activo
        if item_name not in shelf._active_items:
            return f"'{item_name}' no esta activo. Usa activate('{item_name}') primero."

        item = shelf._active_items[item_name]

        # Verificar si tiene get_file (es un skill folder)
        if not hasattr(item, 'get_file'):
            return f"'{item_name}' no tiene archivos de referencia (no es un skill folder)."

        content = item.get_file(file_path)

        if content:
            return f"=== {item_name}/{file_path} ===\n\n{content}"
        else:
            # Listar archivos disponibles
            available = item.list_files()
            return f"Archivo no encontrado: '{file_path}'.\nArchivos disponibles: {', '.join(available[:10])}"

    @skill(tags=["shelf", "navigation"])
    def list_active() -> str:
        """
        Lista todos los items actualmente activos.

        Returns:
            Lista de items activos con sus tipos.
        """
        if not shelf._active_items:
            return "No hay items activos."

        lines = []
        for name, item in shelf._active_items.items():
            # Determinar tipo
            if hasattr(item, 'skill_metadata'):
                item_type = "skill"
            elif hasattr(item, 'get_instructions'):
                item_type = "skill_folder"
            else:
                item_type = "manager"

            lines.append(f"[{item_type}] {name}")

        return "Items activos:\n" + "\n".join(f"  - {line}" for line in lines)

    return [discover, activate, deactivate, search, get_reference, list_active]
