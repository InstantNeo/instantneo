# agent_skill.py
"""
Modelo para representar un Agent Skill cargado desde una carpeta SKILL.md
siguiendo el estándar Agent Skills (https://agentskills.io)
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any
from pathlib import Path


@dataclass
class AgentSkill:
    """
    Representa una carpeta tipo SKILL.md del estándar Agent Skills.

    Una carpeta skill tiene la estructura:
        mi-skill/
        ├── SKILL.md          # Requerido
        ├── scripts/          # Opcional
        ├── references/       # Opcional
        └── assets/           # Opcional
    """

    # Frontmatter (requeridos)
    name: str
    description: str

    # Contenido del body del SKILL.md
    instructions: str

    # Frontmatter (opcionales)
    license: Optional[str] = None
    compatibility: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None
    allowed_tools: Optional[List[str]] = None

    # Ruta a la carpeta del skill
    skill_path: Optional[Path] = None

    # Cache para lazy loading
    _file_cache: Dict[str, str] = field(default_factory=dict)

    @property
    def discovery_info(self) -> Dict[str, Any]:
        """
        Nivel 1 del Progressive Disclosure: Solo metadata ligera (~100 tokens).
        Usado para listar skills disponibles sin cargar todo el contenido.
        """
        return {
            "name": self.name,
            "description": self.description,
            "type": "skill_folder"
        }

    def get_instructions(self) -> str:
        """
        Nivel 2 del Progressive Disclosure: Instrucciones completas.
        Retorna el body del SKILL.md.
        """
        return self.instructions

    def get_file(self, relative_path: str) -> Optional[str]:
        """
        Nivel 3 del Progressive Disclosure: Carga archivo bajo demanda.

        Args:
            relative_path: Path relativo a la carpeta del skill
                          (ej: "scripts/extract.py", "references/API.md")

        Returns:
            Contenido del archivo o None si no existe
        """
        if relative_path in self._file_cache:
            return self._file_cache[relative_path]

        if self.skill_path:
            file_path = self.skill_path / relative_path
            if file_path.exists() and file_path.is_file():
                try:
                    content = file_path.read_text(encoding="utf-8")
                    self._file_cache[relative_path] = content
                    return content
                except Exception:
                    pass
        return None

    def list_files(self, subdir: Optional[str] = None) -> List[str]:
        """
        Lista archivos disponibles en la carpeta del skill.

        Args:
            subdir: Subdirectorio específico (ej: "scripts", "references", "assets")
                   Si es None, lista todos los archivos recursivamente.

        Returns:
            Lista de paths relativos a la carpeta del skill
        """
        if not self.skill_path:
            return []

        if subdir:
            target_dir = self.skill_path / subdir
            if target_dir.exists() and target_dir.is_dir():
                return [f"{subdir}/{f.name}" for f in target_dir.iterdir() if f.is_file()]
            return []
        else:
            # Lista todos los archivos recursivamente (excluyendo SKILL.md)
            files = []
            for item in self.skill_path.rglob("*"):
                if item.is_file() and item.name != "SKILL.md":
                    rel_path = item.relative_to(self.skill_path)
                    files.append(str(rel_path))
            return files

    def get_file_path(self, relative_path: str) -> Optional[Path]:
        """
        Retorna el path absoluto a un archivo.
        Útil para archivos binarios que no se pueden leer como texto.

        Args:
            relative_path: Path relativo a la carpeta del skill

        Returns:
            Path absoluto al archivo o None si no existe
        """
        if self.skill_path:
            file_path = self.skill_path / relative_path
            if file_path.exists():
                return file_path
        return None

    def __repr__(self) -> str:
        return f"AgentSkill(name='{self.name}', path='{self.skill_path}')"
