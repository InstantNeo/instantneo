---
name: politicas_devolucion
description: Reglas internas del comercio para autorizar (o rechazar) la devolución de un pedido por parte de un cliente.
license: Internal use only
---

# Política de devoluciones del comercio

## Ventana de elegibilidad

- Producto **sin abrir**: hasta 30 días desde la entrega.
- Producto **abierto pero sin uso**: hasta 14 días, con foto del estado.
- Producto **usado**: no se admite devolución, salvo defecto de fábrica
  comprobable.

## Excepciones

1. **Alimentos perecederos** (yerba abierta, mate listo abierto):
   no se admiten devoluciones por inocuidad. Solo crédito a cuenta si
   el cliente reclama dentro de los 3 días por defecto.
2. **Productos personalizados** (mate con grabado, termo con logo):
   no admiten devolución.
3. **Compras corporativas mayores a $2000**: la devolución requiere
   aprobación del responsable de operaciones.

## Procedimiento que el agente debe seguir

Cuando un cliente pida una devolución:

1. Pedirle el id del pedido y la razón.
2. Cruzar con las reglas anteriores y decidir: **autorizado**,
   **rechazado**, o **escalar al responsable**.
3. En el caso `autorizado`, devolver al cliente: motivo de autorización
   + monto a reintegrar + plazo (5-7 días hábiles).
4. En el caso `rechazado`, explicar la regla específica que aplica.
5. En el caso `escalar`, indicar al cliente que su solicitud quedará en
   revisión.
