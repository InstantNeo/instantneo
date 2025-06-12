from dataclasses import dataclass, field
from typing import List, Dict, Any, Callable, Optional, Union, Generator, Type, AsyncGenerator
import asyncio
import json
import threading
from instantneo.skills import SkillManager
from instantneo.utils.image_utils import process_images
from instantneo.utils.skill_utils import format_tool
#tracker
from instantneo.tracking.session_tracker import SessionTracker



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
    api_key: str
    role_setup: str
    skills: Optional[Union[List[str], SkillManager]] = None
    images: Optional[Union[str, List[str]]] = None
    image_detail: str = "auto"


@dataclass
class RunParams(BaseParams):
    """Parameters for a specific run."""
    prompt: str
    role_setup: Optional[str] = None
    execution_mode: str = "wait_response"
    async_execution: bool = False
    return_full_response: bool = False
    skills: Optional[List[str]] = None,
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
            skills=instantneo_params.skills,
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
    such as OpenAI, Anthropic, and Groq, by providing a unified interface. It supports
    text generation, function calling (skills), and image processing, making it versatile
    for a wide range of applications.

    Args:
        provider (str): The LLM provider to use. Supported providers are:
            - "openai": OpenAI's models.
            - "anthropic": Anthropic's models.
            - "groq": Groq's models.
        api_key (str): API key for accessing the specified provider.
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
    """
    WAIT_RESPONSE = "wait_response"
    EXECUTION_ONLY = "execution_only"
    GET_ARGS = "get_args"

    def __init__(
        self,
        provider: str,
        api_key: str,
        model: str,
        role_setup: str,
        skills: Optional[Union[List[str], SkillManager]] = None,
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
        
    ):
        """Initialize an InstantNeo instance."""
        self.config = InstantNeoParams(
            provider=provider,
            api_key=api_key,
            model=model,
            role_setup=role_setup,
            skills=skills,
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
        )

        # print(f"Tipo de 'self.config.skills': {type(self.config.skills)}")

        # Initialize skill manager
        if isinstance(self.config.skills, SkillManager):
            self.skill_manager = self.config.skills
        else:
            self.skill_manager = SkillManager()
            if self.config.skills and isinstance(self.config.skills, list):
                for skill in self.config.skills:
                    self.skill_manager.register_skill(skill)

        self.adapter = self._create_adapter()
        self.tool_calls = []  # For accumulating tool calls in streaming
        self.async_execution = False  # Default value, will be set in run method
        #Tracker
        self.tracker: Optional[SessionTracker] = None

    ##################################
    #         PUBLIC METHODS         #
    ##################################

    ##### Skill Management #####
    def mod_role(self,new_role):
        self.config.role_setup = new_role
        return

    # Backward compatibility methods
    def add_skill(self, skill: Callable):
        """Deprecated. 
        Used to register a skill in the SkillManager.
        Use register_skill instead."""
        return self.register_skill(skill)

    def list_skills(self) -> List[str]:
        """Deprecated.
        Used to get the names of all registered skills.
        Use get_skill_names instead."""
        return self.get_skill_names()

    # New methods
    def register_skill(self, skill: Callable) -> None:
        """Register a skill in the SkillManager."""
        return self.skill_manager.register_skill(skill)

    def get_skill_names(self) -> List[str]:
        """Get the names of all registered skills."""
        return self.skill_manager.get_skill_names()

    def get_skill_by_name(self, name: str) -> Union[Any, Dict[str, Any], None]:
        """Get a skill by its name."""
        return self.skill_manager.get_skill_by_name(name)

    def get_skill_metadata_by_name(self, name: str) -> Dict[str, Any]:
        """Get the metadata of a skill by its name."""
        return self.skill_manager.get_skill_metadata_by_name(name)

    def get_skills_by_tag(self, tag: str, return_keys: bool = False) -> Union[List[str], Dict[str, Any]]:
        """Get skills by tag."""
        return self.skill_manager.get_skills_by_tag(tag, return_keys)

    def get_all_skills_metadata(self) -> Dict[str, Dict[str, Any]]:
        """Get the metadata of all skills."""
        return self.skill_manager.get_all_skills_metadata()

    def get_duplicate_skills(self) -> Dict[str, List[Any]]:
        """Get duplicate skills."""
        return self.skill_manager.get_duplicate_skills()

    def remove_skill(self, skill_name: str, module: Optional[str] = None) -> bool:
        """Remove a skill by its name."""
        return self.skill_manager.remove_skill(skill_name, module)

    def update_skill_metadata(self, key: str, new_metadata: Dict[str, Any]) -> bool:
        """Update the metadata of a skill."""
        return self.skill_manager.update_skill_metadata(key, new_metadata)

    def clear_registry(self) -> None:
        """Clear the skill registry."""
        return self.skill_manager.clear_registry()

    def load_skills_from_file(self, file_path: str, metadata_filter: Optional[Callable[[Dict[str, Any]], bool]] = None) -> None:
        """Load skills from a file.

        Args:
            file_path (str): The path to the file.
            metadata_filter (Optional[Callable[[Dict[str, Any]], bool]], optional): A function to filter skills by metadata. Defaults to None."""
        return self.skill_manager._load_skills_from_file(file_path, metadata_filter)

    def load_skills_from_current(self,
                                 metadata_filter: Optional[Callable[[Dict[str, Any]], bool]] = None) -> None:
        """Load skills from the current file.

        Args:
            metadata_filter (Optional[Callable[[Dict[str, Any]], bool]], optional): A function to filter skills by metadata. Defaults to None."""
        return self.skill_manager._load_skills_from_current_module(metadata_filter)
    
    def load_skills_from_folder(self, folder_path: str, metadata_filter: Optional[Callable[[Dict[str, Any]], bool]] = None) -> None:
        """Load skills from a folder.

        Args:
            folder_path (str): The path to the folder.
            metadata_filter (Optional[Callable[[Dict[str, Any]], bool]], optional): A function to filter skills by metadata. Defaults to None."""
        return self.skill_manager._load_skills_from_folder(folder_path, metadata_filter)

    

    ##### Skill Operations #####

    def sm_ops_union(self, *otros_managers) -> None:
        """
        Combines the skills of this SkillManager with other SkillManagers or InstantNeo Agents,
        replacing the internal skills with the union of both.
        """
        from instantneo.skills.skill_manager_operations import SkillManagerOperations  # Import here to avoid circular dependency
        # Inicializar con el propio SkillManager
        managers_para_union = [self.skill_manager]
        for manager_or_neo in otros_managers:
            if isinstance(manager_or_neo, InstantNeo):
                # Usar el SkillManager interno de InstantNeo
                managers_para_union.append(manager_or_neo.skill_manager)
            else:
                # Usar SkillManager directamente
                managers_para_union.append(manager_or_neo)
        self.skill_manager = SkillManagerOperations.union(*managers_para_union)

    def sm_ops_intersection(self, *otros_managers) -> None:
        """
        Performs the intersection of skills with other SkillManagers or InstantNeos,
        replacing the internal skills with the intersection of both.
        """
        from instantneo.skills.skill_manager_operations import SkillManagerOperations  # Import here to avoid circular dependency
        # Inicializar con el propio SkillManager
        managers_para_interseccion = [self.skill_manager]
        for manager_or_neo in otros_managers:
            if isinstance(manager_or_neo, InstantNeo):
                # Usar el SkillManager interno de InstantNeo
                managers_para_interseccion.append(manager_or_neo.skill_manager)
            else:
                # Usar SkillManager directamente
                managers_para_interseccion.append(manager_or_neo)
        self.skill_manager = SkillManagerOperations.intersection(
            *managers_para_interseccion)

    def sm_ops_difference(self, exclude_manager) -> None:
        """
        Calculates the difference of skills with another SkillManager or InstantNeo,
        replacing the internal skills with those that are in this agent but not in the other.
        """
        from instantneo.skills.skill_manager_operations import SkillManagerOperations  # Import here to avoid circular dependency

        if isinstance(exclude_manager, InstantNeo):
            # Usar el SkillManager interno de InstantNeo
            exclude_skill_manager = exclude_manager.skill_manager
        else:
            exclude_skill_manager = exclude_manager  # Usar SkillManager directamente

        self.skill_manager = SkillManagerOperations.difference(
            self.skill_manager, exclude_skill_manager)

    def sm_ops_symmetric_difference(self, otro_manager) -> None:
        """
        Calculates the symmetric difference of skills with another SkillManager or InstantNeo,
        replacing the internal skills with the symmetric difference of both. That is, skills that are in this agent or in the incoming one, but NOT in both.
        """
        from instantneo.skills.skill_manager_operations import SkillManagerOperations  # Import here to avoid circular dependency

        if isinstance(otro_manager, InstantNeo):
            # Usar el SkillManager interno de InstantNeo
            otro_skill_manager = otro_manager.skill_manager
        else:
            otro_skill_manager = otro_manager  # Usar SkillManager directamente

        self.skill_manager = SkillManagerOperations.symmetric_difference(
            self.skill_manager, otro_skill_manager)

    def sm_ops_compare(self, otro_manager: Union["SkillManager", "InstantNeo"]) -> Dict[str, set[str]]:
        """
        Compares the SkillManager internal with another SkillManager or InstantNeo and returns
