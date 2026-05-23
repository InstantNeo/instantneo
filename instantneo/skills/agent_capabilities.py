import sys
import os
import logging
import pkgutil
import importlib
import importlib.util
import inspect
from dataclasses import dataclass, field
from typing import Dict, List, Any, Union, Optional, Callable
from pathlib import Path

from .agent_skill import AgentSkill
from .skill_md_parser import SkillMdParser

logger = logging.getLogger(__name__)


@dataclass
class ActivationRecord:
    """Tracks everything that an activate() call brought in, for atomic cleanup."""
    item: Any                              # Item original (AgentSkill, AgentCapabilities, callable)
    item_type: str                         # "skill_folder", "manager", "skill" (tool directo)
    context: str                           # Texto/instrucciones que inyecta
    tools: Dict[str, Callable] = field(default_factory=dict)     # Tools callables que trajo
    tool_registry_keys: List[str] = field(default_factory=list)  # Keys registradas en registry (para cleanup)


class CapabilityLoader:
    """Loads tools into an AgentCapabilities instance from various sources."""
    def __init__(self, manager: "AgentCapabilities"):
        self.manager = manager

    def _build_metadata_filter(self, by_tags: Optional[List[str]] = None, by_name: Optional[str] = None) -> Callable[[Dict[str, Any]], bool]:
        def metadata_filter(metadata: Dict[str, Any]) -> bool:
            if by_tags and not all(tag in metadata.get('tags', []) for tag in by_tags):
                return False
            if by_name and metadata.get('name') != by_name:
                return False
            return True
        return metadata_filter

    def from_file(self, file_path: str, by_tags: Optional[List[str]] = None, by_name: Optional[str] = None) -> List[str]:
        metadata_filter = self._build_metadata_filter(by_tags, by_name)
        return self.manager._load_tools_from_file(file_path, metadata_filter)

    def from_folder(self, folder_path: str, by_tags: Optional[List[str]] = None, by_name: Optional[str] = None) -> List[str]:
        metadata_filter = self._build_metadata_filter(by_tags, by_name)
        return self.manager._load_tools_from_folder(folder_path, metadata_filter)

    def from_current(self, by_tags: Optional[List[str]] = None, by_name: Optional[str] = None) -> None:
        metadata_filter = self._build_metadata_filter(by_tags, by_name)
        self.manager._load_tools_from_current_module(metadata_filter)

    def from_module(self, module: Any, by_tags: Optional[List[str]] = None, by_name: Optional[str] = None) -> None:
        metadata_filter = self._build_metadata_filter(by_tags, by_name)
        self.manager._load_tools_from_module(module, metadata_filter)

    # ═══════════════════════════════════════════════════════
    # SKILL FOLDERS (SKILL.md)
    # ═══════════════════════════════════════════════════════

    def from_skill_folder(self, folder_path: str) -> str:
        """
        Carga una carpeta tipo SKILL.md.

        Args:
            folder_path: Path a la carpeta que contiene SKILL.md

        Returns:
            Nombre del skill cargado
        """
        agent_skill = SkillMdParser.parse_folder(folder_path)
        self.manager.skill_folders[agent_skill.name] = agent_skill
        return agent_skill.name

    def from_skill_folders(self, root_path: str) -> List[str]:
        """
        Carga múltiples carpetas SKILL.md de un directorio.

        Args:
            root_path: Directorio que contiene carpetas con SKILL.md

        Returns:
            Lista de nombres de skills cargados
        """
        loaded = []
        root = Path(root_path)

        for folder in root.iterdir():
            if folder.is_dir() and (folder / "SKILL.md").exists():
                try:
                    name = self.from_skill_folder(str(folder))
                    loaded.append(name)
                except Exception as e:
                    logger.exception("Error cargando %s", folder)

        return loaded

    # ═══════════════════════════════════════════════════════
    # MANAGERS
    # ═══════════════════════════════════════════════════════

    def from_manager(self, manager: "AgentCapabilities") -> str:
        """
        Agrega un AgentCapabilities como sub-manager.

        Args:
            manager: AgentCapabilities a agregar

        Returns:
            Nombre del manager agregado
        """
        if not manager.name:
            raise ValueError("El AgentCapabilities debe tener un nombre para ser agregado como sub-manager")
        self.manager.managers[manager.name] = manager
        return manager.name

    def from_managers(self, managers: List["AgentCapabilities"]) -> List[str]:
        """
        Agrega múltiples AgentCapabilities como sub-managers.

        Args:
            managers: Lista de AgentCapabilities a agregar

        Returns:
            Lista de nombres de managers agregados
        """
        return [self.from_manager(m) for m in managers]


