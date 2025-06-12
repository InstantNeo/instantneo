import json
import os
from typing import Dict, Any, List, Union, Generator, Optional
from instantneo.adapters.base_adapter import BaseAdapter
from types import SimpleNamespace


class GeminiAdapter(BaseAdapter):
    """Adapter for Google's Gemini API.
    
    This adapter handles the conversion between InstantNeo's unified interface
    and Gemini's specific API format, including support for multimodal inputs
    like images and various file types (PDFs, etc.).
    
    Note: This is a basic implementation. Advanced features like temperature control,
    max_tokens, and function calling are not yet implemented pending better
    understanding of the google-genai library's current capabilities.
    """
    
    def __init__(self, api_key: str):
        try:
            from google import genai
            self.genai = genai
            self.client = genai.Client(api_key=api_key)
            self._file_cache = {}  # Cache uploaded files to avoid re-uploading
        except ImportError:
            raise ImportError(
                "google-genai package is required for Gemini adapter. "
                "Install it with: pip install google-genai"
            )
    
    def create_chat_completion(self, **kwargs) -> Any:
        """Create a chat completion using Gemini API."""
        try:
            # Get basic parameters
            model = kwargs.get('model', 'gemini-2.0-flash')
            messages = kwargs.get('messages', [])
            additional_params = kwargs.get('additional_params', {})
            files = additional_params.get('files', None)
            
            # Build contents
            contents = self._build_contents(messages, files)
            
            # Check if tools are provided
            tools = kwargs.get('tools', None)
            
            if tools:
                # Import types from google.genai
                from google.genai import types
                
                # Convert InstantNeo format to Gemini function declarations
                function_declarations = []
                for tool in tools:
                    if 'function' in tool and tool.get('type') == 'function':
                        func = tool['function']
                        function_declarations.append({
                            'name': func['name'],
                            'description': func['description'],
                            'parameters': func['parameters']
                        })
                
                if function_declarations:
                    # Create config with tools
                    tools_obj = types.Tool(function_declarations=function_declarations)
                    config = types.GenerateContentConfig(tools=[tools_obj])
                    
                    # Make the API call with config
                    response = self.client.models.generate_content(
                        model=model,
                        contents=contents,
                        config=config
                    )
                else:
                    response = self.client.models.generate_content(
                        model=model,
                        contents=contents
                    )
            else:
                response = self.client.models.generate_content(
                    model=model,
                    contents=contents
                )
            
            return self._convert_response_to_instantneo_format(response)
            
        except Exception as e:
            raise RuntimeError(f"Error in Gemini API: {str(e)}")
    
    def create_streaming_chat_completion(self, **kwargs) -> Generator[str, None, None]:
        """Create a streaming chat completion."""
        try:
            # Get basic parameters
            model = kwargs.get('model', 'gemini-2.0-flash')
            messages = kwargs.get('messages', [])
            files = kwargs.get('files', None)
            
            # Build contents
            contents = self._build_contents(messages, files)
            
            # Note: The google-genai library might handle streaming differently
            # For now, we'll call generate_content and yield the result
            response = self.client.models.generate_content(
                model=model,
                contents=contents
            )
            
            # Yield the response text in chunks if available
            if hasattr(response, 'text') and response.text:
                text = response.text
                # Yield in reasonable chunks
                chunk_size = 100
                for i in range(0, len(text), chunk_size):
                    yield text[i:i + chunk_size]
            
        except Exception as e:
            raise RuntimeError(f"Error in Gemini API streaming: {str(e)}")
    
    def supports_images(self) -> bool:
        """Gemini supports multimodal inputs including images."""
        return True
    
    # Note: Keeping this method for future use when generation_config is supported
    def _convert_to_gemini_format_future(self, kwargs: Dict[str, Any]) -> Dict[str, Any]:
        """Convert InstantNeo format to Gemini API format."""
        # Extract key parameters
        messages = kwargs.get('messages', [])
        model = kwargs.get('model', 'gemini-2.0-flash')
        
        # Extract files from additional params if present
        files = kwargs.get('files', None)
        
        # Build contents from messages
        contents = self._build_contents(messages, files)
        
        # Build Gemini-specific parameters
        gemini_kwargs = {
            'model': model,
            'contents': contents
        }
        
        # Build generation_config for parameters
        # Note: We'll only add parameters that are actually supported
        generation_config = {}
        
        # Check if these parameters are supported by trying them
        if 'temperature' in kwargs and kwargs['temperature'] is not None:
            generation_config['temperature'] = kwargs['temperature']
        
        if 'max_tokens' in kwargs and kwargs['max_tokens'] is not None:
            # Try both parameter names in case one works
            generation_config['max_output_tokens'] = kwargs['max_tokens']
        
        if 'stop' in kwargs and kwargs['stop'] is not None:
            stop_sequences = kwargs['stop'] if isinstance(kwargs['stop'], list) else [kwargs['stop']]
            generation_config['stop_sequences'] = stop_sequences
        
        # Add more parameters as supported
        if 'seed' in kwargs and kwargs['seed'] is not None:
            generation_config['seed'] = kwargs['seed']
            
        # Only add generation_config if it has parameters
        if generation_config:
            gemini_kwargs['generation_config'] = generation_config
        
        # Handle tools/functions if present
        if 'tools' in kwargs and kwargs['tools']:
            gemini_kwargs['tools'] = self._convert_tools_format(kwargs['tools'])
        
        return gemini_kwargs
    
    def _build_contents(self, messages: List[Dict[str, Any]], files: Optional[List[str]] = None) -> Union[str, List[Any]]:
        """Build Gemini contents from messages and optional files."""
        # Handle system messages by prepending to content
        system_content = ""
        user_messages = []
        
        for msg in messages:
            if msg['role'] == 'system':
                system_content += msg['content'] + "\n"
            else:
                user_messages.append(msg)
        
        # If only text content and no files, return simple string
        if not files and len(user_messages) == 1 and isinstance(user_messages[0]['content'], str):
            content = user_messages[0]['content']
            if system_content:
                content = system_content + "\n" + content
            return content
        
        # Build multimodal content
        parts = []
        
        # Add system message as first part if exists
        if system_content:
            parts.append(system_content.strip())
        
        # Process user messages
        for msg in user_messages:
            if isinstance(msg['content'], str):
                parts.append(msg['content'])
            elif isinstance(msg['content'], list):
                # Handle multimodal content
                for item in msg['content']:
                    if item['type'] == 'text':
                        parts.append(item['text'])
                    elif item['type'] == 'image_url':
                        # InstantNeo passes base64 images with data URLs
                        url_or_path = item['image_url']['url']
                        
                        if url_or_path.startswith('data:'):
                            # Base64 data - need to convert to file
                            parts.append(self._create_part_from_base64(url_or_path))
                        else:
                            # For Gemini, we skip URL handling as it requires file upload
                            # This would need to be implemented if URL support is needed
                            pass
        
        # Add files if provided (from additional_params)
        if files:
            for file_path in files:
                parts.append(self._upload_file(file_path))
        
        return parts
    
    def _upload_file(self, file_path: str):
        """Upload a file to Gemini and return the file reference."""
        # Check cache first
        if file_path in self._file_cache:
            return self._file_cache[file_path]
        
        # Upload file using the correct parameter name
        uploaded_file = self.client.files.upload(file=file_path)
        self._file_cache[file_path] = uploaded_file
        return uploaded_file
    
    def _create_part_from_base64(self, data_url: str):
        """Create a part from base64 data URL."""
        # Extract MIME type and data
        header, data = data_url.split(',', 1)
        mime_type = header.split(':')[1].split(';')[0]
        
        import base64
        image_bytes = base64.b64decode(data)
        
        # Create a temporary file
        import tempfile
        suffix = '.jpg' if 'jpeg' in mime_type or 'jpg' in mime_type else '.png'
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp_file:
            tmp_file.write(image_bytes)
            tmp_path = tmp_file.name
        
        try:
            # Upload and return
            result = self._upload_file(tmp_path)
            return result
        finally:
            # Clean up temp file
            os.unlink(tmp_path)
    
    # Note: Keeping these methods for future use when more features are supported
    def _convert_tools_format_future(self, tools: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Convert InstantNeo tools format to Gemini format."""
        gemini_tools = []
        function_declarations = []
        
        for tool in tools:
            if 'function' in tool:
                func = tool['function']
                function_declarations.append({
                    'name': func['name'],
                    'description': func['description'],
                    'parameters': func['parameters']
                })
        
        if function_declarations:
            gemini_tools.append({
                'function_declarations': function_declarations
            })
        
        return gemini_tools
    
    def _convert_response_to_instantneo_format(self, response) -> Any:
        """Convert Gemini response to InstantNeo format."""
        # Create response structure similar to OpenAI
        message = SimpleNamespace()
        message.content = response.text if hasattr(response, 'text') else ""
        message.tool_calls = []
        
        # Check for function calls in response
        if hasattr(response, 'candidates') and response.candidates:
            candidate = response.candidates[0]
            if hasattr(candidate, 'content') and hasattr(candidate.content, 'parts'):
                for part in candidate.content.parts:
                    if hasattr(part, 'function_call') and part.function_call is not None:
                        # Convert to InstantNeo format
                        tool_call = SimpleNamespace()
                        tool_call.type = 'function'
                        tool_call.function = SimpleNamespace(
                            name=part.function_call.name,
                            # IMPORTANTE: Gemini usa 'args' no 'arguments'
                            arguments=json.dumps(part.function_call.args)
                        )
                        message.tool_calls.append(tool_call)
        
        # Create choice
        choice = SimpleNamespace()
        choice.message = message
        choice.finish_reason = getattr(response, 'finish_reason', 'stop')
        
        # Create response
        response_obj = SimpleNamespace()
        response_obj.choices = [choice]
        
        # Add usage information if available
        if hasattr(response, 'usage_metadata'):
            response_obj.usage = response.usage_metadata
        
        return response_obj