a dictionary with common and unique skills. It does not modify the internal skills.
        """
        from instantneo.skills.skill_manager_operations import SkillManagerOperations  # Import here to avoid circular dependency
        if isinstance(otro_manager, InstantNeo):
            # Usar el SkillManager interno de InstantNeo
            otro_skill_manager = otro_manager.skill_manager
        else:
            otro_skill_manager = otro_manager  # Usar SkillManager directamente

        return SkillManagerOperations.compare(self.skill_manager, otro_skill_manager)

    #####################
    #      TRACKING     #
    #####################

    def _log_session_metadata(self, run_params: RunParams):
        """Registra en el tracker la configuración del agente y los parámetros del run."""
        if self.tracker and self.tracker.has_active_session():
            from instantneo.tracking.tracking_utils import get_config_snapshot, get_run_params_snapshot
            self.tracker._current_session["metadata"]["agent_config"] = get_config_snapshot(self)
            self.tracker._current_session["metadata"]["run_params"] = get_run_params_snapshot(run_params)

    def _log_run_result(self, prompt: str, output: Any, skills: List[str]):
        if not (self.tracker and self.tracker.has_active_session()):
            return

        log_data = {
            "input": prompt,
            "skills": skills,
            "origin": "run",
        }

        if isinstance(output, list) and all("name" in r and "result" in r and "arguments" in r for r in output):
            log_data["result_type"] = "skill_result"
            log_data["executed_skills"] = output
            log_data["output"] = output  # ✅ añadimos output obligatorio

        elif isinstance(output, dict) and "name" in output and "result" in output and "arguments" in output:
            log_data["result_type"] = "skill_result"
            log_data["executed_skills"] = [output]
            log_data["output"] = [output]  # ✅ lista para mantener consistencia

        else:
            log_data["result_type"] = "model_response"
            log_data["output"] = output

        self.tracker.log(**log_data)

    def _log_run_error(self, prompt: str, skills: List[str], exception: Exception):
        """Registra en el tracker una ejecución con error."""
        if self.tracker and self.tracker.has_active_session():
            self.tracker.log(
                input=prompt,
                output=None,
                origin="error",
                skills=skills,
                exception=str(exception)
        )
    
    #####################
    #        RUN        #
    #####################

    def run(
        self,
        prompt: str,
        execution_mode: str = "wait_response",
        async_execution: bool = False,
        return_full_response: bool = False,
        skills: Optional[List[str]] = None,
        images: Optional[Union[str, List[str]]] = None,
        image_detail: Optional[str] = None,
        stream: bool = False,
        **additional_params
    ):
        """Runs a prompt with the InstantNeo agent.

