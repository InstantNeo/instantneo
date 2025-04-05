"""
Utilidades para convertir entre formatos de InstantNeo y MCP.
"""
from typing import Dict, Any, List, Optional, Union

def _map_python_type_to_json_schema(python_type: str) -> Dict[str, Any]:
    """
    Mapea tipos de Python a tipos JSON Schema.
    
    Args:
        python_type: Tipo de Python como string (ej: "str", "int", "List[str]")
        
    Returns:
        Dict: Objeto JSON Schema correspondiente
    """
    # Tipos básicos
    basic_types = {
        "str": {"type": "string"},
        "int": {"type": "integer"},
        "float": {"type": "number"},
        "bool": {"type": "boolean"},
        "None": {"type": "null"},
        "any": {},  # Sin restricción de tipo
        "Any": {},
        "dict": {"type": "object"},
        "Dict": {"type": "object"},
        "list": {"type": "array"},
        "List": {"type": "array"},
        "tuple": {"type": "array"},
        "Tuple": {"type": "array"},
    }
    
    # Verificar si es un tipo básico
    if python_type in basic_types:
        return basic_types[python_type]
    
    # Verificar si es un tipo genérico (List[...], Dict[...], etc.)
    if python_type.startswith("List[") or python_type.startswith("list["):
        # Extraer el tipo de elemento
        item_type = python_type[5:-1]  # Quitar "List[" y "]"
        return {
            "type": "array",
            "items": _map_python_type_to_json_schema(item_type)
        }
    
    if python_type.startswith("Dict[") or python_type.startswith("dict["):
        # Para diccionarios, no podemos representar completamente la estructura en JSON Schema
        # sin conocer las claves específicas, así que usamos un objeto genérico
        return {"type": "object"}
    
    if python_type.startswith("Union[") or python_type.startswith("Optional["):
        # Para Union y Optional, usamos anyOf
        if python_type.startswith("Union["):
            types_str = python_type[6:-1]  # Quitar "Union[" y "]"
        else:
            types_str = python_type[9:-1]  # Quitar "Optional[" y "]"
            
        # Dividir por comas, pero respetando los corchetes anidados
        types = []
        current = ""
        bracket_level = 0
        
        for char in types_str:
            if char == "[":
                bracket_level += 1
            elif char == "]":
                bracket_level -= 1
            elif char == "," and bracket_level == 0:
                types.append(current.strip())
                current = ""
                continue
            
            current += char
        
        if current:
            types.append(current.strip())
        
        return {
            "anyOf": [_map_python_type_to_json_schema(t) for t in types]
        }
    
    # Para tipos desconocidos, no especificamos restricciones
    return {}

def skill_metadata_to_mcp_tool(name: str, metadata: Dict[str, Any]) -> Dict[str, Any]:
    """
    Convierte metadatos de skill al formato tool MCP.
    
    Args:
        name: Nombre de la skill
        metadata: Metadatos de la skill
        
    Returns:
        Dict: Objeto tool MCP
    """
    # Extraer descripción y parámetros
    description = metadata.get("description", "")
    parameters = metadata.get("parameters", {})
    required_params = metadata.get("required", [])
    
    # Construir propiedades para JSON Schema
    properties = {}
    for param_name, param_info in parameters.items():
        param_type = param_info.get("type", "")
        param_description = param_info.get("description", "")
        
        # Convertir tipo de Python a JSON Schema
        type_schema = _map_python_type_to_json_schema(param_type)
        
        # Añadir descripción si existe
        if param_description:
            type_schema["description"] = param_description
            
        properties[param_name] = type_schema
    
    # Construir estructura de tool MCP
    tool = {
        "name": name,
        "description": description,
        "inputSchema": {
            "type": "object",
            "properties": properties,
        }
    }
    
    # Añadir parámetros requeridos si existen
    if required_params:
        tool["inputSchema"]["required"] = required_params
    
    # Añadir anotaciones si hay tags
    tags = metadata.get("tags", [])
    if tags:
        tool["annotations"] = {
            "tags": tags
        }
        
        # Inferir algunas propiedades de ToolAnnotations basadas en los tags
        if "read_only" in tags:
            tool["annotations"]["readOnlyHint"] = True
        if "idempotent" in tags:
            tool["annotations"]["idempotentHint"] = True
        if "destructive" in tags:
            tool["annotations"]["destructiveHint"] = True
    
    return tool

def mcp_tool_result_to_response(result: Any) -> Dict[str, Any]:
    """
    Convierte un resultado de ejecución de skill a formato de respuesta MCP.
    
    Args:
        result: Resultado de la ejecución de la skill
        
    Returns:
        Dict: Objeto de respuesta MCP
    """
    # Si el resultado ya es un diccionario con el formato esperado, devolverlo directamente
    if isinstance(result, dict) and "content" in result:
        return result
    
    # Verificar si es una excepción
    is_error = isinstance(result, Exception)
    
    # Convertir el resultado a texto si no es un tipo básico
    if not isinstance(result, (str, int, float, bool, list, dict)) or result is None:
        result = str(result)
    
    # Para tipos básicos, crear una respuesta de texto
    return {
        "content": [
            {
                "type": "text",
                "text": str(result)
            }
        ],
        "isError": is_error
    }