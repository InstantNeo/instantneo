# skill_md_parser.py
"""
Parser para archivos SKILL.md del estándar Agent Skills.

El formato SKILL.md consiste en:
- Frontmatter YAML (entre --- y ---)
- Body en Markdown con instrucciones
"""

import logging
import re
import yaml
from pathlib import Path
from typing import List, Dict, Optional, Any

from .agent_skill import AgentSkill

logger = logging.getLogger(__name__)


class SkillMdParser:
    """Parser para archivos SKILL.md del estándar Agent Skills."""

    # Regex para extraer frontmatter YAML y body
    FRONTMATTER_PATTERN = re.compile(
        r"^---\s*\n(.*?)\n---\s*\n(.*)$",
        re.DOTALL
    )

    @classmethod
    def parse_content(cls, content: str, skill_path: Optional[Path] = None) -> AgentSkill:
        """
        Parsea el contenido de un SKILL.md.

        Args:
            content: Contenido del archivo SKILL.md
            skill_path: Path a la carpeta que contiene el SKILL.md

        Returns:
            AgentSkill con los datos parseados

        Raises:
            ValueError: Si el formato es inválido o faltan campos requeridos
        """
        match = cls.FRONTMATTER_PATTERN.match(content)
        if not match:
            raise ValueError(
                "SKILL.md debe tener frontmatter YAML válido (entre --- y ---)"
            )

        frontmatter_str, body = match.groups()

        try:
            frontmatter = yaml.safe_load(frontmatter_str)
        except yaml.YAMLError as e:
            raise ValueError(f"Error parseando frontmatter YAML: {e}")

        if not frontmatter:
            frontmatter = {}

        # Validar campos requeridos
        if "name" not in frontmatter or not frontmatter["name"]:
            raise ValueError("Campo 'name' es requerido en SKILL.md")
        if "description" not in frontmatter or not frontmatter["description"]:
            raise ValueError("Campo 'description' es requerido en SKILL.md")

        # Parsear allowed-tools (espacio-separados según el estándar)
        allowed_tools = None
        if frontmatter.get("allowed-tools"):
            allowed_tools = frontmatter["allowed-tools"].split()

        return AgentSkill(
            name=frontmatter["name"],
            description=frontmatter["description"],
            instructions=body.strip(),
            license=frontmatter.get("license"),
            compatibility=frontmatter.get("compatibility"),
            metadata=frontmatter.get("metadata"),
            allowed_tools=allowed_tools,
            skill_path=skill_path
        )

    @classmethod
    def parse_file(cls, skill_md_path: str) -> AgentSkill:
        """
        Parsea un archivo SKILL.md desde su path.

        Args:
            skill_md_path: Path al archivo SKILL.md

        Returns:
            AgentSkill con los datos parseados
        """
        path = Path(skill_md_path)
        if not path.exists():
            raise FileNotFoundError(f"No se encontró: {skill_md_path}")

        content = path.read_text(encoding="utf-8")
        # El skill_path es la carpeta padre del SKILL.md
        return cls.parse_content(content, skill_path=path.parent)

    @classmethod
    def parse_folder(cls, folder_path: str) -> AgentSkill:
        """
        Parsea una carpeta que contiene SKILL.md.

        Args:
            folder_path: Path a la carpeta del skill

        Returns:
            AgentSkill con los datos parseados

        Raises:
            FileNotFoundError: Si no existe SKILL.md en la carpeta
        """
        path = Path(folder_path)
        skill_md = path / "SKILL.md"

        if not skill_md.exists():
            raise FileNotFoundError(
                f"No se encontró SKILL.md en {folder_path}"
            )

        content = skill_md.read_text(encoding="utf-8")
        return cls.parse_content(content, skill_path=path)

    @classmethod
    def discover_folders(cls, root_path: str) -> List[Dict[str, Any]]:
        """
        Descubre carpetas con SKILL.md en un directorio.
        Solo retorna metadata ligera (discovery info), no carga todo el contenido.

        Args:
            root_path: Directorio raíz donde buscar

        Returns:
            Lista de dicts con name, description, path de cada skill encontrado
        """
        root = Path(root_path)
        discoveries = []

        for folder in root.iterdir():
            if folder.is_dir():
                skill_md = folder / "SKILL.md"
                if skill_md.exists():
                    try:
                        # Solo parseamos para obtener name y description
                        content = skill_md.read_text(encoding="utf-8")
                        match = cls.FRONTMATTER_PATTERN.match(content)
                        if match:
                            frontmatter = yaml.safe_load(match.group(1))
                            if frontmatter:
                                discoveries.append({
                                    "name": frontmatter.get("name"),
                                    "description": frontmatter.get("description"),
                                    "path": str(folder),
                                    "type": "skill_folder"
                                })
                    except Exception:
                        logger.exception("Error parseando %s", folder)

        return discoveries
