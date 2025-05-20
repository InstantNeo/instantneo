import json
from typing import List, Dict, Any, Generator, Union, Tuple, Optional

import google.generativeai as genai
import google.generativeai.types as genai_types
from google.generativeai.types import GenerationConfig, SafetySetting, HarmCategory, HarmBlockThreshold, FunctionDeclaration, Tool

from .base_adapter import BaseAdapter

class GeminiAPIAdapter(BaseAdapter):
    def __init__(self, api_key: str):
        super().__init__()
        genai.configure(api_key=api_key)

    def _format_gemini_finish_reason(self, finish_reason: genai_types.FinishReason, has_tool_calls: bool) -> str:
        if has_tool_calls:
            return "tool_calls"
        
        mapping = {
            genai_types.FinishReason.STOP: "stop",
            genai_types.FinishReason.MAX_TOKENS: "length",
            genai_types.FinishReason.SAFETY: "safety",
            genai_types.FinishReason.RECITATION: "recitation",
            genai_types.FinishReason.OTHER: "stop",  # Defaulting OTHER to 'stop'
        }
        return mapping.get(finish_reason, "stop")

    def format_messages(self, messages: List[Dict[str, Any]]) -> Tuple[Optional[str], List[Dict[str, Any]]]:
        system_instruction = None
        formatted_messages = []
        system_parts = []

        for message in messages:
            role = message.get("role")
            content = message.get("content")

            if role == "system":
                if isinstance(content, str):
                    system_parts.append(content)
                elif isinstance(content, list): # Handle list of content parts for system (though unusual)
                    for part in content:
                        if isinstance(part, dict) and part.get("type") == "text":
                            system_parts.append(part.get("text",""))
                        elif isinstance(part, str): # if part is just a string
                             system_parts.append(part)
                continue

            gemini_role = "model" if role == "assistant" else role
            
            if isinstance(content, str):
                formatted_messages.append({"role": gemini_role, "parts": [{"text": content}]})
            elif isinstance(content, list):
                parts_list = []
                for part_item in content:
                    if isinstance(part_item, dict):
                        if part_item.get("type") == "text":
                            parts_list.append({"text": part_item.get("text")})
                        elif part_item.get("type") == "image_url":
                            # Assuming image_url is a dict like {'url': 'data:image/...;base64,...'}
                            # Gemini needs raw image data. This part needs careful implementation
                            # of how image data is passed and processed.
                            # For now, placeholder for image handling.
                            # parts_list.append({"inline_data": {"mime_type": "image/jpeg", "data": "..."}})
                            pass # Placeholder, requires image data processing
                    elif isinstance(part_item, str): # if part is just a string
                        parts_list.append({"text": part_item})
                if parts_list:
                    formatted_messages.append({"role": gemini_role, "parts": parts_list})
            
            # Handle tool calls from previous assistant message
            if role == "assistant" and message.get("tool_calls"):
                for tool_call in message.get("tool_calls", []):
                    function_name = tool_call.get("function", {}).get("name")
                    function_args_str = tool_call.get("function", {}).get("arguments", "{}")
                    try:
                        function_args = json.loads(function_args_str)
                    except json.JSONDecodeError:
                        function_args = {}
                    
                    # This is adding a function *call* to the history, which Gemini expects as a function *response*
                    # The format should be:
                    # {'role': 'tool', 'parts': [{'function_response': {'name': '...', 'response': {'content': '...'}}}]}
                    # This part needs to be corrected if we are to pass prior tool execution results to the model.
                    # For now, assuming 'tool_calls' in input are for display and not re-execution by Gemini in this turn.
                    # If they *are* for re-execution, the format needs to be:
                    # formatted_messages.append({
                    #     "role": "function", # or "tool" based on Gemini's expectation for responses
                    #     "parts": [genai_types.Part(function_response=genai_types.FunctionResponse(name=..., response=...))]
                    # })
                    pass # Placeholder for handling tool call history

        if system_parts:
            system_instruction = "\n".join(system_parts)
        
        return system_instruction, formatted_messages

    def format_tools(self, tools: List[Dict[str, Any]]) -> Optional[List[FunctionDeclaration]]:
        if not tools:
            return None
        
        gemini_tools = []
        for tool_dict in tools:
            if tool_dict.get("type") == "function":
                func_spec = tool_dict.get("function")
                if not func_spec: continue

                name = func_spec.get("name")
                description = func_spec.get("description")
                parameters_dict = func_spec.get("parameters")

                if not name: continue

                gemini_tools.append(
                    FunctionDeclaration(
                        name=name,
                        description=description,
                        parameters=parameters_dict # Assuming parameters_dict is already in OpenAPI schema format
                    )
                )
        return [Tool(function_declarations=gemini_tools)] if gemini_tools else None


    def _prepare_gemini_request_params(
        self,
        model: str,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]] = None,
        tool_choice: Optional[Union[str, Dict]] = None, # Added tool_choice
        temperature: Optional[float] = None,
        top_p: Optional[float] = None,
        top_k: Optional[int] = None,
        max_output_tokens: Optional[int] = None,
        stop_sequences: Optional[List[str]] = None,
        safety_settings: Optional[List[Dict[str, Any]]] = None,
        **kwargs 
    ) -> Dict[str, Any]:
        
        system_instruction, formatted_messages = self.format_messages(messages)
        
        generation_config = {}
        if temperature is not None:
            generation_config["temperature"] = temperature
        if top_p is not None:
            generation_config["top_p"] = top_p
        if top_k is not None:
            generation_config["top_k"] = top_k
        if max_output_tokens is not None:
            generation_config["max_output_tokens"] = max_output_tokens
        if stop_sequences is not None:
            generation_config["stop_sequences"] = stop_sequences
        
        # tool_config for Gemini
        gemini_tool_config = None
        if tool_choice:
            if isinstance(tool_choice, str) and tool_choice == "auto":
                gemini_tool_config = {"function_calling_config": {"mode": "auto"}}
            elif isinstance(tool_choice, str) and tool_choice == "any": # Gemini's "ANY"
                 gemini_tool_config = {"function_calling_config": {"mode": "any"}}
            elif isinstance(tool_choice, str) and tool_choice == "none": # Gemini's "NONE"
                 gemini_tool_config = {"function_calling_config": {"mode": "none"}}
            elif isinstance(tool_choice, dict) and tool_choice.get("type") == "function" and tool_choice.get("function",{}).get("name"):
                gemini_tool_config = {
                    "function_calling_config": {
                        "mode": "any", # Or "AUTO"? For specific function, Gemini implies ANY and then model decides.
                                         # If we want to force a specific function, this needs more thought.
                                         # The API seems to imply that the *model* chooses from the provided list.
                                         # Forcing a specific function might be done by only providing that one function.
                        "allowed_function_names": [tool_choice["function"]["name"]]
                    }
                }

        formatted_safety_settings = None
        if safety_settings:
            formatted_safety_settings = []
            for setting in safety_settings:
                try:
                    category = HarmCategory[setting.get("category", "").upper()]
                    threshold = HarmBlockThreshold[setting.get("threshold", "").upper()]
                    formatted_safety_settings.append(SafetySetting(category=category, threshold=threshold))
                except KeyError:
                    # Handle invalid category or threshold, perhaps log a warning
                    pass # Or raise ValueError("Invalid safety setting...")

        params = {
            "model_name": model,
            "system_instruction": system_instruction,
            "contents": formatted_messages,
            "generation_config": GenerationConfig(**generation_config) if generation_config else None,
            "safety_settings": formatted_safety_settings if formatted_safety_settings else None,
            "tools": self.format_tools(tools) if tools else None,
        }
        if gemini_tool_config: # Add tool_config if specified
            params["tool_config"] = gemini_tool_config
            
        return params

    def create_chat_completion(self, model: str, messages: List[Dict[str, Any]], **kwargs) -> Dict[str, Any]:
        request_params = self._prepare_gemini_request_params(model, messages, **kwargs)
        
        try:
            gemini_model = genai.GenerativeModel(
                model_name=request_params.pop("model_name"),
                system_instruction=request_params.pop("system_instruction"),
                tools=request_params.pop("tools"),
                safety_settings=request_params.pop("safety_settings"),
                generation_config=request_params.pop("generation_config"),
                # Pass tool_config if it exists (it's part of request_params if set)
                tool_config=request_params.pop("tool_config", None) 
            )
            response = gemini_model.generate_content(
                contents=request_params.pop("contents"), 
                **request_params # any remaining kwargs for generate_content
            )
        except Exception as e:
            raise RuntimeError(f"Gemini API error: {e}")

        if response.prompt_feedback.block_reason:
            raise RuntimeError(f"Content blocked due to: {response.prompt_feedback.block_reason}. Details: {response.prompt_feedback.block_reason_message}")

        choices = []
        total_input_tokens = response.usage_metadata.prompt_token_count if response.usage_metadata else 0
        total_output_tokens = response.usage_metadata.candidates_token_count if response.usage_metadata else 0
        
        for i, candidate in enumerate(response.candidates):
            content_text = ""
            tool_calls = []
            has_tool_calls_in_candidate = False

            # Check for function calls
            if candidate.content and candidate.content.parts:
                for part_idx, part in enumerate(candidate.content.parts):
                    if part.function_call:
                        has_tool_calls_in_candidate = True
                        tool_calls.append({
                            "id": f"call_{i}_{part_idx}_{part.function_call.name}", # more unique id
                            "type": "function",
                            "function": {
                                "name": part.function_call.name,
                                "arguments": json.dumps(dict(part.function_call.args)) if part.function_call.args else "{}"
                            }
                        })
                    if part.text:
                        content_text += part.text
            
            # If no explicit text but function calls are present, content might be None or empty
            message_content = None if has_tool_calls_in_candidate and not content_text.strip() else content_text

            choice = {
                "index": i,
                "message": {
                    "role": "assistant",
                    "content": message_content,
                },
                "finish_reason": self._format_gemini_finish_reason(candidate.finish_reason, has_tool_calls_in_candidate)
            }
            if tool_calls:
                choice["message"]["tool_calls"] = tool_calls
            
            if candidate.finish_reason == genai_types.FinishReason.SAFETY:
                 # Include safety ratings if available and reason is SAFETY
                safety_ratings_dict = {}
                for rating in candidate.safety_ratings:
                    category_name = HarmCategory(rating.category).name
                    probability_name = rating.probability.name # Use probability name e.g. NEGLIGIBLE
                    safety_ratings_dict[category_name] = probability_name
                choice["safety_ratings"] = safety_ratings_dict


            choices.append(choice)

        return {
            "id": response.candidates[0].citation_metadata.citation_sources[0].uri if response.candidates and response.candidates[0].citation_metadata and response.candidates[0].citation_metadata.citation_sources else "gemini_response", # Placeholder ID
            "object": "chat.completion",
            "created": int(json.loads(response.candidates[0].to_json()).get("citation_metadata",{}).get("retrieval_source",{}).get("retrieval_time",0) or 0), # needs better timestamp
            "model": model,
            "choices": choices,
            "usage": {
                "prompt_tokens": total_input_tokens,
                "completion_tokens": total_output_tokens,
                "total_tokens": total_input_tokens + total_output_tokens,
            },
        }

    def create_streaming_chat_completion(self, model: str, messages: List[Dict[str, Any]], **kwargs) -> Generator[Dict[str, Any], None, None]:
        request_params = self._prepare_gemini_request_params(model, messages, **kwargs)

        try:
            gemini_model = genai.GenerativeModel(
                model_name=request_params.pop("model_name"),
                system_instruction=request_params.pop("system_instruction"),
                tools=request_params.pop("tools"),
                safety_settings=request_params.pop("safety_settings"),
                generation_config=request_params.pop("generation_config"),
                tool_config=request_params.pop("tool_config", None)
            )
            stream = gemini_model.generate_content(
                contents=request_params.pop("contents"),
                stream=True,
                **request_params
            )
        except Exception as e:
            raise RuntimeError(f"Gemini API error: {e}")

        for chunk_idx, chunk in enumerate(stream):
            if chunk.prompt_feedback.block_reason:
                # This error should ideally be caught before streaming starts, or handled carefully during.
                # Yielding an error object or raising here might be options.
                # For now, raising an error.
                raise RuntimeError(f"Content blocked during streaming due to: {chunk.prompt_feedback.block_reason}. Details: {chunk.prompt_feedback.block_reason_message}")

            # Initialize fields for each chunk
            delta_content = ""
            tool_call_chunks = [] # For streaming tool calls if Gemini supports it this way
            finish_reason_str = None
            usage_metadata = None
            
            # Process parts in the chunk
            if chunk.candidates:
                candidate = chunk.candidates[0] # Assuming one candidate in streaming for now
                has_tool_calls_in_chunk = False

                if candidate.content and candidate.content.parts:
                    for part_idx, part in enumerate(candidate.content.parts):
                        if part.text:
                            delta_content += part.text
                        if part.function_call:
                            has_tool_calls_in_chunk = True
                            # This is tricky for streaming. Gemini might send FC in one go or streamed.
                            # Assuming it sends the full FC in one part of a chunk.
                            tool_call_chunks.append({
                                # "index": 0, # if we need to specify which tool call is being updated
                                "id": f"call_stream_{chunk_idx}_{part_idx}_{part.function_call.name}",
                                "type": "function",
                                "function": {
                                    "name": part.function_call.name,
                                    "arguments": json.dumps(dict(part.function_call.args)) if part.function_call.args else "" # Arguments might be streamed
                                }
                            })
                
                # Determine finish reason for this chunk if available
                # The final finish_reason comes with the last chunk or after iteration.
                # Here, we map the current candidate's finish reason.
                finish_reason_str = self._format_gemini_finish_reason(candidate.finish_reason, has_tool_calls_in_chunk)


            # Construct the chunk dictionary
            # Mimic OpenAI's streaming format
            response_chunk = {
                "id": f"chatcmpl-stream-{chunk_idx}", # Placeholder ID
                "object": "chat.completion.chunk",
                "created": 0, # Placeholder timestamp
                "model": model,
                "choices": [
                    {
                        "index": 0, # Assuming one choice for streaming
                        "delta": {},
                        "finish_reason": finish_reason_str if finish_reason_str != "stop" or (delta_content or tool_call_chunks) else None, 
                        # Only send finish_reason if it's not 'stop' due to empty delta,
                        # or if it's a terminal reason like 'length', 'safety'.
                        # The final 'stop' usually comes with an empty delta.
                    }
                ]
            }

            if delta_content:
                response_chunk["choices"][0]["delta"]["content"] = delta_content
            
            if tool_call_chunks:
                 # If Gemini streams tool calls with arguments incrementally, this needs to be handled.
                 # For now, sending them as a list if they appear in the chunk.
                response_chunk["choices"][0]["delta"]["tool_calls"] = tool_call_chunks


            # The final finish reason and usage should ideally be sent after the loop.
            # However, some APIs might send usage per chunk or only at the end.
            # Gemini's `chunk.usage_metadata` might exist.
            if hasattr(chunk, 'usage_metadata') and chunk.usage_metadata:
                usage_metadata = {
                    "prompt_tokens": chunk.usage_metadata.prompt_token_count,
                    "completion_tokens": chunk.usage_metadata.candidates_token_count, # This might be cumulative or per chunk
                    "total_tokens": chunk.usage_metadata.total_token_count
                }
                response_chunk["usage"] = usage_metadata # OpenAI doesn't send usage in chunks, but we can add it if available

            # Only yield if there's actual content, tool calls, or a meaningful finish reason
            if delta_content or tool_call_chunks or (finish_reason_str and finish_reason_str != "stop"):
                 yield response_chunk
            elif finish_reason_str == "stop" and not (delta_content or tool_call_chunks): # Handle final empty chunk with stop
                 response_chunk["choices"][0]["finish_reason"] = "stop"
                 yield response_chunk


    def supports_images(self) -> bool:
        return True

    # BaseAdapter methods to be potentially overridden if different behavior is needed
    # def format_messages(self, messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    #     return super().format_messages(messages)

    # def format_tools(self, tools: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    #     return super().format_tools(tools)

```
