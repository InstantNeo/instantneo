#base_adapter.py
"""
Interfaz base abstracta para adapters de proveedores LLM.

Este módulo define el contrato que todos los adapters deben implementar.
Los adapters son responsables de:
1. Recibir StandardRequest del Core
2. Traducir al formato específico del proveedor
3. Usar el Fetcher para hacer la llamada HTTP
4. Traducir la respuesta a StandardResponse

Arquitectura:
    Core (InstantNeo)
        ↓ StandardRequest
    ProviderAdapter (traduce + usa fetcher)
        ↓ formato proveedor
    Fetcher (HTTP puro)
        ↓
    API Externa
"""

import warnings
from abc import ABC, abstractmethod
from typing import Dict, Iterator, Optional, Set

from instantneo.models.standard import (
    StandardRequest,
    StandardResponse,
    StandardStreamChunk,
)

# Supported reasoning options per provider with human-readable descriptions
_REASONING_OPTIONS: Dict[str, Dict[str, str]] = {
    "cerebras": {
        "effort": '"low" | "medium" | "high"',
    },
    "openai": {
        "effort": '"low" | "medium" | "high"',
        "summary": '"auto" | "concise" | "detailed"',
    },
    "anthropic": {
        "effort": '"low" | "medium" | "high"',
        "budget_tokens": "int (min 1024)",
    },
    "groq": {
        "effort": '"low" | "medium" | "high"',
    },
    "gemini": {
        "effort": '"low" | "medium" | "high"',
        "budget_tokens": "int",
    },
    "vertexai": {
        "effort": '"low" | "medium" | "high"',
        "budget_tokens": "int",
    },
}


