import sys
import os
import pkgutil
import importlib
import importlib.util
import inspect
from typing import Dict, List, Any, Union, Optional, Callable
from pathlib import Path

from .agent_skill import AgentSkill
from .skill_md_parser import SkillMdParser

class SkillLoader:
    def __init__(self, manager: "SkillManager"):
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
        return self.manager._load_skills_from_file(file_path, metadata_filter)

    def from_folder(self, folder_path: str, by_tags: Optional[List[str]] = None, by_name: Optional[str] = None) -> List[str]:
        metadata_filter = self._build_metadata_filter(by_tags, by_name)
        return self.manager._load_skills_from_folder(folder_path, metadata_filter)

    def from_current(self, by_tags: Optional[List[str]] = None, by_name: Optional[str] = None) -> None:
        metadata_filter = self._build_metadata_filter(by_tags, by_name)
        self.manager._load_skills_from_current_module(metadata_filter)

    def from_module(self, module: Any, by_tags: Optional[List[str]] = None, by_name: Optional[str] = None) -> None:
        metadata_filter = self._build_metadata_filter(by_tags, by_name)
        self.manager._load_skills_from_module(module, metadata_filter)

    # ═══════════════════════════════════════════════════════
    # CARPETAS SKILL.MD (nuevo)
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
                    print(f"Error cargando {folder}: {e}")

        return loaded

    # ═══════════════════════════════════════════════════════
    # MANAGERS (nuevo)
    # ═══════════════════════════════════════════════════════

    def from_manager(self, manager: "SkillManager") -> str:
        """
        Agrega un SkillManager como sub-manager.

        Args:
            manager: SkillManager a agregar

        Returns:
            Nombre del manager agregado
        """
        if not manager.name:
            raise ValueError("El SkillManager debe tener un nombre para ser agregado como sub-manager")
        self.manager.managers[manager.name] = manager
        return manager.name

    def from_managers(self, managers: List["SkillManager"]) -> List[str]:
        """
        Agrega múltiples SkillManagers como sub-managers.

        Args:
            managers: Lista de SkillManagers a agregar

        Returns:
            Lista de nombres de managers agregados
        """
        return [self.from_manager(m) for m in managers]