Args:
    prompt (str): The prompt to run.
    execution_mode (str, optional): The skill execution mode. Defaults to "wait_response".
        - "wait_response": Waits for the skill's response.
        - "execution_only": Executes the skill without waiting for the response.
        - "get_args": Gets the skill's name and arguments without executing it, for later use.
    async_execution (bool, optional): Asynchronous skill execution. Defaults to False.
    return_full_response (bool, optional): Returns the provider's full response. Defaults to False.
    skills (List[str], optional): The skills to use in this run; if not provided, the instance's configured skills are used.
    images (Optional[Union[str, List[str]]], optional): Images to use in this run.
    image_detail (Optional[str], optional): Detail of the images to use in this run.
    stream (bool, optional): Enable response streaming.
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

        # Determine which skills to use
        skills_to_use = skills if skills is not None else [name for name in self.get_skill_names()] 

        # print(f"Skills to be used in this run: {skills_to_use}")

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
            skills=skills_to_use,
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
            additional_params=additional_params
        )
        #Tracker
        self._log_session_metadata(run_params)
        # Add any additional parameters
        # No need to add again, already handled when creating run_params
        # for key, value in additional_params.items():
        #     run_params.additional_params[key] = value

        if run_params.execution_mode not in [self.WAIT_RESPONSE, self.EXECUTION_ONLY, self.GET_ARGS]:
            raise ValueError(
                f"Invalid execution_mode: {run_params.execution_mode}")

        self.async_execution = run_params.async_execution

        active_skills = self._get_active_skills(skills_to_use)
        #print(f"Active skills for this run: {list(active_skills.keys())}")

        image_config = self._get_image_config(run_params)

        messages = self._prepare_messages(run_params.prompt, image_config)

        adapter_params = AdapterParams.from_run_params(run_params, messages)

        if active_skills:
            formatted_tools = []
            for name, skill in active_skills.items():
                skill_info = self.get_skill_metadata_by_name(name)
                if skill_info and 'parameters' in skill_info:
                    formatted_tools.append(format_tool(skill_info))
                else:
                    print(f"Warning: Skill '{name}' is missing metadata or 'parameters'. Skipping.")

            if formatted_tools:
                adapter_params.additional_params['tools'] = formatted_tools
                if 'tool_choice' in run_params.additional_params:
                    adapter_params.additional_params['tool_choice'] = run_params.additional_params['tool_choice']

        #print("Adapter params:", json.dumps(adapter_params.to_dict(), indent=2))
        try:
            if run_params.stream:
                output = self._handle_streaming_response(adapter_params, run_params.execution_mode, run_params.return_full_response)
            else:
                output = self._handle_normal_response(adapter_params, run_params.execution_mode, run_params.return_full_response)
            # Tracker: registrar resultado final del run
            self._log_run_result(
                prompt=run_params.prompt,
                output=output,
                skills=skills_to_use
            )

            return output
        
        except Exception as e:
            # Tracker: registrar error en el run
            self._log_run_error(
                prompt=run_params.prompt,
                skills=skills_to_use,
                exception=e
            )
            raise   

    #################################
    #        PRIVATE METHODS        #
    #################################

    def _get_active_skills(self, skills: Optional[List[str]] = None) -> Dict[str, Callable]:
        """Get active skills based on the provided skill names."""
        active_skills = {}
        if skills is None:
            return active_skills

        if isinstance(skills, SkillManager):
            skills = skills.get_skill_names()

        for skill_name in skills:
            skill = self.get_skill_by_name(skill_name)
            if isinstance(skill, dict):
                skill = next(iter(skill.values()))
            if skill:
                active_skills[skill_name] = skill
            else:
                print(f"Warning: Skill '{skill_name}' not found in SkillManager.")

        return active_skills

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
                f"El proveedor actual no soporta el procesamiento de imágenes")
        return process_images(image_config.images, image_config.image_detail)

    def _prepare_messages(self, prompt: str, image_config: Optional[ImageConfig] = None) -> List[Dict[str, Any]]:
        """Prepare messages for the language model."""
        messages = []
        if self.config.role_setup:
            messages.append(
                {"role": "system", "content": self.config.role_setup})
        if image_config and image_config.images:
            content = [{"type": "text", "text": prompt}]
            content.extend(process_images(
                image_config.images, image_config.image_detail))
            messages.append({"role": "user", "content": content})
        else:
            messages.append({"role": "user", "content": prompt})
        return messages

    def _process_response(self, response, execution_mode):
        """Process the response from the language model."""
        if not hasattr(response, 'choices') or len(response.choices) == 0:
            #print("No 'choices' were found in the response")
            return None

        choice = response.choices[0]
        if not hasattr(choice, 'message'):
            #print("No 'message' attribute found in the choice")
            return None

        message = choice.message
        content = message.content if message.content else ''
        tool_calls = message.tool_calls if hasattr(
            message, 'tool_calls') else None

        if tool_calls:
            print(f'{"*" * 40}\n* {"I am using my skills. Wait for it...":^36} *\n{"*" * 40}\n')
            results = self._handle_tool_calls(tool_calls, execution_mode)
            return results
        else:
            return content

    def _handle_tool_calls(self, tool_calls, execution_mode):
        """Handle tool calls from the language model."""
        results = []
        futures = []  # Para almacenar futures en caso de ejecución asíncrona
        #print(f"DEBUG: Valor de self.async_execution en _handle_tool_calls: {self.async_execution}")

        for tool_call in tool_calls:
            if tool_call.type == 'function':
                function_name = tool_call.function.name
                function_args = json.loads(tool_call.function.arguments)
                #print(f"Llamando a la función: {function_name} con argumentos: {function_args}")

                if function_name in self.get_skill_names():
                    skill = self.get_skill_by_name(function_name)

                    if execution_mode == self.EXECUTION_ONLY:
                        result = self._execute_skill(
                            function_name, function_args)
                        if self.async_execution:
                            futures.append(result)
                        #print(f"Función {function_name} ejecutada usando EXECUTION_ONLY (async_execution={self.async_execution})")
                    elif execution_mode == self.GET_ARGS:
                        results.append(
                            {"name": function_name, "arguments": function_args})
                    else:  # WAIT_RESPONSE
                        if self.async_execution:
                            results.append(self._execute_skill(
                                function_name, function_args))
                        else:
                            result = self._execute_skill(
                                function_name, function_args)
                            results.append(result)
                else:
                    print(f"Función {function_name} no encontrada en las skills disponibles")

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

                #print(f"Resultados de ejecución asíncrona: {results}")
            except Exception as e:
                print(f"Error al ejecutar corrutinas de manera asíncrona: {e}")

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
                print(f"Error al ejecutar corrutinas en modo EXECUTION_ONLY: {e}")

        if execution_mode == self.EXECUTION_ONLY:
            return "Todas las funciones se han ejecutado en segundo plano."
        elif execution_mode == self.GET_ARGS:
            return results
        else:  # WAIT_RESPONSE
            return results[0] if len(results) == 1 else results

    def _execute_skill(self, skill_name: str, arguments: Dict[str, Any]):
        """Execute a skill with the given arguments."""
        skill = self.get_skill_by_name(skill_name)
        if skill is None:
            raise ValueError(f"Skill not found: {skill_name}")
        #print(f"DEBUG: _execute_skill llamado para {skill_name} con async_execution={self.async_execution}")
        skill_func = next(iter(skill.values())) if isinstance(skill, dict) else skill
        print(f"DEBUG: _execute_skill llamado para {skill_name} con async_execution={self.async_execution}")
        print(f"DEBUG: ----> skill_func ------> {skill_func}")
        if self.async_execution:
            #print(f"ASYNC_EXECUTION: Preparando {skill_name} para ejecución asíncrona")
            # Solo preparamos la función para ejecución asíncrona, no la ejecutamos todavía
            loop = asyncio.get_event_loop()
            return loop.run_in_executor(None, self._run_and_track_skill_return_payload, skill_name, skill_func, arguments)
        else:
            return self._run_and_track_skill_return_payload(skill_name, skill_func, arguments)
    
    def _run_and_track_skill_return_payload(self, skill_name, skill_func, arguments):
        try:
            result = skill_func(**arguments)
            return {
                "name": skill_name,
                "arguments": arguments,
                "result": result
            }
        except Exception as e:
            return {
                "name": skill_name,
                "arguments": arguments,
                "exception": str(e)
            }

    def _handle_streaming_response(self, adapter_params: AdapterParams, execution_mode: str, return_full_response: bool):
        """Handle streaming responses from the language model."""
        #print(f"DEBUG: Valor de self.async_execution en _handle_streaming_response: {self.async_execution}")
        stream = self.adapter.create_streaming_chat_completion(
            **adapter_params.to_dict())
        full_response = ""
        tool_calls = []

        for chunk in stream:
            try:
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
                            yield content

                    if 'tool_calls' in delta:
                        tool_calls.extend(delta['tool_calls'])

                    if delta.get('finish_reason') == 'stop':
                        break
                else:
                    full_response += str(chunk_data)
                    if execution_mode == self.WAIT_RESPONSE:
                        yield str(chunk_data)

            except json.JSONDecodeError:
                full_response += str(chunk)
                if execution_mode == self.WAIT_RESPONSE:
                    yield str(chunk)
            except Exception as e:
                print(f"Error inesperado: {e}")

        # Procesamos las herramientas según el modo de ejecución
        if tool_calls:
            if execution_mode == self.EXECUTION_ONLY:
                #print(f"DEBUG: En streaming, usando _execute_skill con async_execution={self.async_execution}")
                futures = []
                for tool_call in tool_calls:
                    result = self._execute_skill(
                        tool_call.function.name, json.loads(tool_call.function.arguments))
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
                        print(f"Error al ejecutar corrutinas en streaming: {e}")

                yield "Todas las funciones se han ejecutado en segundo plano."
            elif execution_mode == self.GET_ARGS:
                yield tool_calls
            elif execution_mode == self.WAIT_RESPONSE and tool_calls:
                # Para WAIT_RESPONSE, ejecutamos las herramientas y devolvemos los resultados
                #print(f"DEBUG: En streaming, procesando herramientas en modo WAIT_RESPONSE con async_execution={self.async_execution}")
                results = []
                futures = []

                for tool_call in tool_calls:
                    if hasattr(tool_call, 'function'):
                        function_name = tool_call.function.name
                        function_args = json.loads(
                            tool_call.function.arguments)

                        if function_name in self.get_skill_names():
                            if self.async_execution:
                                result = self._execute_skill(
                                    function_name, function_args)
                                futures.append(result)
                            else:
                                result = self._execute_skill(
                                    function_name, function_args)
                                results.append(result)
                        else:
                            print(f"Función {function_name} no encontrada en las skills disponibles")


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

                        #print(f"Resultados de ejecución asíncrona en streaming: {results}")
                    except Exception as e:
                        print(f"Error al ejecutar corrutinas en streaming con WAIT_RESPONSE: {e}")
                        

                # Devolvemos los resultados
                if results:
                    yield results[0] if len(results) == 1 else results

        if return_full_response:
            # --- TRACKER LOG ---
            if self.tracker and self.tracker.has_active_session():
                # Último mensaje de usuario, normalmente el prompt original
                prompt_input = adapter_params.messages[-1]["content"]
                self.tracker.log(
                    input=prompt_input,
                    output=full_response,
                    origin="model",
                    skills=[],  # skills ya fueron trackeadas por separado
                    exception=None
                )
            yield {
                "content": full_response,
                "tool_calls": tool_calls
            }

    def _handle_normal_response(self, adapter_params: AdapterParams, execution_mode: str, return_full_response: bool):
        """Handle normal (non-streaming) responses from the language model."""
        response = self.adapter.create_chat_completion(
            **adapter_params.to_dict())
        if return_full_response:
            return response
        else:
            return self._process_response(response, execution_mode)

    def _create_adapter(self):
        """Create an adapter based on the provider."""
        adapter_map = {
            "openai": ("instantneo.adapters.openai_adapter", "OpenAIAdapter"),
            "anthropic": ("instantneo.adapters.anthropic_adapter", "AnthropicAdapter"),
            "groq": ("instantneo.adapters.groq_adapter", "GroqAdapter"),
            "gemini": ("instantneo.adapters.gemini_adapter", "GeminiAdapter"),  # Nuevo

        }

        if self.config.provider not in adapter_map:
            raise ValueError(f"Unsupported provider: {self.config.provider}")

        module_path, class_name = adapter_map[self.config.provider]
        module = __import__(module_path, fromlist=[class_name])
        adapter_class = getattr(module, class_name)

        return adapter_class(self.config.api_key)
