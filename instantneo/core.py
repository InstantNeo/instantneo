from dataclasses import dataclass, field
from typing import List, Dict, Any, Callable, Optional, Union, Generator, Type, AsyncGenerator
import asyncio
import json
import logging
import time
import threading
from datetime import datetime, timezone

logger = logging.getLogger(__name__)
from instantneo.skills.agent_capabilities import AgentCapabilities
from instantneo.skills.agent_capabilities import AgentCapabilities as SkillManager  # backward compat
from instantneo.models.run_info import RunInfo, LLMCall, ToolExecution, SkillExecution
from instantneo.skills.capabilities_operations import CapabilitiesOperations
from instantneo.skills.capabilities_operations import CapabilitiesOperations as SkillManagerOperations  # backward compat
from instantneo.utils.image_utils import process_images
from instantneo.utils.tool_utils import format_tool


@dataclass(kw_only=True)
class BaseParams:
    """Base class for all parameter classes with common LLM parameters."""
    model: str
    temperature: Optional[float] = None
    max_tokens: Optional[int] = None
    presence_penalty: Optional[float] = None
    frequency_penalty: Optional[float] = None
    stop: Optional[Union[str, List[str]]] = None
    logit_bias: Optional[Dict[int, float]] = None
    seed: Optional[int] = None
    stream: bool = False


@dataclass(kw_only=True)
class InstantNeoParams(BaseParams):
    """Parameters for initializing an InstantNeo instance."""
    provider: str
    api_key: Optional[str] = None
    role_setup: str
    tools: Optional[Union[List[str], AgentCapabilities, List[AgentCapabilities]]] = None
    images: Optional[Union[str, List[str]]] = None
    image_detail: str = "auto"
    # Vertex AI specific parameters
    location: Optional[str] = None
    service_account_file: Optional[str] = None


@dataclass
class RunParams(BaseParams):
    """Parameters for a specific run."""
    prompt: str
    role_setup: Optional[str] = None
    execution_mode: str = "wait_response"
    async_execution: bool = False
    return_full_response: bool = False
    tools: Optional[List[str]] = None,
    images: Optional[Union[str, List[str]]] = None
    image_detail: Optional[str] = None
    additional_params: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_instantneo_params(cls, instantneo_params: InstantNeoParams, prompt: str, **kwargs):
        """Create a RunParams instance from InstantNeoParams."""
        run_params = cls(
            prompt=prompt,
            model=instantneo_params.model,
            role_setup=instantneo_params.role_setup,
            temperature=instantneo_params.temperature,
            max_tokens=instantneo_params.max_tokens,
            presence_penalty=instantneo_params.presence_penalty,
            frequency_penalty=instantneo_params.frequency_penalty,
            stop=instantneo_params.stop,
            logit_bias=instantneo_params.logit_bias,
            seed=instantneo_params.seed,
            stream=instantneo_params.stream,
            tools=instantneo_params.tools,
            images=instantneo_params.images,
            image_detail=instantneo_params.image_detail,
        )

        # Override with any provided kwargs
        for key, value in kwargs.items():
            if hasattr(run_params, key):
                setattr(run_params, key, value)
            else:
                run_params.additional_params[key] = value

        return run_params

    def to_dict(self) -> Dict[str, Any]:
        """Snapshot completo de los kwargs efectivos del run.

        Diseñado para alimentar ``RunInfo.run_params`` y, vía el bridge,
        quedar reflejado en ``Entry(type="response").content["run_params"]``.

        Incluye todos los campos del dataclass excepto:

        - ``prompt``: vive aparte en ``RunInfo.prompt``, no duplicar.
        - ``additional_params``: se spreadea al top level (es lo que
          espera el consumidor del snapshot — kwargs planos, no anidados).

        Si querés ver exactamente qué pasó (e.g. ``reasoning="high"``,
        ``image_detail="low"``, kwargs custom), todo aparece acá.
        """
        EXCLUDE = {"prompt", "additional_params"}
        result = {k: v for k, v in self.__dict__.items() if k not in EXCLUDE}
        result.update(self.additional_params)
        return result


@dataclass
class AdapterParams(BaseParams):
    """Parameters for adapter-specific operations."""
    messages: List[Dict[str, Any]]
    additional_params: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_run_params(cls, run_params: RunParams, messages: List[Dict[str, Any]]):
        """Create an AdapterParams instance from RunParams."""
        adapter_params = cls(
            model=run_params.model,
            messages=messages,
            temperature=run_params.temperature,
            max_tokens=run_params.max_tokens,
            presence_penalty=run_params.presence_penalty,
            frequency_penalty=run_params.frequency_penalty,
            stop=run_params.stop,
            logit_bias=run_params.logit_bias,
            seed=run_params.seed,
            stream=run_params.stream,
        )

        # Exclude specific parameters from additional_params
        exclude_params = {'execution_mode', 'async_execution', 'return_full_response',
                          'prompt', 'role_setup', 'skills', 'images', 'image_detail'}

        adapter_params.additional_params = {
            k: v for k, v in run_params.additional_params.items()
            if k not in exclude_params
        }

        return adapter_params

    def to_dict(self) -> Dict[str, Any]:
        """Convert the adapter parameters to a dictionary."""
        result = {k: v for k, v in self.__dict__.items(
        ) if v is not None and k != 'additional_params'}
        result.update(self.additional_params)
        return result


@dataclass
class ImageConfig:
    """Configuration for image processing."""
    images: Union[str, List[str]]
    image_detail: str = "auto"
    convert_to_base64: bool = True