class SkillManager:
    """
    Provide a way to register and retrieve skills.

    methods:
        register_skill(func): Register a skill function.
        get_skill_names(): Get a list of registered skill names.
        get_skills_with_keys(): Get a list of registered skill functions and their keys.
        get_all_skills_metadata(): Get metadata for all registered skills.
        get_skill_metadata_by_name(name): Get metadata for a skill by name.
        get_skills_by_tag(tag, return_keys=False): Get skills with a specific tag.
    """
    def __init__(
        self, 
        name: Optional[str] = None,                 # Nombre opcional
        description: Optional[str] = None,          # Descripción opcional
        skills: Optional[List[Callable]] = None,    # Carga skills directamente desde una lista
        skills_from_files: Optional[List[str]] = None,           # Carga skills desde archivos .py
        skills_from_folders: Optional[List[str]] = None,         # Carga skills desde carpetas
        global_instructions: str = ""          # Instrucciones globales del skill manager, que aplican para todas las skills
    ):
        # Almacenamos el módulo del contexto en el que se instanció el manager
        caller_frame = inspect.currentframe().f_back
        self.instantiation_module = inspect.getmodule(caller_frame)

        self.name = name
        self.description = description

        # Registro de funciones @skill (existente)
        self.registry: Dict[str, Any] = {}
        self.registry_by_name: Dict[str, List[Any]] = {}
        self.duplicates: Dict[str, List[Any]] = {}

        # Nuevos: skill folders y sub-managers
        self.skill_folders: Dict[str, AgentSkill] = {}
        self.managers: Dict[str, "SkillManager"] = {}

        # Estado de activación
        self._active_items: Dict[str, Any] = {}  # name -> skill/folder/manager activado

        # Se instancia la clase auxiliar para carga de skills.
        self.load_skills = SkillLoader(self)

        # Atributo de Instrucciones Globales
        self.global_instructions: str = global_instructions

        # Carga Inicial Declarativa de skills
        if skills:
            for func in skills:
                self.register_skill(func)
        
        if skills_from_files:
            for file_path in skills_from_files:
                self.load_skills.from_file(file_path)
                
        if skills_from_folders:
            for folder_path in skills_from_folders:
                self.load_skills.from_folder(folder_path)
        
        # Métodos de interfaz para setear y obtener instrucciones globales del SkillManager

    def set_global_instructions(self, text: str) -> None:
        """Establece las instrucciones globales para el uso de las skills de este manager."""
        if not isinstance(text, str):
            raise TypeError("Las instrucciones deben ser texto (str).")
        self.global_instructions = text

    def get_global_instructions(self) -> str:
        """Devuelve las instrucciones globales de las skills."""
        return self.global_instructions

    def register_skill(self, func) -> None:
        
        key = f"{func.__module__}.{func.__name__}"
        simple_name = func.__name__
        file_path = func.__code__.co_filename

        if simple_name in self.registry_by_name:
            if simple_name not in self.duplicates:
                self.duplicates[simple_name] = []
            self.duplicates[simple_name].append(func)
            print(f"Advertencia: La skill '{simple_name}' ya fue registrada en "
                  f"{self.registry_by_name[simple_name][0].__code__.co_filename}. "
                  f"La definición en {file_path} se ha agregado al registro de duplicados.")
        else:
            self.registry_by_name[simple_name] = [func]

        self.registry[key] = func



    def _load_skills_from_module(self, module, 
                                      metadata_filter: Optional[Callable[[Dict[str, Any]], bool]] = None) -> None:
       
        for attr_name in dir(module):
            attr = getattr(module, attr_name)
            if callable(attr) and hasattr(attr, 'skill_metadata'):
                if metadata_filter is not None:
                    if not metadata_filter(attr.skill_metadata):
                        continue
                self.register_skill(attr)

    def _load_skills_from_current_module(
        self, 
        metadata_filter: Optional[Callable[[Dict[str, Any]], bool]] = None
    ) -> None:
        # Usamos directamente el módulo almacenado en el constructor
        caller_module = self.instantiation_module
        if caller_module:
            self._load_skills_from_module(caller_module, metadata_filter)
        else:
            raise RuntimeError("No se pudo determinar el módulo que instanció SkillManager.")

    def _load_skills_from_file(self, file_path: str, 
                             metadata_filter: Optional[Callable[[Dict[str, Any]], bool]] = None) -> List[str]:
        if not os.path.isfile(file_path):
            raise ValueError(f"{file_path} no es un archivo válido.")
        
        module_name = os.path.splitext(os.path.basename(file_path))[0]
        spec = importlib.util.spec_from_file_location(module_name, file_path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        registered = []
        self._load_skills_from_module(module, metadata_filter)
        for attr_name in dir(module):
            attr = getattr(module, attr_name)
            if callable(attr) and hasattr(attr, 'skill_metadata'):
                registered.append(f"{attr.__module__}.{attr.__name__}")
        return registered

    def _load_skills_from_folder(self, folder_path: str, metadata_filter=None): 
        """
        Carga skills desde archivos Python en un directorio sin requerir que sean módulos importables.
        """
        if not os.path.isdir(folder_path):
            raise ValueError(f"{folder_path} no es una carpeta válida.")
        
        # registered = []
        
        # Recorre todos los archivos .py en la carpeta
        for filename in os.listdir(folder_path):
            # print(f"Procesando '{filename}'")
            if filename.endswith('.py'):
                file_path = os.path.join(folder_path, filename)
                module_name = os.path.splitext(filename)[0]
                            
                # Carga el módulo desde el archivo directamente
                try:
                    spec = importlib.util.spec_from_file_location(module_name, file_path)
                    module = importlib.util.module_from_spec(spec)
                    
                    # Registra el módulo temporalmente en sys.modules para permitir importaciones internas
                    sys.modules[module_name] = module
                    
                    # Ejecuta el módulo
                    spec.loader.exec_module(module)
                    
                    # Carga las skills desde el módulo
                    self._load_skills_from_module(module, metadata_filter)
                    
                    # # Registra las skills encontradas
                    # for attr_name in dir(module):
                    #     attr = getattr(module, attr_name)
                    #     if callable(attr) and hasattr(attr, 'skill_metadata'):
                    #         print(f"ver el interior de ATTR: {}")
                    #         registered.append(f"{attr._module}.{attr.name_}")
                    
                    # Opcional: limpiar sys.modules si no quieres mantener el módulo cargado
                    del sys.modules[module_name]
                    
                except Exception as e:
                    print(f"Error al cargar el archivo {file_path}: {e}")
        
        return f"Skills Loaded:{self.get_skill_names()} from {folder_path}"

    # Métodos de consulta y manejo del registro (se mantienen sin cambios)
    def get_skill_names(self) -> List[str]:
        return list({func.__name__ for func in self.registry.values()})

    def get_skills_with_keys(self) -> Dict[str, Any]:
        return self.registry

    def get_all_skills_metadata(self) -> Dict[str, Dict[str, Any]]:
        return {
            key: {"key": key, **func.skill_metadata}
            for key, func in sorted(self.registry.items())
        }
    
    def get_skill_metadata_by_name(self, name: str) -> Dict[str, Any]:
        matches = {key: func for key, func in self.registry.items() if func.__name__ == name}
        if not matches:
            return None
        if len(matches) == 1:
            return matches[next(iter(matches.keys()))].skill_metadata
        # For duplicate skills, just return the metadata of the first one
        return matches[next(iter(matches.keys()))].skill_metadata

    def get_skills_by_tag(self, tag: str, 
                          return_keys: bool = False) -> Union[List[str], Dict[str, Any]]:
        filtered = {
            key: func for key, func in self.registry.items()
            if tag in func.skill_metadata.get('tags', [])
        }
        if return_keys:
            return filtered
        else:
            return list({func.__name__ for func in filtered.values()})

    def get_skill_by_name(self, name: str) -> Union[Any, Dict[str, Any], None]:
        matches = {key: func for key, func in self.registry.items() if func.__name__ == name}
        if not matches:
            return None
        if len(matches) == 1:
            return next(iter(matches.values()))
        return matches

    def get_duplicate_skills(self) -> Dict[str, List[Any]]:
        return self.duplicates

    def remove_skill(self, name: str, module: Optional[str] = None) -> bool:
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
                print(f"Advertencia: Existen múltiples skills con el nombre '{name}'. Especifica el módulo para eliminar.")
                return False

    def clear_registry(self) -> None:
        self.registry.clear()
        self.registry_by_name.clear()
        self.duplicates.clear()

    def update_skill_metadata(self, key: str, new_metadata: Dict[str, Any]) -> bool:
        if key in self.registry:
            func = self.registry[key]
            func.skill_metadata.update(new_metadata)
            return True
        return False

    # ═══════════════════════════════════════════════════════
    # MÉTODOS DE NAVEGACIÓN (shelf)
    # ═══════════════════════════════════════════════════════

    def discover(self, path: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Lista contenido disponible (nivel 1 del progressive disclosure).

        Args:
            path: Path a un sub-manager para listar su contenido.
                  Si es None, lista el nivel superior.

        Returns:
            Lista de dicts con name, type, description de cada item
        """
        # Si hay path, navegar al sub-manager
        if path:
            target = self._resolve_path(path)
            if target and isinstance(target, SkillManager):
                return target.discover()
            return []

        discoveries = []

        # Skills Python (@skill functions)
        for func in self.registry.values():
            meta = func.skill_metadata
            discoveries.append({
                "name": meta["name"],
                "description": meta.get("description", ""),
                "type": "skill"
            })

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
                "children": children[:5]  # Solo primeros 5 para preview
            })

        return discoveries

    def activate(self, name: str, persistent: bool = True) -> Dict[str, Any]:
        """
        Activa un skill/folder/manager por nombre o path.

        Args:
            name: Nombre del item o path (ej: "manager/skill")
            persistent: Si True, registra los @skills encontrados

        Returns:
            Dict con info del item activado:
            - name: Nombre
            - type: "skill", "skill_folder", "manager"
            - instructions: Contenido/instrucciones (si aplica)
            - skills_loaded: Lista de @skills cargados (si aplica)
            - files: Lista de archivos disponibles (si es folder)
        """
        # Resolver el item (puede ser path o nombre)
        item, item_type = self._find_item(name)

        if item is None:
            raise ValueError(f"No se encontró: {name}")

        result = {"name": name, "type": item_type}

        if item_type == "skill":
            # Es una función @skill
            if persistent and name not in self.registry_by_name:
                self.register_skill(item)
            result["description"] = item.skill_metadata.get("description", "")
            result["skills_loaded"] = [name]

        elif item_type == "skill_folder":
            # Es un AgentSkill
            result["instructions"] = item.get_instructions()
            result["description"] = item.description
            result["files"] = item.list_files()
            result["skills_loaded"] = []

            # Cargar @skills que estén en scripts/ si existen archivos .py
            if persistent:
                for file_path in item.list_files("scripts"):
                    if file_path.endswith(".py"):
                        full_path = item.skill_path / file_path
                        try:
                            loaded = self._load_skills_from_file(str(full_path))
                            result["skills_loaded"].extend(loaded)
                        except Exception as e:
                            print(f"Error cargando skills de {file_path}: {e}")

        elif item_type == "manager":
            # Es un sub-manager
            result["description"] = item.description or ""
            result["contents"] = item.discover()
            result["skills_loaded"] = []

        # Registrar como activo
        self._active_items[name] = item

        return result

    def deactivate(self, name: str) -> bool:
        """
        Desactiva un item previamente activado.

        Args:
            name: Nombre del item a desactivar

        Returns:
            True si se desactivó, False si no estaba activo
        """
        if name in self._active_items:
            del self._active_items[name]
            return True
        return False

    def get_active_context(self) -> str:
        """
        Retorna las instrucciones concatenadas de todos los items activos.
        Útil para inyectar como contexto al agente.

        - Para AgentSkill (skill folders): usa get_instructions() (body del SKILL.md)
        - Para SkillManager: usa global_instructions
        """
        contexts = []

        for name, item in self._active_items.items():
            if isinstance(item, AgentSkill):
                contexts.append(f"## {name}\n\n{item.get_instructions()}")
            elif isinstance(item, SkillManager):
                # Usar global_instructions del manager
                if item.global_instructions:
                    contexts.append(f"## {name}\n\n{item.global_instructions}")

        return "\n\n---\n\n".join(contexts)

    def clear_active(self) -> None:
        """Limpia todos los items activos."""
        self._active_items.clear()

    def find(self, query: str) -> List[Dict[str, Any]]:
        """
        Busca items en todo el árbol que coincidan con el query.

        Args:
            query: Texto a buscar en nombres

        Returns:
            Lista de dicts con name, type, path de cada coincidencia
        """
        results = []
        self._search_recursive(query, "", results)
        return results

    def _search_recursive(self, query: str, current_path: str, results: List[Dict[str, Any]]) -> None:
        """Búsqueda recursiva en el árbol."""
        # Buscar en skills
        for name in self.registry_by_name.keys():
            if query.lower() in name.lower():
                path = f"{current_path}/{name}" if current_path else name
                results.append({"name": name, "type": "skill", "path": path})

        # Buscar en skill folders
        for name in self.skill_folders.keys():
            if query.lower() in name.lower():
                path = f"{current_path}/{name}" if current_path else name
                results.append({"name": name, "type": "skill_folder", "path": path})

        # Buscar recursivamente en sub-managers
        for name, manager in self.managers.items():
            if query.lower() in name.lower():
                path = f"{current_path}/{name}" if current_path else name
                results.append({"name": name, "type": "manager", "path": path})
            # Continuar búsqueda dentro del manager
            sub_path = f"{current_path}/{name}" if current_path else name
            manager._search_recursive(query, sub_path, results)

    def _resolve_path(self, path: str) -> Optional[Any]:
        """Resuelve un path y retorna el item."""
        parts = path.split("/")
        current = self

        for part in parts:
            if isinstance(current, SkillManager):
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

    # ═══════════════════════════════════════════════════════
    # MÉTODOS PARA CONTEXTO EFÍMERO (usado por run())
    # ═══════════════════════════════════════════════════════

    def get_item_context(self, name: str) -> str:
        """
        Obtiene el contexto/instrucciones de un item SIN activarlo persistentemente.
        Útil para inyectar contexto efímero en un run() específico.

        Args:
            name: Nombre del item o path

        Returns:
            String con las instrucciones/contexto del item
        """
        item, item_type = self._find_item(name)

        if item is None:
            return ""

        if item_type == "skill_folder":
            return f"## {name}\n\n{item.get_instructions()}"
        elif item_type == "manager":
            # Para managers, usamos global_instructions (instrucciones completas)
            if item.global_instructions:
                return f"## {name}\n\n{item.global_instructions}"
            else:
                # Fallback si no hay instrucciones
                return f"## {name}\n\n{item.description or 'Sin instrucciones'}"
        elif item_type == "skill":
            # Para skills, retornamos la descripción
            desc = item.skill_metadata.get("description", "")
            return f"## {name}\n\n{desc}"

        return ""

    def get_item_skills(self, name: str) -> Dict[str, Callable]:
        """
        Obtiene los @skill de un item SIN registrarlos persistentemente.
        Útil para agregar tools efímeros en un run() específico.

        Args:
            name: Nombre del item o path

        Returns:
            Dict de {nombre: función} con los skills encontrados
        """
        item, item_type = self._find_item(name)

        if item is None:
            return {}

        skills = {}

        if item_type == "skill":
            # Es un skill directo
            skills[item.__name__] = item

        elif item_type == "skill_folder":
            # Cargar @skills de scripts/ sin registrarlos
            for file_path in item.list_files("scripts"):
                if file_path.endswith(".py"):
                    full_path = item.skill_path / file_path
                    try:
                        # Cargar módulo temporalmente
                        module_name = f"_temp_{item.name}_{Path(file_path).stem}"
                        spec = importlib.util.spec_from_file_location(module_name, str(full_path))
                        module = importlib.util.module_from_spec(spec)
                        spec.loader.exec_module(module)

                        # Encontrar @skills sin registrarlos
                        for attr_name in dir(module):
                            attr = getattr(module, attr_name)
                            if callable(attr) and hasattr(attr, 'skill_metadata'):
                                skills[attr.__name__] = attr
                    except Exception as e:
                        print(f"Error cargando skills de {file_path}: {e}")

        elif item_type == "manager":
            # Retornar todos los skills del manager
            for func in item.registry.values():
                skills[func.__name__] = func

        return skills

    def _find_item(self, name: str) -> tuple:
        """
        Encuentra un item por nombre o path.

        Returns:
            Tupla de (item, tipo) o (None, None) si no se encuentra
        """
        # Si tiene "/" es un path
        if "/" in name:
            item = self._resolve_path(name)
            if item:
                if isinstance(item, SkillManager):
                    return item, "manager"
                elif isinstance(item, AgentSkill):
                    return item, "skill_folder"
                elif callable(item):
                    return item, "skill"
            return None, None

        # Buscar por nombre simple
        # 1. En skills
        if name in self.registry_by_name:
            return self.registry_by_name[name][0], "skill"

        # 2. En skill folders
        if name in self.skill_folders:
            return self.skill_folders[name], "skill_folder"

        # 3. En managers
        if name in self.managers:
            return self.managers[name], "manager"

        # 4. Buscar recursivamente en managers (si nombre es único)
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