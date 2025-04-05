"""
Configuraciones para el servidor MCP.
"""
from typing import Dict, Any

def get_default_config(environment: str = "development") -> Dict[str, Any]:
    """
    Obtiene la configuración por defecto según el entorno.
    
    Args:
        environment: Entorno de ejecución ("development", "production", "testing")
        
    Returns:
        Dict: Configuración por defecto
    """
    # Configuración base común a todos los entornos
    base_config = {
        "server_name": "InstantNeo MCP Server",
        "server_version": "1.0.0",
        "protocol_version": "2025-03-26",
        "cleanup_interval": 300,  # 5 minutos
        "session_timeout": 3600,  # 1 hora
        "http": {
            "enabled": True,
            "host": "localhost",
            "port": 8000,
            "use_https": False,
            "cert_file": None,
            "key_file": None,
            "cors_origins": ["*"],
            "auth": {
                "enabled": False,
                "type": "api_key",  # "api_key", "basic", "oauth"
                "api_keys": []
            }
        },
        "stdio": {
            "enabled": False
        },
        "logging": {
            "level": "info",
            "file": None
        }
    }
    
    # Configuraciones específicas por entorno
    if environment == "development":
        return base_config
    
    elif environment == "production":
        prod_config = base_config.copy()
        prod_config.update({
            "http": {
                "enabled": True,
                "host": "0.0.0.0",  # Escuchar en todas las interfaces
                "port": 8000,
                "use_https": True,
                "cert_file": "cert.pem",
                "key_file": "key.pem",
                "cors_origins": [],  # Restringir CORS en producción
                "auth": {
                    "enabled": True,
                    "type": "api_key",
                    "api_keys": []
                }
            },
            "stdio": {
                "enabled": False
            },
            "logging": {
                "level": "warning",
                "file": "mcp_server.log"
            }
        })
        return prod_config
    
    elif environment == "testing":
        test_config = base_config.copy()
        test_config.update({
            "http": {
                "enabled": True,
                "host": "localhost",
                "port": 8001,  # Puerto diferente para no interferir con desarrollo
                "use_https": False
            },
            "stdio": {
                "enabled": True
            },
            "logging": {
                "level": "debug",
                "file": None
            }
        })
        return test_config
    
    # Si el entorno no es reconocido, devolver configuración de desarrollo
    return base_config

def merge_configs(base_config: Dict[str, Any], override_config: Dict[str, Any]) -> Dict[str, Any]:
    """
    Combina dos configuraciones, permitiendo anular valores.
    
    Args:
        base_config: Configuración base
        override_config: Configuración que anula valores de la base
        
    Returns:
        Dict: Configuración combinada
    """
    result = base_config.copy()
    
    def _merge_dict(target, source):
        for key, value in source.items():
            if key in target and isinstance(target[key], dict) and isinstance(value, dict):
                _merge_dict(target[key], value)
            else:
                target[key] = value
    
    _merge_dict(result, override_config)
    return result