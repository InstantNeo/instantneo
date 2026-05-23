"""Shim de compatibilidad.

La metadata del proyecto vive en ``pyproject.toml`` (PEP 621). Este archivo
solo existe para herramientas que aún invocan ``setup.py`` directamente; no
duplica metadata.
"""
from setuptools import setup

setup()