class BaseAdapter(ABC):
    """
    Clase base abstracta para todos los adapters de proveedores.

    Cada adapter de proveedor (OpenAI, Anthropic, Groq) debe heredar
    de esta clase e implementar los métodos abstractos.

    El adapter encapsula:
    - La lógica de traducción de formatos
    - La instancia del fetcher correspondiente
    - El manejo de errores específico del proveedor
    """

    @abstractmethod
    def complete(self, request: StandardRequest) -> StandardResponse:
        """
        Ejecuta una completion y devuelve la respuesta estandarizada.

        Args:
            request: Petición en formato estándar

        Returns:
            StandardResponse con la respuesta del modelo

        Raises:
            RuntimeError: Si hay un error en la API del proveedor
        """
        pass

    @abstractmethod
    def complete_stream(self, request: StandardRequest) -> Iterator[StandardStreamChunk]:
        """
        Ejecuta una completion con streaming.

        Args:
            request: Petición en formato estándar (stream se fuerza a True)

        Yields:
            StandardStreamChunk con fragmentos incrementales de la respuesta

        Raises:
            RuntimeError: Si hay un error en la API del proveedor
        """
        pass

    def supports_images(self) -> bool:
        """
        Indica si el adapter soporta imágenes en los mensajes.

        Returns:
            True si soporta imágenes, False en caso contrario

        Note:
            Los subclases deben sobrescribir este método si soportan imágenes.
        """
        return False

    def supports_tools(self) -> bool:
        """
        Indica si el adapter soporta herramientas/funciones.

        Returns:
            True si soporta tools, False en caso contrario

        Note:
            Por defecto True, ya que la mayoría de proveedores modernos lo soportan.
        """
        return True

    def supports_streaming(self) -> bool:
        """
        Indica si el adapter soporta streaming.

        Returns:
            True si soporta streaming, False en caso contrario

        Note:
            Por defecto True, ya que la mayoría de proveedores modernos lo soportan.
        """
        return True

    def get_provider_name(self) -> str:
        """
        Devuelve el nombre del proveedor.

        Returns:
            Nombre del proveedor (ej: "openai", "anthropic", "groq")
        """
        # Por defecto, extrae del nombre de la clase
        class_name = self.__class__.__name__
        return class_name.replace("Adapter", "").lower()

    def _warn_unsupported_reasoning_keys(self, reasoning_config: dict, supported_keys: Set[str]) -> None:
        """Warn about unsupported reasoning keys and describe available options."""
        provider = self.get_provider_name()
        unsupported = set(reasoning_config.keys()) - supported_keys
        if unsupported:
            opts = _REASONING_OPTIONS.get(provider, {})
            opts_str = ", ".join(f'"{k}": {v}' for k, v in opts.items())
            warnings.warn(
                f"{provider} does not support reasoning option(s): {unsupported}. "
                f"Supported options for {provider}: {{{opts_str}}}",
                stacklevel=5,
            )

    # =========================================================================
    # MÉTODOS LEGACY (compatibilidad hacia atrás)
    # =========================================================================
    # Estos métodos mantienen compatibilidad con el core actual mientras
    # se migra a la nueva arquitectura. Serán deprecados en futuras versiones.

    def create_chat_completion(self, **kwargs) -> StandardResponse:
        """
        LEGACY: Método de compatibilidad con el core actual.

        Convierte los kwargs al formato StandardRequest y llama a complete().
        Este método será deprecado cuando el core migre a StandardRequest.
        """
        from instantneo.models.standard import StandardMessage, StandardTool, StandardToolChoice

        # Extraer mensajes
        messages = []
        for msg in kwargs.get("messages", []):
            messages.append(StandardMessage(
                role=msg["role"],
                content=msg["content"],
                name=msg.get("name"),
                tool_call_id=msg.get("tool_call_id"),
            ))

        # Extraer tools si existen
        tools = None
        if "tools" in kwargs and kwargs["tools"]:
            tools = []
            for tool in kwargs["tools"]:
                if "function" in tool:
                    func = tool["function"]
                    tools.append(StandardTool(
                        name=func["name"],
                        description=func.get("description", ""),
                        parameters=func.get("parameters", {}),
                    ))
                else:
                    tools.append(StandardTool(
                        name=tool["name"],
                        description=tool.get("description", ""),
                        parameters=tool.get("parameters", {}),
                    ))

        # Extraer tool_choice
        tool_choice = None
        if "tool_choice" in kwargs and kwargs["tool_choice"]:
            tc = kwargs["tool_choice"]
            if isinstance(tc, str):
                tool_choice = StandardToolChoice(type=tc if tc in ["auto", "none", "required"] else "auto")
            elif isinstance(tc, dict):
                tool_choice = StandardToolChoice(
                    type="specific",
                    name=tc.get("function", {}).get("name") or tc.get("name")
                )

        # Construir request estándar
        request = StandardRequest(
            model=kwargs.get("model", ""),
            messages=messages,
            max_tokens=kwargs.get("max_tokens"),
            temperature=kwargs.get("temperature"),
            top_p=kwargs.get("top_p"),
            stream=kwargs.get("stream", False),
            tools=tools,
            tool_choice=tool_choice,
            stop=kwargs.get("stop"),
            seed=kwargs.get("seed"),
            reasoning=kwargs.get("reasoning"),
        )

        return self.complete(request)

    def create_streaming_chat_completion(self, **kwargs):
        """
        LEGACY: Método de compatibilidad con el core actual para streaming.

        Este método será deprecado cuando el core migre a StandardRequest.
        """
        from instantneo.models.standard import StandardMessage, StandardTool

        # Similar a create_chat_completion pero para streaming
        messages = []
        for msg in kwargs.get("messages", []):
            messages.append(StandardMessage(
                role=msg["role"],
                content=msg["content"],
                name=msg.get("name"),
                tool_call_id=msg.get("tool_call_id"),
            ))

        tools = None
        if "tools" in kwargs and kwargs["tools"]:
            tools = []
            for tool in kwargs["tools"]:
                if "function" in tool:
                    func = tool["function"]
                    tools.append(StandardTool(
                        name=func["name"],
                        description=func.get("description", ""),
                        parameters=func.get("parameters", {}),
                    ))

        request = StandardRequest(
            model=kwargs.get("model", ""),
            messages=messages,
            max_tokens=kwargs.get("max_tokens"),
            temperature=kwargs.get("temperature"),
            stream=True,
            tools=tools,
            reasoning=kwargs.get("reasoning"),
        )

        # Para compatibilidad, el core espera strings or chunks
        # Yield full chunk objects so core can access reasoning deltas
        for chunk in self.complete_stream(request):
            yield chunk

    def format_messages(self, messages):
        """LEGACY: Método de compatibilidad. Ya no se usa en la nueva arquitectura."""
        return messages

    def format_tools(self, tools):
        """LEGACY: Método de compatibilidad. Ya no se usa en la nueva arquitectura."""
        return tools
