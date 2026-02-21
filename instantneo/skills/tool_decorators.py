import functools
import contextvars
import inspect
from typing import List, Dict, Any, Union, Optional, get_type_hints
import docstring_parser

def tool(
    description: Optional[str] = None,
    parameters: Optional[Dict[str, Dict[str, Any]]] = None,
    tags: Optional[List[str]] = None,
    version: Optional[str] = "1.0",
    **additional_metadata
):
    """
    Decorator that adds metadata to the function and captures information about the last call.

    Automatically extracts parameter types and function documentation (description and
    parameters) in Google, NumPy, or reStructuredText format if not specified in the decorator's
    metadata. Values provided manually take precedence.
    """
    tags = tags or []  # Asigna lista vacía si no se proporcionan tags

    def decorator(func):
        # Obtener el docstring de la función
        func_doc = inspect.getdoc(func) or ""
        parsed_doc = None
        if func_doc:
            try:
                parsed_doc = docstring_parser.parse(func_doc)
            except Exception:
                parsed_doc = None

        # Determinar la descripción final:
        # - Si se proporciona en el decorador, se usa esa.
        # - Si no, se usa la short_description del docstring (si existe).
        # - Si tampoco, se usa el docstring completo o un fallback.
        if description is not None:
            description_final = description
        elif parsed_doc and parsed_doc.short_description:
            description_final = parsed_doc.short_description
        else:
            description_final = func_doc or "No description"

        # Obtener las anotaciones de los parámetros (excluyendo 'return')
        annotations = get_type_hints(func)
        annotations.pop('return', None)

        # Extraer la firma de la función para determinar los parámetros requeridos
        signature = inspect.signature(func)

        required_params = [
            param_name for param_name, param in signature.parameters.items()
            if param.default == inspect.Parameter.empty  # Sin valor por defecto
        ]

        # Construir la metadata de los parámetros:
        # Si se proporciona metadata explícita, se utiliza; sino, se genera a partir de hints y docstring.
        parameters_final = {}
        for name in signature.parameters:
            if parameters and name in parameters:
                param_metadata = parameters[name]
                # Si no es un diccionario, lo convertimos a uno usando el valor como descripción
                if not isinstance(param_metadata, dict):
                    param_metadata = {"description": str(param_metadata)}
                else:
                    param_metadata = param_metadata.copy()
                if "type" not in param_metadata:
                    param_type = annotations.get(name, "")
                    param_metadata["type"] = param_type.__name__ if isinstance(param_type, type) else str(param_type)
                parameters_final[name] = param_metadata
            else:
                # Generar metadata básica
                param_type = annotations.get(name, "")
                param_type_str = param_type.__name__ if isinstance(param_type, type) else str(param_type)
                param_description = ""
                if parsed_doc:
                    for p in parsed_doc.params:
                        if p.arg_name == name:
                            param_description = p.description or ""
                            break
                parameters_final[name] = {
                    "type": param_type_str,
                    "description": param_description
                }

        # Combinar toda la metadata extraída y la proporcionada manualmente
        metadata = {
            'name': func.__name__,
            'description': description_final,
            'parameters': parameters_final,
            'required': required_params,
            'tags': tags,
            'version': version,
        }
        metadata.update(additional_metadata)

        # Context variable para almacenar la información de la última llamada a la función
        last_call_var = contextvars.ContextVar(f"last_call_{func.__name__}_{id(func)}", default=None)

        # Definir el wrapper, diferenciando funciones asíncronas y sincrónicas
        if inspect.iscoroutinefunction(func):
            @functools.wraps(func)
            async def async_wrapper(*args, **kwargs):
                last_call_var.set({
                    'args': args,
                    'kwargs': kwargs,
                    'result': None,
                    'exception': None
                })
                try:
                    result = await func(*args, **kwargs)
                    info = last_call_var.get()
                    info['result'] = result
                    return result
                except Exception as e:
                    info = last_call_var.get()
                    info['exception'] = e
                    raise
            wrapper = async_wrapper
        else:
            @functools.wraps(func)
            def sync_wrapper(*args, **kwargs):
                last_call_var.set({
                    'args': args,
                    'kwargs': kwargs,
                    'result': None,
                    'exception': None
                })
                try:
                    result = func(*args, **kwargs)
                    info = last_call_var.get()
                    info['result'] = result
                    return result
                except Exception as e:
                    info = last_call_var.get()
                    info['exception'] = e
                    raise
            wrapper = sync_wrapper

        # Métodos auxiliares para acceder a la información de la última llamada
        wrapper.get_last_call = lambda: last_call_var.get()
        wrapper.get_last_result = lambda: last_call_var.get().get('result') if last_call_var.get() else None
        wrapper.get_last_params = lambda: {'args': last_call_var.get().get('args'),
                                            'kwargs': last_call_var.get().get('kwargs')} if last_call_var.get() else None

        # Asignar la metadata procesada a la función (dual name for backward compat)
        wrapper.tool_metadata = metadata
        wrapper.skill_metadata = metadata  # Backward compat alias (same dict object)

        return wrapper
    return decorator

# Backward compatibility alias
skill = tool
