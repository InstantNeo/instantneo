from typing import List, Dict, Any
from instantneo.adapters.base_adapter import BaseAdapter
from typing import AsyncGenerator
import groq
import json

class GroqAdapter(BaseAdapter):
    def __init__(self, api_key: str):
        from groq import Groq
        self.client = Groq(api_key=api_key)

    def create_chat_completion(self, messages: List[Dict[str, Any]], **kwargs) -> Dict[str, Any]:
        try:
            response = self.client.chat.completions.create(messages=messages, **kwargs)
            return response
        except Exception as e:
            raise RuntimeError(f"Error en la llamada a la API de Groq: {str(e)}")

    async def create_streaming_chat_completion(self, messages: List[Dict[str, Any]], **kwargs) -> AsyncGenerator[Dict[str, Any], None]:
        try:
            for chunk in self.client.chat.completions.create(messages=messages, stream=True, **kwargs):
                yield chunk
        except Exception as e:
            raise RuntimeError(f"Error en el streaming de la API de Groq: {str(e)}")

    def process_response(self, response: Dict[str, Any]) -> Dict[str, Any]:
        return {
            'content': response['choices'][0]['message']['content'],
            'tool_calls': response['choices'][0]['message'].get('tool_calls', []),
            'usage': response['usage'],
            'model': response.get('model'),
            'id': response.get('id')
        }

    def supports_images(self) -> bool:
        return True  # Groq soporta imágenes con modelos de visión

    # Sobrescribimos estos métodos para asegurarnos de que son compatibles con Groq
    def format_messages(self, messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        # Groq usa el mismo formato que OpenAI para los mensajes
        return messages

    def format_tools(self, tools: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        # Groq usa el mismo formato que OpenAI para las herramientas
        return tools