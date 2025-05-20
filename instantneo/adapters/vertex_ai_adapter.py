import json
import time
import base64 # For image data handling
from typing import List, Dict, Any, Generator, Union, Tuple, Optional

import vertexai
from google.cloud import aiplatform # Standard import, though direct use might be minimal for this adapter
from vertexai.generative_models import (
    GenerativeModel,
    Content,
    Part,
    Tool as VertexTool, # Aliasing to avoid conflict if a generic 'Tool' type is used elsewhere
    FunctionDeclaration,
    Schema, # Used for defining tool parameters
    GenerationConfig,
    SafetySetting,
    HarmCategory,
    HarmBlockThreshold,
    ToolConfig, # For specifying tool usage mode (e.g., auto, any, none)
    FunctionCallingConfig # For specifying function calling mode
)
# Import FinishReason enum and alias it for clarity
from vertexai.generative_models import FinishReason as VertexFinishReasonEnum

from .base_adapter import BaseAdapter

class VertexAIAdapter(BaseAdapter):
    def __init__(self, project: str, location: str, api_key: Optional[str] = None): # api_key is often not directly used by vertexai.init
        super().__init__()
        # Initialize the Vertex AI SDK with project and location.
        # api_key is part of the signature for consistency but typically not passed if using ADC.
        vertexai.init(project=project, location=location)
        # No specific client instance is usually stored for GenerativeModel,
        # as it's often instantiated per call or per specific model configuration.

    def _format_vertex_finish_reason(self, finish_reason: Optional[VertexFinishReasonEnum], has_tool_calls: bool) -> str:
        """Helper to map Vertex AI finish reasons to InstantNeo standardized strings."""
        if has_tool_calls:
            return "tool_calls" # OpenAI standard for when a tool/function is called
        if finish_reason is None:
            return "stop" # Default to "stop" if no specific reason is provided
            
        # Mapping from Vertex AI's FinishReason enum
        mapping = {
            VertexFinishReasonEnum.STOP: "stop",
            VertexFinishReasonEnum.MAX_TOKENS: "length",
            VertexFinishReasonEnum.SAFETY: "safety",
            VertexFinishReasonEnum.RECITATION: "recitation",
            VertexFinishReasonEnum.OTHER: "stop", # Default 'OTHER' to 'stop'
            VertexFinishReasonEnum.UNSPECIFIED: "stop", # Treat 'UNSPECIFIED' as 'stop'
        }
        return mapping.get(finish_reason, "stop")

    def format_messages(self, messages: List[Dict[str, Any]]) -> Tuple[Optional[str], List[Content]]:
        """
        Converts InstantNeo messages to Vertex AI format.
        Returns a tuple: (system_instruction_string, list_of_history_content_objects).
        """
        system_instruction_str: Optional[str] = None
        history_content_list: List[Content] = []
        system_message_parts_texts = [] # Collects text parts for system instruction

        for message in messages:
            role = message.get("role")
            content = message.get("content")

            if role == "system":
                if isinstance(content, str):
                    system_message_parts_texts.append(content)
                elif isinstance(content, list): # Handle list of content parts for system message
                    for part_item_sys in content:
                        if isinstance(part_item_sys, dict) and part_item_sys.get("type") == "text":
                            system_message_parts_texts.append(part_item_sys.get("text", ""))
                        elif isinstance(part_item_sys, str):
                             system_message_parts_texts.append(part_item_sys)
                continue # System instructions are processed at the end.

            # Map InstantNeo roles to Vertex AI roles for chat history
            # 'assistant' maps to 'model'; 'tool' (for tool responses) maps to 'function' role in Vertex AI
            vertex_message_role = "model" if role == "assistant" else ("function" if role == "tool" else role)
            
            current_message_parts_list = []
            if isinstance(content, str):
                current_message_parts_list.append(Part.from_text(content))
            elif isinstance(content, list): # For multi-part messages (e.g., text and image)
                for part_item in content:
                    if isinstance(part_item, dict):
                        part_type = part_item.get("type")
                        if part_type == "text":
                            current_message_parts_list.append(Part.from_text(part_item.get("text", "")))
                        elif part_type == "image_url" and self.supports_images():
                            image_data_url = part_item.get("image_url", {}).get("url")
                            if image_data_url and ";base64," in image_data_url:
                                try:
                                    header, base64_encoded_data = image_data_url.split(';base64,', 1)
                                    mime_type = header.split(':', 1)[1] if ':' in header else 'application/octet-stream'
                                    image_bytes = base64.b64decode(base64_encoded_data)
                                    current_message_parts_list.append(Part.from_data(data=image_bytes, mime_type=mime_type))
                                except Exception as e:
                                    # print(f"Warning: Could not decode base64 image data URI: {e}") # Optional log
                                    pass 
                    elif isinstance(part_item, str):
                        current_message_parts_list.append(Part.from_text(part_item))
            
            # Handle tool calls *made by the assistant* in a previous message
            if role == "assistant" and message.get("tool_calls"):
                for tool_call in message.get("tool_calls", []):
                    function_name = tool_call.get("function", {}).get("name")
                    function_args_str = tool_call.get("function", {}).get("arguments", "{}")
                    try:
                        function_args = json.loads(function_args_str) # Vertex AI expects args as a dict
                    except json.JSONDecodeError:
                        function_args = {} 
                    if function_name:
                        current_message_parts_list.append(Part.from_function_call(name=function_name, args=function_args))
            
            # Handle 'tool' role message (this is a function response *from the user/client*)
            if role == "tool":
                function_name = message.get("name") 
                tool_response_content_str = message.get("content", "{}")
                try:
                    tool_response_payload = json.loads(tool_response_content_str)
                except json.JSONDecodeError:
                    tool_response_payload = {"result": tool_response_content_str} # Wrap if not JSON

                if function_name:
                    # The role for this Content object will be 'function'
                    current_message_parts_list.append(Part.from_function_response(
                        name=function_name,
                        response={"content": tool_response_payload} # Vertex expects a dict for 'response'
                    ))

            if current_message_parts_list:
                history_content_list.append(Content(role=vertex_message_role, parts=current_message_parts_list))

        if system_message_parts_texts:
            system_instruction_str = "\n".join(system_message_parts_texts)
        
        return system_instruction_str, history_content_list

    def format_tools(self, tools: List[Dict[str, Any]]) -> Optional[List[VertexTool]]:
        if not tools:
            return None
        
        vertex_function_declarations_list = []
        for tool_dict in tools:
            if tool_dict.get("type") == "function":
                func_spec = tool_dict.get("function")
                if not func_spec or not func_spec.get("name"):
                    # print("Warning: Skipping tool with missing function spec or name.") # Optional log
                    continue

                name = func_spec["name"]
                description = func_spec.get("description")
                parameters_openapi_schema = func_spec.get("parameters") # Expected to be OpenAPI schema dict

                try:
                    # Schema.from_dict can construct the schema object from a dictionary.
                    parameters_schema_obj = Schema.from_dict(parameters_openapi_schema) if parameters_openapi_schema else None
                    
                    declaration = FunctionDeclaration(
                        name=name,
                        description=description,
                        parameters_schema=parameters_schema_obj
                    )
                    vertex_function_declarations_list.append(declaration)
                except Exception as e:
                    # print(f"Warning: Could not format tool '{name}' due to schema issue: {e}") # Optional log
                    pass 
        
        if not vertex_function_declarations_list:
            return None
        return [VertexTool(function_declarations=vertex_function_declarations_list)]


    def _prepare_vertex_request_params(
        self,
        model_id_str: str, # Renamed to avoid conflict with 'model' variable later
        messages: List[Dict[str, Any]],
        tools_input_list: Optional[List[Dict[str, Any]]] = None, # Renamed for clarity
        tool_choice_config: Optional[Union[str, Dict]] = None, # Renamed for clarity
        temperature_val: Optional[float] = None,
        top_p_val: Optional[float] = None,
        top_k_val: Optional[int] = None,
        max_output_tokens_val: Optional[int] = None,
        stop_sequences_list: Optional[List[str]] = None,
        safety_settings_list_input: Optional[List[Dict[str, Any]]] = None, # Renamed
        **kwargs # Catch-all for other potential passthrough arguments
    ) -> Dict[str, Any]:
        
        system_instruction_str, history_contents_list = self.format_messages(messages)
        
        gen_config_dict_params = {} # For GenerationConfig object
        if temperature_val is not None: gen_config_dict_params["temperature"] = temperature_val
        if top_p_val is not None: gen_config_dict_params["top_p"] = top_p_val
        if top_k_val is not None: gen_config_dict_params["top_k"] = int(top_k_val) # Vertex top_k must be int
        if max_output_tokens_val is not None: gen_config_dict_params["max_output_tokens"] = max_output_tokens_val
        if stop_sequences_list: gen_config_dict_params["stop_sequences"] = stop_sequences_list
        
        generation_config_obj = GenerationConfig.from_dict(gen_config_dict_params) if gen_config_dict_params else None

        vertex_tool_config_obj: Optional[ToolConfig] = None # For ToolConfig object
        if tool_choice_config:
            mode_map = { 
                "auto": FunctionCallingConfig.Mode.AUTO,
                "any": FunctionCallingConfig.Mode.ANY,
                "none": FunctionCallingConfig.Mode.NONE,
            }
            if isinstance(tool_choice_config, str) and tool_choice_config in mode_map:
                vertex_tool_config_obj = ToolConfig(
                    function_calling_config=FunctionCallingConfig(mode=mode_map[tool_choice_config])
                )
            elif isinstance(tool_choice_config, dict) and tool_choice_config.get("type") == "function":
                func_name = tool_choice_config.get("function", {}).get("name")
                if func_name: # To force a specific function
                    vertex_tool_config_obj = ToolConfig(
                        function_calling_config=FunctionCallingConfig(
                            mode=FunctionCallingConfig.Mode.ANY, 
                            allowed_function_names=[func_name]
                        )
                    )
        
        final_safety_settings_list: Optional[List[SafetySetting]] = None # For SafetySetting objects
        if safety_settings_list_input:
            final_safety_settings_list = []
            for setting_dict in safety_settings_list_input:
                try:
                    category_enum = HarmCategory[setting_dict["category"].upper()]
                    threshold_enum = HarmBlockThreshold[setting_dict["threshold"].upper()]
                    final_safety_settings_list.append(SafetySetting(category=category_enum, threshold=threshold_enum))
                except (KeyError, AttributeError) as e:
                    # print(f"Warning: Invalid safety setting format: {setting_dict}. Error: {e}") # Optional log
                    pass
        
        formatted_tools_list_obj = self.format_tools(tools_input_list) # List of VertexTool objects

        # Consolidate all parameters for the model and generation steps
        return {
            "model_id_str": model_id_str,
            "system_instruction_str": system_instruction_str,
            "history_contents_list": history_contents_list,
            "generation_config_obj": generation_config_obj,
            "final_safety_settings_list": final_safety_settings_list,
            "formatted_tools_list_obj": formatted_tools_list_obj,
            "vertex_tool_config_obj": vertex_tool_config_obj,
            "remaining_kwargs": kwargs # Pass through any other kwargs not explicitly handled
        }

    def create_chat_completion(self, model: str, messages: List[Dict[str, Any]], **kwargs) -> Dict[str, Any]:
        # Pop specific kwargs for _prepare_vertex_request_params; others are passed via its **kwargs
        prep_kwargs = {
            "tools_input_list": kwargs.pop("tools", None),
            "tool_choice_config": kwargs.pop("tool_choice", None),
            "temperature_val": kwargs.pop("temperature", None),
            "top_p_val": kwargs.pop("top_p", None),
            "top_k_val": kwargs.pop("top_k", None),
            "max_output_tokens_val": kwargs.pop("max_tokens", kwargs.pop("max_output_tokens", None)), # Alias support
            "stop_sequences_list": kwargs.pop("stop", kwargs.pop("stop_sequences", None)), # Alias support
            "safety_settings_list_input": kwargs.pop("safety_settings", None),
        }
        prep_kwargs = {k: v for k, v in prep_kwargs.items() if v is not None} # Filter out Nones
        
        request_params = self._prepare_vertex_request_params(model, messages, **prep_kwargs, **kwargs)
        
        try:
            vertex_model_instance = GenerativeModel(
                model_name=request_params["model_id_str"],
                system_instruction=request_params["system_instruction_str"],
                tools=request_params["formatted_tools_list_obj"],
                safety_settings=request_params["final_safety_settings_list"]
            )
            
            response = vertex_model_instance.generate_content(
                contents=request_params["history_contents_list"],
                generation_config=request_params["generation_config_obj"],
                tool_config=request_params.get("vertex_tool_config_obj"), # Optional
                **(request_params.get("remaining_kwargs", {})) # Pass other valid generate_content params
            )

        except Exception as e:
            raise RuntimeError(f"Vertex AI API error in create_chat_completion: {e}")

        # Process the response
        if hasattr(response, 'prompt_feedback') and response.prompt_feedback and response.prompt_feedback.block_reason:
            raise RuntimeError(f"Content generation blocked by Vertex AI (prompt). Reason: {response.prompt_feedback.block_reason}. Msg: {getattr(response.prompt_feedback, 'block_reason_message', 'N/A')}")

        output_choices_list = []
        prompt_tokens_count = response.usage_metadata.prompt_token_count if response.usage_metadata else 0
        candidates_tokens_count = response.usage_metadata.candidates_token_count if response.usage_metadata else 0
        
        for i, candidate in enumerate(response.candidates):
            text_content_accumulated = ""
            tool_calls_data_list = []
            has_function_calls_in_candidate = False

            if candidate.content and candidate.content.parts:
                for part_idx, part_instance in enumerate(candidate.content.parts):
                    if part_instance.function_call:
                        has_function_calls_in_candidate = True
                        tool_calls_data_list.append({
                            "id": f"call_vertex_{i}_{part_idx}_{part_instance.function_call.name}",
                            "type": "function",
                            "function": {
                                "name": part_instance.function_call.name,
                                "arguments": json.dumps(dict(part_instance.function_call.args)) if part_instance.function_call.args else "{}"
                            }
                        })
                    if part_instance.text:
                        text_content_accumulated += part_instance.text
            
            message_content_final = None if has_function_calls_in_candidate and not text_content_accumulated.strip() else text_content_accumulated
            
            candidate_finish_reason_enum_val = getattr(candidate, 'finish_reason', None)
            current_choice_finish_reason_str = self._format_vertex_finish_reason(candidate_finish_reason_enum_val, has_function_calls_in_candidate)

            choice_entry_dict = {
                "index": i,
                "message": { "role": "assistant", "content": message_content_final },
                "finish_reason": current_choice_finish_reason_str
            }
            if tool_calls_data_list:
                choice_entry_dict["message"]["tool_calls"] = tool_calls_data_list
            
            if candidate_finish_reason_enum_val == VertexFinishReasonEnum.SAFETY:
                safety_ratings_data_list = [] 
                for rating_instance in candidate.safety_ratings: # Iterate through safety ratings if present
                    safety_ratings_data_list.append({
                        "category": HarmCategory(rating_instance.category).name,
                        "probability": rating_instance.probability.name, 
                    })
                choice_entry_dict["safety_ratings"] = safety_ratings_data_list
            output_choices_list.append(choice_entry_dict)

        response_id_str = f"vertex-chatcmpl-{int(time.time())}-{hash(str(response.candidates))}"
        
        return {
            "id": response_id_str,
            "object": "chat.completion",
            "created": int(time.time()),
            "model": model,
            "choices": output_choices_list,
            "usage": {
                "prompt_tokens": prompt_tokens_count,
                "completion_tokens": candidates_tokens_count,
                "total_tokens": prompt_tokens_count + candidates_tokens_count,
            },
        }

    def create_streaming_chat_completion(self, model: str, messages: List[Dict[str, Any]], **kwargs) -> Generator[Dict[str, Any], None, None]:
        prep_kwargs = {
            "tools_input_list": kwargs.pop("tools", None),
            "tool_choice_config": kwargs.pop("tool_choice", None),
            "temperature_val": kwargs.pop("temperature", None),
            "top_p_val": kwargs.pop("top_p", None),
            "top_k_val": kwargs.pop("top_k", None),
            "max_output_tokens_val": kwargs.pop("max_tokens", kwargs.pop("max_output_tokens", None)),
            "stop_sequences_list": kwargs.pop("stop", kwargs.pop("stop_sequences", None)),
            "safety_settings_list_input": kwargs.pop("safety_settings", None),
        }
        prep_kwargs = {k: v for k, v in prep_kwargs.items() if v is not None}
        request_params = self._prepare_vertex_request_params(model, messages, **prep_kwargs, **kwargs)

        try:
            vertex_model_instance = GenerativeModel(
                model_name=request_params["model_id_str"],
                system_instruction=request_params["system_instruction_str"],
                tools=request_params["formatted_tools_list_obj"],
                safety_settings=request_params["final_safety_settings_list"]
            )
            
            stream_response_iter = vertex_model_instance.generate_content(
                contents=request_params["history_contents_list"],
                generation_config=request_params["generation_config_obj"],
                tool_config=request_params.get("vertex_tool_config_obj"),
                stream=True,
                **(request_params.get("remaining_kwargs", {}))
            )
        except Exception as e:
            raise RuntimeError(f"Vertex AI API error during streaming setup: {e}")

        for chunk_idx, chunk_data_item in enumerate(stream_response_iter):
            if hasattr(chunk_data_item, 'prompt_feedback') and chunk_data_item.prompt_feedback and chunk_data_item.prompt_feedback.block_reason:
                yield { 
                    "error": f"Content generation blocked by Vertex AI (prompt). Reason: {chunk_data_item.prompt_feedback.block_reason}. Message: {getattr(chunk_data_item.prompt_feedback, 'block_reason_message', 'N/A')}"
                }
                return 

            delta_text_content = ""
            tool_call_delta_chunks_list = [] 
            stream_chunk_finish_reason = None 
            
            if chunk_data_item.candidates:
                candidate_in_chunk = chunk_data_item.candidates[0]
                has_function_calls_in_stream_chunk = False

                if candidate_in_chunk.content and candidate_in_chunk.content.parts:
                    for part_idx, part_detail_item in enumerate(candidate_in_chunk.content.parts):
                        if part_detail_item.text:
                            delta_text_content += part_detail_item.text
                        if part_detail_item.function_call:
                            has_function_calls_in_stream_chunk = True
                            tool_call_delta_chunks_list.append({
                                "index": part_idx, 
                                "id": f"call_vertex_stream_{chunk_idx}_{part_idx}_{part_detail_item.function_call.name}",
                                "type": "function",
                                "function": { 
                                    "name": part_detail_item.function_call.name,
                                    "arguments": json.dumps(dict(part_detail_item.function_call.args)) if part_detail_item.function_call.args else "" 
                                }
                            })
                
                chunk_finish_reason_enum = getattr(candidate_in_chunk, 'finish_reason', None)
                if chunk_finish_reason_enum and chunk_finish_reason_enum != VertexFinishReasonEnum.UNSPECIFIED:
                    stream_chunk_finish_reason = self._format_vertex_finish_reason(chunk_finish_reason_enum, has_function_calls_in_stream_chunk)

            output_chunk_dict = {
                "id": f"chatcmpl-stream-vertex-{chunk_idx}-{int(time.time())}",
                "object": "chat.completion.chunk",
                "created": int(time.time()), "model": model,
                "choices": [{"index": 0, "delta": {}, "finish_reason": None }]
            }

            if delta_text_content:
                output_chunk_dict["choices"][0]["delta"]["content"] = delta_text_content
            
            if tool_call_delta_chunks_list:
                output_chunk_dict["choices"][0]["delta"]["tool_calls"] = tool_call_delta_chunks_list
            
            if stream_chunk_finish_reason:
                output_chunk_dict["choices"][0]["finish_reason"] = stream_chunk_finish_reason
            
            if delta_text_content or tool_call_delta_chunks_list or stream_chunk_finish_reason:
                yield output_chunk_dict
        
    def supports_images(self) -> bool:
        # Gemini models on Vertex AI generally support multimodal inputs including images.
        return True
```
