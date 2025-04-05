"""
Herramientas para gestión de SSL en el protocolo MCP.

Proporciona funciones para generar y validar certificados SSL,
principalmente para entornos de desarrollo.
"""

import os
import datetime
import logging
from typing import Optional, Tuple, List

# Intentar importar la biblioteca cryptography
# No es una dependencia obligatoria, pero se requiere para generar certificados
try:
    from cryptography import x509
    from cryptography.x509.oid import NameOID
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.hazmat.backends import default_backend
    CRYPTOGRAPHY_AVAILABLE = True
except ImportError:
    CRYPTOGRAPHY_AVAILABLE = False

# Configurar logging
logger = logging.getLogger(__name__)


def generate_self_signed_cert(
    cert_file: str, 
    key_file: str, 
    common_name: str = "localhost",
    organization: str = "InstantNeo MCP Server",
    country: str = "US",
    state: str = "California",
    locality: str = "San Francisco",
    valid_days: int = 365,
    key_size: int = 2048
) -> Tuple[bool, str]:
    """
    Genera un certificado SSL autofirmado para desarrollo.
    
    Args:
        cert_file: Ruta donde guardar el archivo de certificado
        key_file: Ruta donde guardar el archivo de clave privada
        common_name: Nombre común para el certificado (por defecto: "localhost")
        organization: Nombre de organización
        country: Código de país (dos letras)
        state: Estado o provincia
        locality: Localidad o ciudad
        valid_days: Días de validez del certificado
        key_size: Tamaño de la clave RSA en bits
        
    Returns:
        Tupla con (éxito, mensaje)
        
    Raises:
        ImportError: Si la biblioteca cryptography no está instalada
    """
    if not CRYPTOGRAPHY_AVAILABLE:
        message = (
            "La biblioteca 'cryptography' es necesaria para generar certificados SSL. "
            "Instálala con 'pip install cryptography'."
        )
        logger.error(message)
        raise ImportError(message)
    
    try:
        # Asegurar que existan los directorios
        cert_dir = os.path.dirname(cert_file) or "."
        key_dir = os.path.dirname(key_file) or "."
        os.makedirs(cert_dir, exist_ok=True)
        os.makedirs(key_dir, exist_ok=True)
        
        # Generar clave privada
        private_key = rsa.generate_private_key(
            public_exponent=65537,
            key_size=key_size,
            backend=default_backend()
        )
        
        # Crear atributos del sujeto y emisor
        subject = issuer = x509.Name([
            x509.NameAttribute(NameOID.COUNTRY_NAME, country),
            x509.NameAttribute(NameOID.STATE_OR_PROVINCE_NAME, state),
            x509.NameAttribute(NameOID.LOCALITY_NAME, locality),
            x509.NameAttribute(NameOID.ORGANIZATION_NAME, organization),
            x509.NameAttribute(NameOID.COMMON_NAME, common_name),
        ])
        
        # Crear extensiones
        san = x509.SubjectAlternativeName([
            x509.DNSName(common_name)
        ])
        
        # Si common_name es una IP, agregar como IP SAN
        if common_name != "localhost" and not common_name.startswith("*."):
            # Intentar agregar IP SAN solo si no es un wildcard
            try:
                from ipaddress import ip_address
                try:
                    ip = ip_address(common_name)
                    san = x509.SubjectAlternativeName([
                        x509.DNSName(common_name),
                        x509.IPAddress(ip)
                    ])
                except ValueError:
                    # No es una IP, usar solo DNSName
                    pass
            except ImportError:
                # ipaddress no está disponible, ignorar
                pass
        
        # Construir certificado
        now = datetime.datetime.utcnow()
        cert = x509.CertificateBuilder().subject_name(
            subject
        ).issuer_name(
            issuer
        ).public_key(
            private_key.public_key()
        ).serial_number(
            x509.random_serial_number()
        ).not_valid_before(
            now
        ).not_valid_after(
            now + datetime.timedelta(days=valid_days)
        ).add_extension(
            san, critical=False
        ).add_extension(
            x509.BasicConstraints(ca=False, path_length=None), critical=True
        ).sign(private_key, hashes.SHA256(), default_backend())
        
        # Guardar clave privada
        with open(key_file, "wb") as f:
            f.write(private_key.private_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PrivateFormat.PKCS8,
                encryption_algorithm=serialization.NoEncryption()
            ))
        
        # Guardar certificado
        with open(cert_file, "wb") as f:
            f.write(cert.public_bytes(serialization.Encoding.PEM))
        
        message = (
            f"Certificado SSL autofirmado generado correctamente:\n"
            f"- Certificado: {cert_file}\n"
            f"- Clave privada: {key_file}\n"
            f"- Válido por: {valid_days} días\n"
            f"- Common Name: {common_name}\n"
            f"NOTA: Este certificado es solo para desarrollo, no lo uses en producción."
        )
        logger.info(message)
        return True, message
        
    except Exception as e:
        message = f"Error al generar certificado SSL: {str(e)}"
        logger.error(message)
        return False, message


