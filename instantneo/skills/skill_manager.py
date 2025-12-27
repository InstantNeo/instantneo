import sys
import os
import pkgutil
import importlib
import importlib.util
import inspect
from typing import Dict, List, Any, Union, Optional, Callable

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

        self.registry: Dict[str, Any] = {}
        self.registry_by_name: Dict[str, List[Any]] = {}
        self.duplicates: Dict[str, List[Any]] = {}
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