# Backward compat alias
SkillLoader = CapabilityLoader


class AgentCapabilities:
    """
    Registry for tools (callable functions) and knowledge items (skill folders, sub-managers).

    Provides:
    - Tool registration and retrieval
    - Skill folder and sub-manager loading
    - Progressive disclosure via discover/activate/deactivate
    - Activation records for atomic cleanup
    """
    def __init__(
        self,
        name: Optional[str] = None,
        description: Optional[str] = None,
        skills: Optional[List[Callable]] = None,
        skills_from_files: Optional[List[str]] = None,
        skills_from_folders: Optional[List[str]] = None,
        global_instructions: str = ""
    ):
        # Almacenamos el módulo del contexto en el que se instanció el manager
        caller_frame = inspect.currentframe().f_back
        self.instantiation_module = inspect.getmodule(caller_frame)

        self.name = name
        self.description = description

        # Registro de funciones @tool (existente)
        self.registry: Dict[str, Any] = {}
        self.registry_by_name: Dict[str, List[Any]] = {}
        self.duplicates: Dict[str, List[Any]] = {}

        # Skill folders y sub-managers
        self.skill_folders: Dict[str, AgentSkill] = {}
        self.managers: Dict[str, "AgentCapabilities"] = {}

        # Estado de activación
        self._active_items: Dict[str, ActivationRecord] = {}

        # Clase auxiliar para carga de tools
        self.load_skills = CapabilityLoader(self)

        # Atributo de Instrucciones Globales
        self.global_instructions: str = global_instructions

        # Carga Inicial Declarativa
        if skills:
            for func in skills:
                self.register_tool(func)

        if skills_from_files:
            for file_path in skills_from_files:
                self.load_skills.from_file(file_path)

        if skills_from_folders:
            for folder_path in skills_from_folders:
                self.load_skills.from_folder(folder_path)

    # ═══════════════════════════════════════════════════════
    # GLOBAL INSTRUCTIONS
    # ═══════════════════════════════════════════════════════

    def set_global_instructions(self, text: str) -> None:
        """Establece las instrucciones globales."""
        if not isinstance(text, str):
            raise TypeError("Las instrucciones deben ser texto (str).")
        self.global_instructions = text

    def get_global_instructions(self) -> str:
        """Devuelve las instrucciones globales."""
        return self.global_instructions

    # ═══════════════════════════════════════════════════════
    # TOOL REGISTRATION & RETRIEVAL
    # ═══════════════════════════════════════════════════════

    def register_tool(self, func) -> None:
        key = f"{func.__module__}.{func.__name__}"
        simple_name = func.__name__
        file_path = func.__code__.co_filename

        if simple_name in self.registry_by_name:
            if simple_name not in self.duplicates:
                self.duplicates[simple_name] = []
            self.duplicates[simple_name].append(func)
            logger.warning(
                "La tool '%s' ya fue registrada en %s. La definición en %s "
                "se ha agregado al registro de duplicados.",
                simple_name,
                self.registry_by_name[simple_name][0].__code__.co_filename,
                file_path,
            )
        else:
            self.registry_by_name[simple_name] = [func]

        self.registry[key] = func

    # Backward compat alias
    def register_skill(self, func) -> None:
        return self.register_tool(func)

    def _load_tools_from_module(self, module,
                                metadata_filter: Optional[Callable[[Dict[str, Any]], bool]] = None) -> None:
        for attr_name in dir(module):
            attr = getattr(module, attr_name)
            if callable(attr) and (hasattr(attr, 'tool_metadata') or hasattr(attr, 'skill_metadata')):
                metadata = getattr(attr, 'tool_metadata', None) or getattr(attr, 'skill_metadata', None)
                if metadata_filter is not None:
                    if not metadata_filter(metadata):
                        continue
                self.register_tool(attr)

    # Backward compat alias
    _load_skills_from_module = _load_tools_from_module

    def _load_tools_from_current_module(
        self,
        metadata_filter: Optional[Callable[[Dict[str, Any]], bool]] = None
    ) -> None:
        caller_module = self.instantiation_module
        if caller_module:
            self._load_tools_from_module(caller_module, metadata_filter)
        else:
            raise RuntimeError("No se pudo determinar el módulo que instanció AgentCapabilities.")

    # Backward compat alias
    _load_skills_from_current_module = _load_tools_from_current_module

    def _load_tools_from_file(self, file_path: str,
                              metadata_filter: Optional[Callable[[Dict[str, Any]], bool]] = None) -> List[str]:
        if not os.path.isfile(file_path):
            raise ValueError(f"{file_path} no es un archivo válido.")

        module_name = os.path.splitext(os.path.basename(file_path))[0]
        spec = importlib.util.spec_from_file_location(module_name, file_path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        registered = []
        self._load_tools_from_module(module, metadata_filter)
        for attr_name in dir(module):
            attr = getattr(module, attr_name)
            if callable(attr) and (hasattr(attr, 'tool_metadata') or hasattr(attr, 'skill_metadata')):
                registered.append(f"{attr.__module__}.{attr.__name__}")
        return registered

    # Backward compat alias
    _load_skills_from_file = _load_tools_from_file

    def _load_tools_from_folder(self, folder_path: str, metadata_filter=None):
        """
        Carga tools desde archivos Python en un directorio sin requerir que sean módulos importables.
        """
        if not os.path.isdir(folder_path):
            raise ValueError(f"{folder_path} no es una carpeta válida.")

        for filename in os.listdir(folder_path):
            if filename.endswith('.py'):
                file_path = os.path.join(folder_path, filename)
                module_name = os.path.splitext(filename)[0]

                try:
                    spec = importlib.util.spec_from_file_location(module_name, file_path)
                    module = importlib.util.module_from_spec(spec)
                    sys.modules[module_name] = module
                    spec.loader.exec_module(module)
                    self._load_tools_from_module(module, metadata_filter)
                    del sys.modules[module_name]
                except Exception as e:
                    logger.exception("Error al cargar el archivo %s", file_path)

        return f"Tools Loaded:{self.get_tool_names()} from {folder_path}"

    # Backward compat alias
    _load_skills_from_folder = _load_tools_from_folder

    # ═══════════════════════════════════════════════════════
    # QUERY METHODS
    # ═══════════════════════════════════════════════════════

    def get_tool_names(self) -> List[str]:
        return list({func.__name__ for func in self.registry.values()})

    # Backward compat alias
    get_skill_names = get_tool_names

    def get_tools_with_keys(self) -> Dict[str, Any]:
        return self.registry

    # Backward compat alias
    get_skills_with_keys = get_tools_with_keys

    def get_all_tools_metadata(self) -> Dict[str, Dict[str, Any]]:
        return {
            key: {"key": key, **(func.tool_metadata if hasattr(func, 'tool_metadata') else func.skill_metadata)}
            for key, func in sorted(self.registry.items())
        }

    # Backward compat alias
    get_all_skills_metadata = get_all_tools_metadata

    def get_schemas(self) -> List[Dict[str, Any]]:
        """OpenAI-format tool schemas para todas las tools registradas.

        Devuelve una lista de schemas ``{"type": "function", "function":
        {"name", "description", "parameters": ...}}`` lista para
        serializar. Útil para:

        - Capturar la cabecera del agente en logs / `run_start` entries
          de un orquestador (Loop, Pipeline futuro).
        - Replay: saber qué tools tenía disponibles un agente en un
          momento dado.
        - Introspección externa sin invocar al LLM.

        Reusa ``instantneo.utils.tool_utils.format_tool`` internamente.
        Tools sin ``parameters`` en su metadata se skippean (mismo
        comportamiento que el call site inline en
        ``core.py:_run`` cuando arma `formatted_tools`).
        """
        from instantneo.utils.tool_utils import format_tool
        schemas: List[Dict[str, Any]] = []
        for _key, metadata in self.get_all_tools_metadata().items():
            if not metadata or 'parameters' not in metadata:
                continue
            schemas.append(format_tool(metadata))
        return schemas

    def get_tool_metadata_by_name(self, name: str) -> Dict[str, Any]:
        matches = {key: func for key, func in self.registry.items() if func.__name__ == name}
        if not matches:
            return None
        func = matches[next(iter(matches.keys()))]
        return func.tool_metadata if hasattr(func, 'tool_metadata') else func.skill_metadata

    # Backward compat alias
    get_skill_metadata_by_name = get_tool_metadata_by_name

    def get_tools_by_tag(self, tag: str,
                         return_keys: bool = False) -> Union[List[str], Dict[str, Any]]:
        filtered = {}
        for key, func in self.registry.items():
            metadata = func.tool_metadata if hasattr(func, 'tool_metadata') else func.skill_metadata
            if tag in metadata.get('tags', []):
                filtered[key] = func
        if return_keys:
            return filtered
        else:
            return list({func.__name__ for func in filtered.values()})

    # Backward compat alias
    get_skills_by_tag = get_tools_by_tag

    def get_tool_by_name(self, name: str) -> Union[Any, Dict[str, Any], None]:
        matches = {key: func for key, func in self.registry.items() if func.__name__ == name}
        if not matches:
            return None
        if len(matches) == 1:
            return next(iter(matches.values()))
        return matches

    # Backward compat alias
    get_skill_by_name = get_tool_by_name

    def get_duplicate_tools(self) -> Dict[str, List[Any]]:
        return self.duplicates

    # Backward compat alias
    get_duplicate_skills = get_duplicate_tools

    def remove_tool(self, name: str, module: Optional[str] = None) -> bool:
        if name not in self.registry_by_name:
            return False

        if module:
            key_to_remove = f"{module}.{name}"
            if key_to_remove in self.registry:
                self.registry.pop(key_to_remove)
                self.registry_by_name[name] = [
                    func for func in self.registry_by_name[name] if func.__module__ != module
                ]
                if not self.registry_by_name[name]:
                    self.registry_by_name.pop(name)
                return True
            else:
                return False
        else:
            if len(self.registry_by_name[name]) == 1:
                func_to_remove = self.registry_by_name[name][0]
                key_to_remove = f"{func_to_remove.__module__}.{name}"
                self.registry.pop(key_to_remove, None)
                self.registry_by_name.pop(name, None)
                return True
            else:
                logger.warning("Existen múltiples tools con el nombre '%s'. Especifica el módulo para eliminar.", name)
                return False

    # Backward compat alias
    remove_skill = remove_tool

    def clear_registry(self) -> None:
        self.registry.clear()
        self.registry_by_name.clear()
        self.duplicates.clear()

    def update_tool_metadata(self, key: str, new_metadata: Dict[str, Any]) -> bool:
        if key in self.registry:
            func = self.registry[key]
            metadata = func.tool_metadata if hasattr(func, 'tool_metadata') else func.skill_metadata
            metadata.update(new_metadata)
            return True
        return False

    # Backward compat alias
    update_skill_metadata = update_tool_metadata

    # ═══════════════════════════════════════════════════════
    # NAVIGATION (shelf)
    # ═══════════════════════════════════════════════════════

    def discover(self, path: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Lista contenido activable (nivel 1 del progressive disclosure).
        Only shows skill_folders and managers, not direct tools.
        """
        if path:
            target = self._resolve_path(path)
            if target and isinstance(target, AgentCapabilities):
                return target.discover()
            return []

        discoveries = []

        # Skill folders (SKILL.md)
        for name, agent_skill in self.skill_folders.items():
            discoveries.append(agent_skill.discovery_info)

        # Sub-managers
        for name, manager in self.managers.items():
            children = (
                list(manager.registry_by_name.keys()) +
                list(manager.skill_folders.keys()) +
                list(manager.managers.keys())
            )
            discoveries.append({
                "name": name,
                "description": manager.description or "",
                "type": "manager",
                "children": children[:5]
            })

        return discoveries

    def activate(self, name: str, **kwargs) -> Dict[str, Any]:
        """
        Activa un skill/folder/manager por nombre o path.
        """
        item, item_type = self._find_item(name)

        if item is None:
            raise ValueError(f"No se encontró: {name}")

        result = {"name": name, "type": item_type}
        context = ""
        tools = {}

        keys_before = set(self.registry.keys())

        if item_type == "skill":
            if name not in self.registry_by_name:
                self.register_tool(item)
            metadata = item.tool_metadata if hasattr(item, 'tool_metadata') else item.skill_metadata
            result["description"] = metadata.get("description", "")
            result["skills_loaded"] = [name]
            context = metadata.get("description", "")
            tools[item.__name__] = item

        elif item_type == "skill_folder":
            result["instructions"] = item.get_instructions()
            result["description"] = item.description
            result["files"] = item.list_files()
            result["skills_loaded"] = []
            context = item.get_instructions()

            for file_path in item.list_files("scripts"):
                if file_path.endswith(".py"):
                    full_path = item.skill_path / file_path
                    try:
                        loaded = self._load_tools_from_file(str(full_path))
                        result["skills_loaded"].extend(loaded)
                    except Exception as e:
                        logger.exception("Error cargando tools de %s", file_path)

        elif item_type == "manager":
            result["description"] = item.description or ""
            result["contents"] = item.discover()
            result["skills_loaded"] = []
            context = item.global_instructions or ""

        keys_after = set(self.registry.keys())
        new_keys = list(keys_after - keys_before)

        for key in new_keys:
            func = self.registry[key]
            tools[func.__name__] = func

        record = ActivationRecord(
            item=item,
            item_type=item_type,
            context=context,
            tools=tools,
            tool_registry_keys=new_keys,
        )
        self._active_items[name] = record

        return result

    def deactivate(self, name: str) -> bool:
        """
        Desactiva un item previamente activado.
        Cleans up all tools that were registered during activation.
        """
        if name not in self._active_items:
            return False

        record = self._active_items[name]

        for key in record.tool_registry_keys:
            if key in self.registry:
                func = self.registry.pop(key)
                func_name = func.__name__
                if func_name in self.registry_by_name:
                    self.registry_by_name[func_name] = [
                        f for f in self.registry_by_name[func_name]
                        if f"{f.__module__}.{f.__name__}" != key
                    ]
                    if not self.registry_by_name[func_name]:
                        del self.registry_by_name[func_name]

        del self._active_items[name]
        return True

    def get_active_context(self) -> str:
        """Retorna las instrucciones concatenadas de todos los items activos."""
        contexts = []
        for name, record in self._active_items.items():
            if record.context:
                contexts.append(f"## {name}\n\n{record.context}")
        return "\n\n---\n\n".join(contexts)

    def get_active_tools(self) -> Dict[str, Callable]:
        """Returns all tools from currently active items."""
        tools = {}
        for name, record in self._active_items.items():
            tools.update(record.tools)
        return tools

    def clear_active(self) -> None:
        """Limpia todos los items activos, cleaning up their tools from the registry."""
        for name in list(self._active_items.keys()):
            self.deactivate(name)

    def find(self, query: str) -> List[Dict[str, Any]]:
        """Busca items en todo el árbol que coincidan con el query."""
        results = []
        self._search_recursive(query, "", results)
        return results

    def _search_recursive(self, query: str, current_path: str, results: List[Dict[str, Any]]) -> None:
        for name in self.registry_by_name.keys():
            if query.lower() in name.lower():
                path = f"{current_path}/{name}" if current_path else name
                results.append({"name": name, "type": "skill", "path": path})

        for name in self.skill_folders.keys():
            if query.lower() in name.lower():
                path = f"{current_path}/{name}" if current_path else name
                results.append({"name": name, "type": "skill_folder", "path": path})

        for name, manager in self.managers.items():
            if query.lower() in name.lower():
                path = f"{current_path}/{name}" if current_path else name
                results.append({"name": name, "type": "manager", "path": path})
            sub_path = f"{current_path}/{name}" if current_path else name
            manager._search_recursive(query, sub_path, results)

    def _resolve_path(self, path: str) -> Optional[Any]:
        parts = path.split("/")
        current = self

        for part in parts:
            if isinstance(current, AgentCapabilities):
                if part in current.managers:
                    current = current.managers[part]
                elif part in current.skill_folders:
                    return current.skill_folders[part]
                elif part in current.registry_by_name:
                    return current.registry_by_name[part][0]
                else:
                    return None
            else:
                return None

        return current

    def _find_item(self, name: str) -> tuple:
        if "/" in name:
            item = self._resolve_path(name)
            if item:
                if isinstance(item, AgentCapabilities):
                    return item, "manager"
                elif isinstance(item, AgentSkill):
                    return item, "skill_folder"
                elif callable(item):
                    return item, "skill"
            return None, None

        if name in self.registry_by_name:
            return self.registry_by_name[name][0], "skill"

        if name in self.skill_folders:
            return self.skill_folders[name], "skill_folder"

        if name in self.managers:
            return self.managers[name], "manager"

        found = []
        for manager_name, manager in self.managers.items():
            item, item_type = manager._find_item(name)
            if item:
                found.append((item, item_type, f"{manager_name}/{name}"))

        if len(found) == 1:
            return found[0][0], found[0][1]
        elif len(found) > 1:
            paths = [f[2] for f in found]
            raise ValueError(
                f"'{name}' existe en múltiples ubicaciones: {paths}. "
                "Usá el path completo."
            )

        return None, None


# Backward compatibility alias
SkillManager = AgentCapabilities
