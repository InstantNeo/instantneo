# navigation_helpers.py
"""
Helpers para navegación autónoma de capabilities.

Provee:
- create_navigation_tools(): Factory para crear tools de navegación
- NAVIGATION_PROMPT: Prompt sugerido para agentes autónomos

Uso:
    from instantneo.skills.navigation_helpers import create_navigation_tools, NAVIGATION_PROMPT

    capabilities = create_my_capabilities()
    nav_tools = create_navigation_tools(capabilities)

    agent = InstantNeo(
        role_setup=f"Eres un asistente.\\n\\n{NAVIGATION_PROMPT}",
        skills=capabilities
    )

    for t in nav_tools:
        agent.register_tool(t)
"""

from typing import List, Callable, TYPE_CHECKING
import json

from .tool_decorators import tool

if TYPE_CHECKING:
    from .agent_capabilities import AgentCapabilities


# ═══════════════════════════════════════════════════════
# PROMPT SUGERIDO PARA NAVEGACIÓN AUTÓNOMA
# ═══════════════════════════════════════════════════════

NAVIGATION_PROMPT = """
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

# Backward compat alias
SHELF_NAVIGATION_PROMPT = NAVIGATION_PROMPT


# ═══════════════════════════════════════════════════════
# FACTORY PARA TOOLS DE NAVEGACIÓN
# ═══════════════════════════════════════════════════════

def create_navigation_tools(capabilities: "AgentCapabilities") -> List[Callable]:
    """
    Factory que crea tools para navegación autónoma.

    Args:
        capabilities: AgentCapabilities que actúa como shelf

    Returns:
        Lista de funciones @tool para navegación
    """

    @tool(tags=["shelf", "navigation"])
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
        items = capabilities.discover(path)

        if not items:
            location = f"'{path}'" if path else "el shelf"
            return f"No se encontró contenido en {location}."

        lines = []
        for item in items:
            item_type = item.get("type", "unknown")
            name = item.get("name", "?")
            desc = item.get("description", "")[:60]

            if item_type == "manager":
                children = item.get("children", [])
                children_str = f" [{', '.join(children[:3])}...]" if children else ""
                lines.append(f"[{item_type}] {name}: {desc}{children_str}")
            else:
                lines.append(f"[{item_type}] {name}: {desc}")

        header = f"Contenido de '{path}':" if path else "Contenido del shelf:"
        return f"{header}\n" + "\n".join(f"  - {line}" for line in lines)

    @tool(tags=["shelf", "navigation"])
    def activate(name: str) -> str:
        """
        Activa conocimiento del shelf para tener acceso a sus instrucciones y herramientas.

        Args:
            name: Nombre del item a activar. Puede ser un path
                  (ej: "tools/pdf-processing") o un nombre simple
                  si es único.

        Returns:
            Confirmación de activación con detalles del item.
        """
        try:
            result = capabilities.activate(name)

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

    @tool(tags=["shelf", "navigation"])
    def deactivate(name: str) -> str:
        """
        Desactiva conocimiento que ya no necesitas.

        Args:
            name: Nombre del item a desactivar.

        Returns:
            Confirmación de desactivación.
        """
        success = capabilities.deactivate(name)

        if success:
            return f"Desactivado: '{name}'. Ya no estara en tu contexto."
        else:
            return f"'{name}' no estaba activo."

    @tool(tags=["shelf", "navigation"])
    def search(query: str) -> str:
        """
        Busca conocimiento específico en todo el shelf.

        Args:
            query: Texto a buscar en nombres de items.

        Returns:
            Lista de coincidencias con sus ubicaciones (paths).
        """
        results = capabilities.find(query)

        if not results:
            return f"No se encontro nada para '{query}'."

        lines = []
        for r in results:
            lines.append(f"[{r['type']}] {r['name']} @ {r['path']}")

        return f"Resultados para '{query}':\n" + "\n".join(f"  - {line}" for line in lines)

    @tool(tags=["shelf", "navigation"])
    def get_reference(item_name: str, file_path: str) -> str:
        """
        Obtiene un archivo de referencia de un item activado.

        Args:
            item_name: Nombre del item (debe estar activado).
            file_path: Path relativo al archivo dentro del item.

        Returns:
            Contenido del archivo o mensaje de error.
        """
        if item_name not in capabilities._active_items:
            return f"'{item_name}' no esta activo. Usa activate('{item_name}') primero."

        record = capabilities._active_items[item_name]
        item = record.item

        if not hasattr(item, 'get_file'):
            return f"'{item_name}' no tiene archivos de referencia (no es un skill folder)."

        content = item.get_file(file_path)

        if content:
            return f"=== {item_name}/{file_path} ===\n\n{content}"
        else:
            available = item.list_files()
            return f"Archivo no encontrado: '{file_path}'.\nArchivos disponibles: {', '.join(available[:10])}"

    @tool(tags=["shelf", "navigation"])
    def list_active() -> str:
        """
        Lista todos los items actualmente activos.

        Returns:
            Lista de items activos con sus tipos.
        """
        if not capabilities._active_items:
            return "No hay items activos."

        lines = []
        for name, record in capabilities._active_items.items():
            lines.append(f"[{record.item_type}] {name}")

        return "Items activos:\n" + "\n".join(f"  - {line}" for line in lines)

    return [discover, activate, deactivate, search, get_reference, list_active]


# Backward compat alias
create_navigation_skills = create_navigation_tools