class InstantNeo:
    """
    Main class to instantiate an agent with InstantNeo.

    InstantNeo facilitates interaction with various Large Language Model (LLM) providers,
    such as OpenAI, Anthropic, Groq, Gemini, and Vertex AI, by providing a unified interface.
    It supports text generation, function calling (skills), and image processing, making it
    versatile for a wide range of applications.

    Args:
        provider (str): The LLM provider to use. Supported providers are:
            - "openai": OpenAI's models.
            - "anthropic": Anthropic's models.
            - "groq": Groq's models.
            - "gemini": Google Gemini API (requires api_key).
            - "vertexai": Google Vertex AI (requires service_account_file and location).
        api_key (str): API key for accessing the specified provider.
            Required for: openai, anthropic, groq, gemini.
        model (str): The name of the language model to use.
        role_setup (str): Initial role setup or system prompt for the agent.
        skills (Optional[Union[List[str], SkillManager]], optional): Skills to be registered
            and made available to the agent. Can be a list of skills (functions) or a SkillManager instance.
            Defaults to None.
        temperature (Optional[float], optional): Sampling temperature for text generation.
            Defaults to None, using provider's default.
        max_tokens (Optional[int], optional): Maximum number of tokens to generate in the response.
            Defaults to 200.
        presence_penalty (Optional[float], optional): Presence penalty for text generation.
            Defaults to None, using provider's default.
        frequency_penalty (Optional[float], optional): Frequency penalty for text generation.
            Defaults to None, using provider's default.
        stop (Optional[Union[str, List[str]]], optional): Stop sequences for text generation.
            Defaults to None, using provider's default.
        logit_bias (Optional[Dict[int, float]], optional): Logit bias for token probabilities.
            Defaults to None, using provider's default.
        seed (Optional[int], optional): Seed for reproducible text generation.
            Defaults to None, using provider's default.
        stream (bool, optional): Enable streaming of the response. Defaults to False.
        images (Optional[Union[str, List[str]]], optional): Paths or URLs to images to be included
            in the context. Supported by providers that handle multimodal inputs. Defaults to None.
        location (Optional[str], optional): Vertex AI region (e.g., "us-central1").
            Required for provider="vertexai".
        service_account_file (Optional[str], optional): Path to Google service account JSON file.
            Required for provider="vertexai".
    """
    WAIT_RESPONSE = "wait_response"
    EXECUTION_ONLY = "execution_only"
    GET_ARGS = "get_args"

    def __init__(
        self,
        provider: str,
        api_key: Optional[str],
        model: str,
        role_setup: str,
        tools: Optional[Union[List[str], AgentCapabilities, List[AgentCapabilities]]] = None,
        skills=None,  # backward compat alias for tools
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = 200,
        presence_penalty: Optional[float] = None,
        frequency_penalty: Optional[float] = None,
        stop: Optional[Union[str, List[str]]] = None,
        logit_bias: Optional[Dict[int, float]] = None,
        seed: Optional[int] = None,
        stream: bool = False,
        images: Optional[Union[str, List[str]]] = None,
        image_detail: str = "auto",
        # Vertex AI specific parameters
        location: Optional[str] = None,
        service_account_file: Optional[str] = None,
    ):
        """Initialize an InstantNeo instance."""
        # Accept skills= as backward compat alias for tools=
        if skills is not None and tools is None:
            tools = skills

        self.config = InstantNeoParams(
            provider=provider,
            api_key=api_key,
            model=model,
            role_setup=role_setup,
            tools=tools,
            temperature=temperature,
            max_tokens=max_tokens,
            presence_penalty=presence_penalty,
            frequency_penalty=frequency_penalty,
            stop=stop,
            logit_bias=logit_bias,
            seed=seed,
            stream=stream,
            images=images,
            image_detail=image_detail,
            location=location,
            service_account_file=service_account_file,
        )

        # Initialize capabilities
        tools_input = self.config.tools

        if isinstance(tools_input, AgentCapabilities):
                    # Caso 1: Un solo AgentCapabilities -> Asignación directa
                    self.capabilities = tools_input
        elif isinstance(tools_input, list):
            if all(isinstance(s, AgentCapabilities) for s in tools_input):
                # Caso 2: Lista de AgentCapabilities -> Usar la unión
                self.capabilities = CapabilitiesOperations.union(*tools_input)
            elif all(callable(s) or isinstance(s, str) for s in tools_input):
                # Caso 3: Lista de funciones -> Crear capabilities y registrar
                self.capabilities = AgentCapabilities()
                for tool_func in tools_input:
                    self.capabilities.register_tool(tool_func)
            else:
                # Caso 4: Lista mixta o no válida
                raise TypeError(
                    "Invalid tools list format. 'tools' must be a single AgentCapabilities, "
                    "a list of AgentCapabilities, or a list of functions/tool names (str). "
                    "Mixed types in the list are not allowed."
                )
        else: # tools is None
                self.capabilities = AgentCapabilities()

        # Extracción y concatenación de instrucciones globales del SkillManager
        final_instructions = ""
        #Obtenemos las instrucciones globales de AgentCapabilities
        if hasattr(self.capabilities, 'get_global_instructions'):
            final_instructions = self.capabilities.get_global_instructions()

        self.tool_instructions = ""
        if final_instructions and final_instructions.strip():
            self.tool_instructions = f"""
            ###################################
            ##       TOOLS INSTRUCTIONS       ##
            ###################################

            {final_instructions.strip()}"""

        self.adapter = self._create_adapter()
        self.async_execution = False  # Default value, will be set in run method
        self._last_run: Optional[RunInfo] = None

    ##################################
    #         PUBLIC METHODS         #
    ##################################

    @property
    def last_run(self) -> Optional[RunInfo]:
        """Returns the RunInfo from the most recent run() call."""
        return self._last_run

    @property
    def skill_manager(self):
        """Backward compatibility alias for self.capabilities."""
        return self.capabilities

    ##### Tool Management #####
    def mod_role(self,new_role):
        self.config.role_setup = new_role
        return

    # New canonical methods
    def register_tool(self, tool_func: Callable) -> None:
        """Register a tool in the AgentCapabilities."""
        return self.capabilities.register_tool(tool_func)

    def get_tool_names(self) -> List[str]:
        """Get the names of all registered tools."""
        return self.capabilities.get_tool_names()

    def get_tool_by_name(self, name: str) -> Union[Any, Dict[str, Any], None]:
        """Get a tool by its name."""
        return self.capabilities.get_tool_by_name(name)

    def get_tool_metadata_by_name(self, name: str) -> Dict[str, Any]:
        """Get the metadata of a tool by its name."""
        return self.capabilities.get_tool_metadata_by_name(name)

    def get_tools_by_tag(self, tag: str, return_keys: bool = False) -> Union[List[str], Dict[str, Any]]:
        """Get tools by tag."""
        return self.capabilities.get_tools_by_tag(tag, return_keys)

    def get_all_tools_metadata(self) -> Dict[str, Dict[str, Any]]:
        """Get the metadata of all tools."""
        return self.capabilities.get_all_tools_metadata()

    def get_duplicate_tools(self) -> Dict[str, List[Any]]:
        """Get duplicate tools."""
        return self.capabilities.get_duplicate_tools()

    def remove_tool(self, tool_name: str, module: Optional[str] = None) -> bool:
        """Remove a tool by its name."""
        return self.capabilities.remove_tool(tool_name, module)

    def update_tool_metadata(self, key: str, new_metadata: Dict[str, Any]) -> bool:
        """Update the metadata of a tool."""
        return self.capabilities.update_tool_metadata(key, new_metadata)

    def clear_registry(self) -> None:
        """Clear the tool registry."""
        return self.capabilities.clear_registry()

    # Backward compatibility methods
    def add_skill(self, skill: Callable):
        """Deprecated. Use register_tool instead."""
        return self.register_tool(skill)

    def list_skills(self) -> List[str]:
        """Deprecated. Use get_tool_names instead."""
        return self.get_tool_names()

    def register_skill(self, skill: Callable) -> None:
        """Backward compat alias for register_tool."""
        return self.register_tool(skill)

    def get_skill_names(self) -> List[str]:
        """Backward compat alias for get_tool_names."""
        return self.get_tool_names()

    def get_skill_by_name(self, name: str) -> Union[Any, Dict[str, Any], None]:
        """Backward compat alias for get_tool_by_name."""
        return self.get_tool_by_name(name)

    def get_skill_metadata_by_name(self, name: str) -> Dict[str, Any]:
        """Backward compat alias for get_tool_metadata_by_name."""
        return self.get_tool_metadata_by_name(name)

    def get_skills_by_tag(self, tag: str, return_keys: bool = False) -> Union[List[str], Dict[str, Any]]:
        """Backward compat alias for get_tools_by_tag."""
        return self.get_tools_by_tag(tag, return_keys)

    def get_all_skills_metadata(self) -> Dict[str, Dict[str, Any]]:
        """Backward compat alias for get_all_tools_metadata."""
        return self.get_all_tools_metadata()

    def get_duplicate_skills(self) -> Dict[str, List[Any]]:
        """Backward compat alias for get_duplicate_tools."""
        return self.get_duplicate_tools()

    def remove_skill(self, skill_name: str, module: Optional[str] = None) -> bool:
        """Backward compat alias for remove_tool."""
        return self.remove_tool(skill_name, module)

    def update_skill_metadata(self, key: str, new_metadata: Dict[str, Any]) -> bool:
        """Backward compat alias for update_tool_metadata."""
        return self.update_tool_metadata(key, new_metadata)

    def load_skills_from_file(self, file_path: str, metadata_filter: Optional[Callable[[Dict[str, Any]], bool]] = None) -> None:
        """Load skills from a file.

        Args:
            file_path (str): The path to the file.
            metadata_filter (Optional[Callable[[Dict[str, Any]], bool]], optional): A function to filter skills by metadata. Defaults to None."""
        return self.capabilities._load_skills_from_file(file_path, metadata_filter)

    def load_skills_from_current(self,
                                 metadata_filter: Optional[Callable[[Dict[str, Any]], bool]] = None) -> None:
        """Load skills from the current file.

        Args:
            metadata_filter (Optional[Callable[[Dict[str, Any]], bool]], optional): A function to filter skills by metadata. Defaults to None."""
        return self.capabilities._load_skills_from_current_module(metadata_filter)
    
    def load_skills_from_folder(self, folder_path: str, metadata_filter: Optional[Callable[[Dict[str, Any]], bool]] = None) -> None:
        """Load skills from a folder.

        Args:
            folder_path (str): The path to the folder.
            metadata_filter (Optional[Callable[[Dict[str, Any]], bool]], optional): A function to filter skills by metadata. Defaults to None."""
        return self.capabilities._load_skills_from_folder(folder_path, metadata_filter)



    ##### Skill Operations #####

    def sm_ops_union(self, *otros_managers) -> None:
        """
        Combines the skills of this SkillManager with other SkillManagers or InstantNeo Agents,
        replacing the internal skills with the union of both.
        """
        from instantneo.skills.capabilities_operations import CapabilitiesOperations as SkillManagerOperations  # backward compat
        # Inicializar con el propio SkillManager
        managers_para_union = [self.capabilities]
        for manager_or_neo in otros_managers:
            if isinstance(manager_or_neo, InstantNeo):
                # Usar el SkillManager interno de InstantNeo
                managers_para_union.append(manager_or_neo.skill_manager)
            else:
                # Usar SkillManager directamente
                managers_para_union.append(manager_or_neo)
        self.capabilities = CapabilitiesOperations.union(*managers_para_union)

    def sm_ops_intersection(self, *otros_managers) -> None:
        """
        Performs the intersection of skills with other SkillManagers or InstantNeos,
        replacing the internal skills with the intersection of both.
        """
        from instantneo.skills.capabilities_operations import CapabilitiesOperations as SkillManagerOperations  # backward compat
        # Inicializar con el propio SkillManager
        managers_para_interseccion = [self.capabilities]
        for manager_or_neo in otros_managers:
            if isinstance(manager_or_neo, InstantNeo):
                # Usar el SkillManager interno de InstantNeo
                managers_para_interseccion.append(manager_or_neo.skill_manager)
            else:
                # Usar SkillManager directamente
                managers_para_interseccion.append(manager_or_neo)
        self.capabilities = SkillManagerOperations.intersection(
            *managers_para_interseccion)

    def sm_ops_difference(self, exclude_manager) -> None:
        """
        Calculates the difference of skills with another SkillManager or InstantNeo,
        replacing the internal skills with those that are in this agent but not in the other.
        """
        from instantneo.skills.capabilities_operations import CapabilitiesOperations as SkillManagerOperations  # backward compat

        if isinstance(exclude_manager, InstantNeo):
            # Usar el SkillManager interno de InstantNeo
            exclude_skill_manager = exclude_manager.skill_manager
        else:
            exclude_skill_manager = exclude_manager  # Usar SkillManager directamente

        self.capabilities = SkillManagerOperations.difference(
            self.capabilities, exclude_skill_manager)

    def sm_ops_symmetric_difference(self, otro_manager) -> None:
        """
        Calculates the symmetric difference of skills with another SkillManager or InstantNeo,
        replacing the internal skills with the symmetric difference of both. That is, skills that are in this agent or in the incoming one, but NOT in both.
        """
        from instantneo.skills.capabilities_operations import CapabilitiesOperations as SkillManagerOperations  # backward compat

        if isinstance(otro_manager, InstantNeo):
            # Usar el SkillManager interno de InstantNeo
            otro_skill_manager = otro_manager.skill_manager
        else:
            otro_skill_manager = otro_manager  # Usar SkillManager directamente

        self.capabilities = SkillManagerOperations.symmetric_difference(
            self.capabilities, otro_skill_manager)

    def sm_ops_compare(self, otro_manager: Union["SkillManager", "InstantNeo"]) -> Dict[str, set[str]]:
        """
        Compares the SkillManager internal with another SkillManager or InstantNeo and returns
a dictionary with common and unique skills. It does not modify the internal skills.
        """
        from instantneo.skills.capabilities_operations import CapabilitiesOperations as SkillManagerOperations  # backward compat
        if isinstance(otro_manager, InstantNeo):
            # Usar el SkillManager interno de InstantNeo
            otro_skill_manager = otro_manager.skill_manager
        else:
            otro_skill_manager = otro_manager  # Usar SkillManager directamente

        return SkillManagerOperations.compare(self.capabilities, otro_skill_manager)

    def _normalize_reasoning(self, reasoning) -> Optional[Dict[str, Any]]:
        """Normalize the reasoning parameter to a standard dict format.

        Args:
            reasoning: Can be None, False, True, a string (effort level), or a dict.

        Returns:
            None or a dict with at least {"effort": str}
        """
        if reasoning is None or reasoning is False:
            return None
        if reasoning is True:
            return {"effort": "medium"}
        if isinstance(reasoning, str):
            valid = ("low", "medium", "high")
            if reasoning not in valid:
                import warnings
                warnings.warn(
                    f"Invalid reasoning effort '{reasoning}'. Valid values: {valid}. Falling back to 'medium'.",
                    stacklevel=3,
                )
                return {"effort": "medium"}
            return {"effort": reasoning}
        if isinstance(reasoning, dict):
            return reasoning
        raise ValueError(f"Invalid reasoning parameter: {reasoning}")

    def run(
        self,
        prompt: str,
        execution_mode: str = "wait_response",
        async_execution: bool = False,
        return_full_response: bool = False,
        tools: Optional[List[str]] = None,
        skills: Optional[List[str]] = None,  # backward compat alias for tools
        images: Optional[Union[str, List[str]]] = None,
        image_detail: Optional[str] = None,
        stream: bool = False,
        reasoning: Optional[Union[bool, str, Dict[str, Any]]] = None,
        think_loud: bool = False,
        **additional_params
    ):
        """Runs a prompt with the InstantNeo agent.

Args:
    prompt (str): The prompt to run.
    execution_mode (str, optional): The tool execution mode. Defaults to "wait_response".
        - "wait_response": Waits for the tool's response.
        - "execution_only": Executes the tool without waiting for the response.
        - "get_args": Gets the tool's name and arguments without executing it, for later use.
    async_execution (bool, optional): Asynchronous tool execution. Defaults to False.
    return_full_response (bool, optional): Returns the provider's full response. Defaults to False.
    tools (List[str], optional): The tools to use in this run; if not provided, the instance's configured tools are used.
    images (Optional[Union[str, List[str]]], optional): Images to use in this run.
    image_detail (Optional[str], optional): Detail of the images to use in this run.
    stream (bool, optional): Enable response streaming.
    reasoning (Optional[Union[bool, str, Dict[str, Any]]], optional): Enable reasoning/thinking.
        - True: Enable with default effort ("medium")
        - str: Effort level ("low", "medium", "high")
        - dict: Full config {"effort": str, "budget_tokens": int}
        - None/False: Disabled (default)
    think_loud (bool, optional): Include reasoning in the response output. Defaults to False.
        - Normal mode: returns {"text": ..., "reasoning": ...} instead of just text
        - Streaming mode: yields {"type": "reasoning"|"text", "content": ...} dicts
    additional_params (Dict[str, Any], optional): Additional parameters for the adapter.
        Can include:
            - model (str, optional): The model to use.
            - role_setup (str, optional): Role setup / system prompt.
            - temperature (float, optional): Temperature for sampling.
            - max_tokens (int, optional): Maximum number of tokens in the response.
            - presence_penalty (float, optional): Presence penalty.
            - frequency_penalty (float, optional): Frequency penalty.
            - stop (Optional[Union[str, List[str]]], optional): Stop sequence.
            - logit_bias (Optional[Dict[int, float]], optional): Logit bias.
            - seed (Optional[int], optional): Seed for reproducibility.
        """

        # Accept skills= as backward compat alias for tools=
        if skills is not None and tools is None:
            tools = skills

        # Determine which tools to use
        tools_to_use = tools if tools is not None else [name for name in self.get_tool_names()]

        # Create RunParams with explicit parameters
        run_params = RunParams(
            prompt=prompt,
            model=additional_params.get('model') if additional_params.get(
                'model') is not None else self.config.model,
            role_setup=additional_params.get('role_setup') if additional_params.get(
                'role_setup') is not None else self.config.role_setup,
            execution_mode=execution_mode,
            async_execution=async_execution,
            return_full_response=return_full_response,
            tools=tools_to_use,
            temperature=additional_params.get('temperature') if additional_params.get(
                'temperature') is not None else self.config.temperature,
            max_tokens=additional_params.get('max_tokens') if additional_params.get(
                'max_tokens') is not None else self.config.max_tokens,
            presence_penalty=additional_params.get('presence_penalty') if additional_params.get(
                'presence_penalty') is not None else self.config.presence_penalty,
            frequency_penalty=additional_params.get('frequency_penalty') if additional_params.get(
                'frequency_penalty') is not None else self.config.frequency_penalty,
            stop=additional_params.get('stop') if additional_params.get(
                'stop') is not None else self.config.stop,
            logit_bias=additional_params.get('logit_bias') if additional_params.get(
                'logit_bias') is not None else self.config.logit_bias,
            seed=additional_params.get('seed') if additional_params.get(
                'seed') is not None else self.config.seed,
            stream=stream,
            images=images if images is not None else self.config.images,
            image_detail=image_detail if image_detail is not None else self.config.image_detail,
        )

        # Normalize and add reasoning config
        reasoning_config = self._normalize_reasoning(reasoning)
        if reasoning_config:
            run_params.additional_params['reasoning'] = reasoning_config

        if run_params.execution_mode not in [self.WAIT_RESPONSE, self.EXECUTION_ONLY, self.GET_ARGS]:
            raise ValueError(
                f"Invalid execution_mode: {run_params.execution_mode}")

        self.async_execution = run_params.async_execution

        active_tools = self._get_active_tools(tools_to_use)

        # ═══════════════════════════════════════════════════════
        # SHELF CONTEXT (from activated items)
        # ═══════════════════════════════════════════════════════

        combined_context = ""
        if hasattr(self.capabilities, 'get_active_context'):
            combined_context = self.capabilities.get_active_context()

        image_config = self._get_image_config(run_params)

        messages = self._prepare_messages(run_params.prompt, image_config, combined_context)

        adapter_params = AdapterParams.from_run_params(run_params, messages)

        if active_tools:
            formatted_tools = []
            for name, tool_func in active_tools.items():
                tool_info = self.get_tool_metadata_by_name(name)

                if tool_info and 'parameters' in tool_info:
                    formatted_tools.append(format_tool(tool_info))
                else:
                    logger.warning("Tool '%s' is missing metadata or 'parameters'. Skipping.", name)

            if formatted_tools:
                adapter_params.additional_params['tools'] = formatted_tools
                if 'tool_choice' in run_params.additional_params:
                    adapter_params.additional_params['tool_choice'] = run_params.additional_params['tool_choice']


        # Create RunInfo to capture metadata
        run_info = RunInfo(
            provider=self.config.provider,
            model=run_params.model,
            prompt=prompt,
            execution_mode=execution_mode,
            stream=run_params.stream,
            timestamp=datetime.now(timezone.utc).isoformat(),
            messages_sent=messages,
            run_params=run_params.to_dict(),
        )

        start_time = time.perf_counter()

        if run_params.stream:
            # For streaming, assign run_info before returning the generator.
            # The generator populates it progressively as chunks are consumed.
            self._last_run = run_info
            return self._handle_streaming_response(adapter_params, run_params.execution_mode, run_params.return_full_response, run_info, start_time, think_loud)
        else:
            try:
                result = self._handle_normal_response(adapter_params, run_params.execution_mode, run_params.return_full_response, run_info, think_loud)
                run_info.duration_ms = (time.perf_counter() - start_time) * 1000
                return result
            except Exception as e:
                run_info.error = str(e)
                run_info.duration_ms = (time.perf_counter() - start_time) * 1000
                raise
            finally:
                self._last_run = run_info

    #################################
    #        PRIVATE METHODS        #
    #################################

    def _get_active_tools(self, tools: Optional[List[str]] = None) -> Dict[str, Callable]:
        """Get active tools based on the provided tool names."""
        active_tools = {}
        if tools is None:
            return active_tools

        if isinstance(tools, AgentCapabilities):
            tools = tools.get_tool_names()

        for tool_name in tools:
            tool_func = self.get_tool_by_name(tool_name)
            if isinstance(tool_func, dict):
                tool_func = next(iter(tool_func.values()))
            if tool_func:
                active_tools[tool_name] = tool_func
            else:
                logger.warning("Tool '%s' not found in AgentCapabilities.", tool_name)

        return active_tools

    def _get_image_config(self, run_params: RunParams) -> Optional[ImageConfig]:
        """Get image configuration from run parameters."""
        if run_params.images:
            return ImageConfig(images=run_params.images, image_detail=run_params.image_detail)
        elif self.config.images:
            return ImageConfig(images=self.config.images, image_detail=self.config.image_detail)
        return None

    def _process_images(self, image_config: ImageConfig) -> List[Dict[str, Any]]:
        """Process images according to the configuration."""
        if not self.adapter.supports_images():
            raise ValueError(
                "El proveedor actual no soporta el procesamiento de imágenes")
        return process_images(image_config.images, image_config.image_detail)

    def get_resolved_role_setup(self, shelf_context: Optional[str] = None) -> str:
        """System prompt final efectivo del agente.

        Compone ``self.config.role_setup`` + ``self.tool_instructions``
        (si las hay, generadas a partir de las tools registradas) +
        ``shelf_context`` (si se pasa). Es exactamente el string que
        el agente le manda al provider como mensaje ``system`` en cada
        run.

        Útil para:

        - **Logging / debug**: ver el system prompt completo sin
          ejecutar el run.
        - **Orquestadores**: capturar la cabecera en un ``run_start``
          entry (Loop, Pipeline futuro).
        - **Replay**: reconstruir exactamente lo que el agente "es"
          en un momento dado.

        Args:
            shelf_context: contexto adicional (persistente + efímero)
                que se inyecta al final del system prompt. None por
                default — no se inyecta nada.

        Returns:
            String final del system prompt. Si ``role_setup`` no está
            seteado y no hay ``tool_instructions`` ni ``shelf_context``,
            devuelve ``""``.
        """
        final = self.config.role_setup or ""
        if hasattr(self, 'tool_instructions') and self.tool_instructions:
            final = f"{final}{self.tool_instructions}"
        if shelf_context:
            final = f"""{final}

###################################
## ACTIVE KNOWLEDGE (from shelf) ##
###################################

{shelf_context}"""
        return final

    def _prepare_messages(
        self,
        prompt: str,
        image_config: Optional[ImageConfig] = None,
        shelf_context: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Prepare messages for the language model.

        Args:
            prompt: The user prompt
            image_config: Optional image configuration
            shelf_context: Optional context from shelf (persistent + ephemeral)
        """
        messages = []
        # La lógica de construcción del system prompt vive en el método
        # público `get_resolved_role_setup` (PR 6). Mantenemos
        # `final_role_setup` como variable local para no cambiar la
        # legibilidad del resto del método.
        final_role_setup = self.get_resolved_role_setup(shelf_context)

        if self.config.role_setup:
            messages.append(
                {"role": "system", "content": final_role_setup})
        if image_config and image_config.images:
            content = [{"type": "text", "text": prompt}]
            content.extend(process_images(
                image_config.images, image_config.image_detail))
            messages.append({"role": "user", "content": content})
        else:
            messages.append({"role": "user", "content": prompt})
        return messages

    def _process_response(self, response, execution_mode, run_info: Optional[RunInfo] = None, think_loud: bool = False):
        """Process the response from the language model."""
        if not hasattr(response, 'choices') or len(response.choices) == 0:
            return None

        choice = response.choices[0]
        if not hasattr(choice, 'message'):
            return None

        message = choice.message
        content = message.content if message.content else ''
        tool_calls = message.tool_calls if hasattr(
            message, 'tool_calls') else None
        reasoning = getattr(message, 'reasoning', None)

        if tool_calls:
            logger.debug("Executing %d tool call(s)", len(tool_calls))
            results = self._handle_tool_calls(tool_calls, execution_mode, run_info)
            result = {
                "text": content if content else None,
                "tool_results": results
            }
            if think_loud and reasoning:
                result["reasoning"] = reasoning
            return result
        else:
            if think_loud and reasoning:
                return {"text": content, "reasoning": reasoning}
            return content

    def _handle_tool_calls(self, tool_calls, execution_mode, run_info: Optional[RunInfo] = None):
        """Handle tool calls from the language model."""
        results = []
        futures = []  # Para almacenar futures en caso de ejecución asíncrona

        for tool_call in tool_calls:
            if tool_call.type == 'function':
                function_name = tool_call.function.name
                # `or {}` defensivo: si por cualquier ruta el adapter
                # dejó pasar args == None / "null" (JSON parsea a None),
                # tratamos como llamada sin args en lugar de crashear con
                # `tool_func(**None)`. El adapter ya normaliza a "{}"
                # (ver `_chat_completions._normalize_tool_arguments`),
                # esto es cinturón de seguridad para otras rutas.
                function_args = json.loads(tool_call.function.arguments) or {}

                if function_name in self.get_tool_names():
                    # Track tool execution
                    tool_exec = ToolExecution(
                        name=function_name,
                        arguments=function_args,
                        execution_mode=execution_mode,
                    )

                    if execution_mode == self.EXECUTION_ONLY:
                        try:
                            result = self._execute_tool(
                                function_name, function_args)
                            tool_exec.result = result
                        except Exception as e:
                            tool_exec.exception = str(e)
                            raise
                        if self.async_execution:
                            futures.append(result)
                    elif execution_mode == self.GET_ARGS:
                        tool_exec.result = {"name": function_name, "arguments": function_args}
                        results.append(
                            {"name": function_name, "arguments": function_args})
                    else:  # WAIT_RESPONSE
                        if self.async_execution:
                            try:
                                result = self._execute_tool(
                                    function_name, function_args)
                                tool_exec.result = result
                                results.append(result)
                            except Exception as e:
                                tool_exec.exception = str(e)
                                raise
                        else:
                            try:
                                result = self._execute_tool(
                                    function_name, function_args)
                                tool_exec.result = result
                                results.append(result)
                            except Exception as e:
                                tool_exec.exception = str(e)
                                raise

                    if run_info:
                        run_info.tool_executions.append(tool_exec)
                else:
                    logger.warning("Tool '%s' not found in available tools.", function_name)

        # Si estamos en modo WAIT_RESPONSE y async_execution=True, ejecutamos todas las corrutinas
        # de manera síncrona para esperar los resultados
        if execution_mode == self.WAIT_RESPONSE and self.async_execution and results:
            try:
                # Usamos el event loop existente o creamos uno nuevo si es necesario
                try:
                    loop = asyncio.get_event_loop()
                except RuntimeError:
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)

                # Ejecutamos todas las corrutinas y esperamos los resultados
                if loop.is_running():
                    # Si el loop ya está corriendo, usamos asyncio.gather con ensure_future
                    futures = [asyncio.ensure_future(
                        result) for result in results]
                    results = loop.run_until_complete(asyncio.gather(*futures))
                else:
                    # Si el loop no está corriendo, simplemente ejecutamos gather
                    results = loop.run_until_complete(asyncio.gather(*results))
            except Exception:
                logger.exception("Error al ejecutar corrutinas de manera asíncrona")

        # Si estamos en modo EXECUTION_ONLY y async_execution=True, esperamos a que terminen las ejecuciones
        if execution_mode == self.EXECUTION_ONLY and self.async_execution and futures:
            try:
                try:
                    loop = asyncio.get_event_loop()
                except RuntimeError:
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)

                if loop.is_running():
                    futures = [asyncio.ensure_future(
                        future) for future in futures]
                    loop.run_until_complete(asyncio.gather(*futures))
                else:
                    loop.run_until_complete(asyncio.gather(*futures))
            except Exception as e:
                logger.exception("Error al ejecutar corrutinas en modo EXECUTION_ONLY")

        if execution_mode == self.EXECUTION_ONLY:
            return "Todas las funciones se han ejecutado en segundo plano."
        elif execution_mode == self.GET_ARGS:
            return results
        else:  # WAIT_RESPONSE
            return results[0] if len(results) == 1 else results

    def _execute_tool(self, tool_name: str, arguments: Dict[str, Any]):
        """Execute a tool with the given arguments."""
        tool_func = self.get_tool_by_name(tool_name)

        if tool_func is None:
            raise ValueError(f"Tool not found: {tool_name}")
        if self.async_execution:
            loop = asyncio.get_event_loop()
            return loop.run_in_executor(None, lambda tf, args: (next(iter(tf.values())) if isinstance(tf, dict) else tf)(**args), tool_func, arguments)
        else:
            tool_func = next(iter(tool_func.values())) if isinstance(tool_func, dict) else tool_func
            return tool_func(**arguments)

    def _handle_streaming_response(self, adapter_params: AdapterParams, execution_mode: str, return_full_response: bool, run_info: RunInfo, start_time: float, think_loud: bool = False):
        """Handle streaming responses from the language model."""
        from instantneo.models.standard import StandardStreamChunk

        # Create LLMCall to populate progressively
        llm_call = LLMCall(
            messages_sent=adapter_params.messages,
        )
        run_info.llm_calls.append(llm_call)

        stream = self.adapter.create_streaming_chat_completion(
            **adapter_params.to_dict())
        full_response = ""
        accumulated_reasoning = ""
        tool_calls = []

        for chunk in stream:
            try:
                # Handle StandardStreamChunk objects from new adapter architecture
                if isinstance(chunk, StandardStreamChunk):
                    chunk_delta = chunk.delta

                    # Handle reasoning delta
                    if chunk_delta.reasoning:
                        accumulated_reasoning += chunk_delta.reasoning
                        if think_loud and execution_mode == self.WAIT_RESPONSE:
                            yield {"type": "reasoning", "content": chunk_delta.reasoning}

                    # Handle content delta
                    if chunk_delta.content:
                        full_response += chunk_delta.content
                        if execution_mode == self.WAIT_RESPONSE:
                            if think_loud:
                                yield {"type": "text", "content": chunk_delta.content}
                            else:
                                yield chunk_delta.content

                    # Handle tool calls
                    if chunk_delta.tool_calls:
                        tool_calls.extend(chunk_delta.tool_calls)

                    # Capture usage
                    if chunk.usage:
                        llm_call.usage = {
                            "input_tokens": chunk.usage.input_tokens,
                            "output_tokens": chunk.usage.output_tokens,
                            "total_tokens": chunk.usage.total_tokens,
                            "reasoning_tokens": getattr(chunk.usage, "reasoning_tokens", None),
                        }
                        run_info.usage = llm_call.usage

                    if chunk_delta.finish_reason == 'stop':
                        break

                    continue

                # Legacy handling for string/dict chunks
                if isinstance(chunk, int):
                    chunk = str(chunk)

                if isinstance(chunk, str):
                    chunk_data = json.loads(chunk)
                else:
                    chunk_data = chunk

                if isinstance(chunk_data, dict) and 'choices' in chunk_data and chunk_data['choices']:
                    delta = chunk_data['choices'][0].get('delta', {})
                    content = delta.get('content')

                    if content:
                        full_response += content
                        if execution_mode == self.WAIT_RESPONSE:
                            if think_loud:
                                yield {"type": "text", "content": content}
                            else:
                                yield content

                    if 'tool_calls' in delta:
                        tool_calls.extend(delta['tool_calls'])

                    if delta.get('finish_reason') == 'stop':
                        break

                    # Capture usage from final chunk if present
                    if 'usage' in chunk_data and chunk_data['usage']:
                        usage_data = chunk_data['usage']
                        completion_details = usage_data.get('completion_tokens_details') or {}
                        output_details     = usage_data.get('output_tokens_details') or {}
                        llm_call.usage = {
                            "input_tokens": usage_data.get('prompt_tokens', usage_data.get('input_tokens', 0)),
                            "output_tokens": usage_data.get('completion_tokens', usage_data.get('output_tokens', 0)),
                            "total_tokens": usage_data.get('total_tokens', 0),
                            "reasoning_tokens": completion_details.get('reasoning_tokens') or output_details.get('reasoning_tokens'),
                        }
                        run_info.usage = llm_call.usage
                else:
                    full_response += str(chunk_data)
                    if execution_mode == self.WAIT_RESPONSE:
                        if think_loud:
                            yield {"type": "text", "content": str(chunk_data)}
                        else:
                            yield str(chunk_data)

            except json.JSONDecodeError:
                full_response += str(chunk)
                if execution_mode == self.WAIT_RESPONSE:
                    if think_loud:
                        yield {"type": "text", "content": str(chunk)}
                    else:
                        yield str(chunk)
            except Exception as e:
                run_info.error = str(e)
                logger.exception("Error inesperado durante el streaming")

        # Store accumulated reasoning in run_info
        llm_call.reasoning_content = accumulated_reasoning if accumulated_reasoning else None
        run_info.reasoning = llm_call.reasoning_content

        # Update LLMCall with final data
        llm_call.response_content = full_response
        llm_call.finish_reason = "tool_calls" if tool_calls else "stop"
        if tool_calls:
            llm_call.tool_calls_requested = [
                {"name": tc.function.name, "arguments": tc.function.arguments}
                for tc in tool_calls
                if hasattr(tc, 'function')
            ]
        run_info.response_content = full_response
        run_info.finish_reason = llm_call.finish_reason

        # Procesamos las herramientas según el modo de ejecución
        if tool_calls:
            if execution_mode == self.EXECUTION_ONLY:
                futures = []
                for tool_call in tool_calls:
                    function_name = tool_call.function.name
                    function_args = json.loads(tool_call.function.arguments)
                    tool_exec = ToolExecution(
                        name=function_name,
                        arguments=function_args,
                        execution_mode=execution_mode,
                    )
                    try:
                        result = self._execute_tool(function_name, function_args)
                        tool_exec.result = result
                    except Exception as e:
                        tool_exec.exception = str(e)
                    run_info.tool_executions.append(tool_exec)
                    if self.async_execution:
                        futures.append(result)

                # Si hay futures pendientes y estamos en modo async, esperamos a que terminen
                if self.async_execution and futures:
                    try:
                        try:
                            loop = asyncio.get_event_loop()
                        except RuntimeError:
                            loop = asyncio.new_event_loop()
                            asyncio.set_event_loop(loop)

                        if loop.is_running():
                            futures = [asyncio.ensure_future(
                                future) for future in futures]
                            loop.run_until_complete(asyncio.gather(*futures))
                        else:
                            loop.run_until_complete(asyncio.gather(*futures))
                    except Exception as e:
                        logger.exception("Error al ejecutar corrutinas en streaming")

                yield {
                    "text": full_response if full_response else None,
                    "tool_results": "Todas las funciones se han ejecutado en segundo plano."
                }
            elif execution_mode == self.GET_ARGS:
                for tool_call in tool_calls:
                    if hasattr(tool_call, 'function'):
                        tool_exec = ToolExecution(
                            name=tool_call.function.name,
                            arguments=json.loads(tool_call.function.arguments) if isinstance(tool_call.function.arguments, str) else tool_call.function.arguments,
                            execution_mode=execution_mode,
                            result={"name": tool_call.function.name, "arguments": tool_call.function.arguments},
                        )
                        run_info.tool_executions.append(tool_exec)
                yield {
                    "text": full_response if full_response else None,
                    "tool_results": tool_calls
                }
            elif execution_mode == self.WAIT_RESPONSE and tool_calls:
                # Para WAIT_RESPONSE, ejecutamos las herramientas y devolvemos los resultados
                results = []
                futures = []

                for tool_call in tool_calls:
                    if hasattr(tool_call, 'function'):
                        function_name = tool_call.function.name
                        function_args = json.loads(
                            tool_call.function.arguments)

                        tool_exec = ToolExecution(
                            name=function_name,
                            arguments=function_args,
                            execution_mode=execution_mode,
                        )

                        if function_name in self.get_tool_names():
                            if self.async_execution:
                                try:
                                    result = self._execute_tool(
                                        function_name, function_args)
                                    tool_exec.result = result
                                    futures.append(result)
                                except Exception as e:
                                    tool_exec.exception = str(e)
                            else:
                                try:
                                    result = self._execute_tool(
                                        function_name, function_args)
                                    tool_exec.result = result
                                    results.append(result)
                                except Exception as e:
                                    tool_exec.exception = str(e)
                        else:
                            logger.warning("Tool '%s' not found in available tools.", function_name)

                        run_info.tool_executions.append(tool_exec)


                # Si hay futures pendientes, esperamos a que terminen
                if self.async_execution and futures:
                    try:
                        try:
                            loop = asyncio.get_event_loop()
                        except RuntimeError:
                            loop = asyncio.new_event_loop()
                            asyncio.set_event_loop(loop)

                        if loop.is_running():
                            futures = [asyncio.ensure_future(
                                future) for future in futures]
                            results = loop.run_until_complete(
                                asyncio.gather(*futures))
                        else:
                            results = loop.run_until_complete(
                                asyncio.gather(*futures))
                    except Exception as e:
                        logger.exception("Error al ejecutar corrutinas en streaming con WAIT_RESPONSE")


                # Devolvemos los resultados
                if results:
                    tool_results = results[0] if len(results) == 1 else results
                    yield {
                        "text": full_response if full_response else None,
                        "tool_results": tool_results
                    }

        if return_full_response:
            yield {
                "content": full_response,
                "tool_calls": tool_calls
            }

        # Finalize timing
        run_info.duration_ms = (time.perf_counter() - start_time) * 1000

    def _handle_normal_response(self, adapter_params: AdapterParams, execution_mode: str, return_full_response: bool, run_info: RunInfo, think_loud: bool = False):
        """Handle normal (non-streaming) responses from the language model."""
        response = self.adapter.create_chat_completion(
            **adapter_params.to_dict())

        # Capture LLM call metadata
        llm_call = LLMCall(
            messages_sent=adapter_params.messages,
            raw_response=response,
        )

        if hasattr(response, 'choices') and response.choices:
            choice = response.choices[0]
            llm_call.response_content = choice.message.content if hasattr(choice, 'message') and choice.message else None
            llm_call.finish_reason = response.finish_reason if hasattr(response, 'finish_reason') else None

            # Capture reasoning content
            if hasattr(choice, 'message') and choice.message:
                llm_call.reasoning_content = getattr(choice.message, 'reasoning', None)

            # Capture tool calls requested
            if hasattr(choice, 'message') and choice.message and hasattr(choice.message, 'tool_calls') and choice.message.tool_calls:
                llm_call.tool_calls_requested = [
                    {"name": tc.function.name, "arguments": tc.function.arguments}
                    for tc in choice.message.tool_calls
                    if hasattr(tc, 'function')
                ]

        if hasattr(response, 'usage') and response.usage:
            usage = response.usage
            llm_call.usage = {
                "input_tokens": usage.input_tokens if hasattr(usage, 'input_tokens') else 0,
                "output_tokens": usage.output_tokens if hasattr(usage, 'output_tokens') else 0,
                "total_tokens": usage.total_tokens if hasattr(usage, 'total_tokens') else 0,
                "reasoning_tokens": getattr(usage, "reasoning_tokens", None),
            }
            run_info.usage = llm_call.usage

        if hasattr(response, 'id'):
            llm_call.response_id = response.id
        if hasattr(response, 'model'):
            llm_call.response_model = response.model

        run_info.llm_calls.append(llm_call)
        run_info.reasoning = llm_call.reasoning_content
        run_info.provider_timing = self._extract_provider_timing(response)

        if return_full_response:
            run_info.response_content = llm_call.response_content
            run_info.finish_reason = llm_call.finish_reason
            return response
        else:
            result = self._process_response(response, execution_mode, run_info, think_loud)
            run_info.response_content = llm_call.response_content
            run_info.finish_reason = llm_call.finish_reason
            return result

    def _extract_provider_timing(self, response) -> Optional[Dict]:
        """Extract provider-specific timing from the raw response.

        Supports:
        - Cerebras: time_info with queue_time, prompt_time, completion_time, total_time
        - Groq: usage.prompt_time, usage.completion_time, usage.total_time
        """
        timing = {}

        # Cerebras: response has time_info attribute
        raw = response.raw_response if hasattr(response, 'raw_response') and response.raw_response else response
        if hasattr(raw, 'time_info') and raw.time_info:
            ti = raw.time_info
            if hasattr(ti, 'queue_time'):
                timing['queue_time'] = ti.queue_time
            if hasattr(ti, 'prompt_time'):
                timing['prompt_time'] = ti.prompt_time
            if hasattr(ti, 'completion_time'):
                timing['completion_time'] = ti.completion_time
            if hasattr(ti, 'total_time'):
                timing['total_time'] = ti.total_time

        # Groq: usage has prompt_time, completion_time, total_time
        usage = raw.usage if hasattr(raw, 'usage') and raw.usage else None
        if usage:
            if hasattr(usage, 'prompt_time') and usage.prompt_time is not None:
                timing['prompt_time'] = usage.prompt_time
            if hasattr(usage, 'completion_time') and usage.completion_time is not None:
                timing['completion_time'] = usage.completion_time
            if hasattr(usage, 'total_time') and usage.total_time is not None:
                timing['total_time'] = usage.total_time

        return timing if timing else None

    def _create_adapter(self):
        """Create an adapter based on the provider."""
        adapter_map = {
            "openai": ("instantneo.adapters.openai_adapter", "OpenAIAdapter"),
            "anthropic": ("instantneo.adapters.anthropic_adapter", "AnthropicAdapter"),
            "groq": ("instantneo.adapters.groq_adapter", "GroqAdapter"),
            "deepseek": ("instantneo.adapters.deepseek_adapter", "DeepSeekAdapter"),
            "mistral": ("instantneo.adapters.mistral_adapter", "MistralAdapter"),
            "qwen": ("instantneo.adapters.qwen_adapter", "QwenAdapter"),
            "kimi": ("instantneo.adapters.kimi_adapter", "KimiAdapter"),
            "moonshot": ("instantneo.adapters.kimi_adapter", "KimiAdapter"),
            "zhipu": ("instantneo.adapters.zhipu_adapter", "ZhipuAdapter"),
            "glm": ("instantneo.adapters.zhipu_adapter", "ZhipuAdapter"),
            "mimo": ("instantneo.adapters.mimo_adapter", "MiMoAdapter"),
            "xiaomi_mimo": ("instantneo.adapters.mimo_adapter", "MiMoAdapter"),
            "cerebras": ("instantneo.adapters.cerebras_adapter", "CerebrasAdapter"),
            "gemini": ("instantneo.adapters.gemini_adapter", "GeminiAdapter"),
            "vertexai": ("instantneo.adapters.vertex_gemini_adapter", "VertexGeminiAdapter"),
            "vertex_anthropic": ("instantneo.adapters.vertex_anthropic_adapter", "VertexAnthropicAdapter"),
            "xai": ("instantneo.adapters.xai_adapter", "XAIAdapter"),
            "vertex_xai": ("instantneo.adapters.vertex_xai_adapter", "VertexXAIAdapter"),
        }

        if self.config.provider not in adapter_map:
            raise ValueError(f"Unsupported provider: {self.config.provider}")

        module_path, class_name = adapter_map[self.config.provider]
        module = __import__(module_path, fromlist=[class_name])
        adapter_class = getattr(module, class_name)

        # Handle different authentication methods
        if self.config.provider in ("vertexai", "vertex_anthropic", "vertex_xai"):
            if not self.config.service_account_file:
                raise ValueError("service_account_file is required for Vertex AI provider")
            if not self.config.location:
                raise ValueError("location is required for Vertex AI provider")
            return adapter_class(
                location=self.config.location,
                service_account_file=self.config.service_account_file,
            )
        else:
            # openai, anthropic, groq, gemini - todos usan api_key
            if not self.config.api_key:
                raise ValueError(f"api_key is required for {self.config.provider} provider")
            return adapter_class(api_key=self.config.api_key)
