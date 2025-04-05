"""
Módulo MCP para InstantNeo.

Este módulo proporciona la implementación del Model Context Protocol (MCP)
para InstantNeo, permitiendo exponer skills como tools MCP.
"""

from .server.core import InstantMCPServer

__all__ = ["InstantMCPServer"]