def validate_certificate(cert_file: str) -> Tuple[bool, dict]:
    """
    Valida un certificado SSL existente.
    
    Args:
        cert_file: Ruta al archivo de certificado
        
    Returns:
        Tupla con (válido, información)
        La información incluye detalles como fechas de validez,
        common name, emisor, etc.
    """
    if not CRYPTOGRAPHY_AVAILABLE:
        message = (
            "La biblioteca 'cryptography' es necesaria para validar certificados SSL. "
            "Instálala con 'pip install cryptography'."
        )
        logger.error(message)
        raise ImportError(message)
    
    try:
        # Leer certificado
        with open(cert_file, "rb") as f:
            cert_data = f.read()
            
        # Cargar certificado
        cert = x509.load_pem_x509_certificate(cert_data, default_backend())
        
        # Obtener información
        now = datetime.datetime.utcnow()
        not_valid_before = cert.not_valid_before
        not_valid_after = cert.not_valid_after
        
        # Verificar validez temporal
        is_valid = not_valid_before <= now <= not_valid_after
        
        # Extraer información del sujeto
        subject = cert.subject
        common_name = None
        for attr in subject:
            if attr.oid == NameOID.COMMON_NAME:
                common_name = attr.value
                break
                
        # Extraer información del emisor
        issuer = cert.issuer
        issuer_cn = None
        for attr in issuer:
            if attr.oid == NameOID.COMMON_NAME:
                issuer_cn = attr.value
                break
        
        # Comprobar si es autofirmado
        is_self_signed = subject == issuer
        
        # Extraer SANs
        san_extension = None
        for extension in cert.extensions:
            if extension.oid == x509.ExtensionOID.SUBJECT_ALTERNATIVE_NAME:
                san_extension = extension
                break
                
        sans = []
        if san_extension:
            san_value = san_extension.value
            for name in san_value:
                if isinstance(name, x509.DNSName):
                    sans.append(f"DNS:{name.value}")
                elif isinstance(name, x509.IPAddress):
                    sans.append(f"IP:{name.value}")
        
        # Crear resumen de información
        info = {
            "subject": {
                "common_name": common_name,
            },
            "issuer": {
                "common_name": issuer_cn,
            },
            "validity": {
                "not_before": not_valid_before.isoformat(),
                "not_after": not_valid_after.isoformat(),
                "days_remaining": (not_valid_after - now).days,
                "is_valid": is_valid
            },
            "is_self_signed": is_self_signed,
            "sans": sans,
            "fingerprint": cert.fingerprint(hashes.SHA256()).hex(),
        }
        
        return is_valid, info
        
    except Exception as e:
        logger.error(f"Error al validar certificado SSL: {str(e)}")
        return False, {"error": str(e)}


def check_ssl_requirements() -> Tuple[bool, List[str]]:
    """
    Verifica los requisitos para usar SSL en la aplicación.
    
    Returns:
        Tupla con (cumple_requisitos, mensajes)
    """
    messages = []
    requirements_met = True
    
    # Verificar que la biblioteca cryptography esté instalada
    if not CRYPTOGRAPHY_AVAILABLE:
        requirements_met = False
        messages.append(
            "La biblioteca 'cryptography' no está instalada. "
            "Instálala con 'pip install cryptography'."
        )
        
    return requirements_met, messages