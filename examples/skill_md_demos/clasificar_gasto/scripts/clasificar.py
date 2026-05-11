"""Tool del skill `clasificar_gasto`.

Este archivo se carga automáticamente cuando el agente activa el skill
vía `capability.activate("clasificar_gasto")`. La función decorada con
`@tool` queda registrada en el capability padre.
"""
from instantneo import tool


_REGLAS = {
    "administrativo": ["alquiler", "luz", "agua", "internet", "papelería", "gas", "oficina"],
    "operativo":      ["mercadería", "insumo", "transporte", "mantenimiento", "envío", "embalaje"],
    "financiero":     ["interés", "comisión bancaria", "tarjeta", "transferencia", "banco"],
    "comercial":      ["publicidad", "marketing", "comisión vendedor", "evento", "promoción"],
}


@tool(
    description="Clasifica un gasto en una categoría contable según reglas predefinidas.",
    parameters={
        "descripcion": {"type": "string", "description": "Descripción breve del gasto."},
        "monto":       {"type": "number", "description": "Monto en dólares."},
    },
)
def clasificar_gasto_categoria(descripcion: str, monto: float) -> dict:
    desc_lower = descripcion.lower()
    for categoria, palabras in _REGLAS.items():
        if any(palabra in desc_lower for palabra in palabras):
            return {"descripcion": descripcion, "monto": monto, "categoria": categoria}
    return {"descripcion": descripcion, "monto": monto, "categoria": "sin_clasificar"}
