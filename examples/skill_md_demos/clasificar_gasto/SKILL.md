---
name: clasificar_gasto
description: Clasifica un gasto del comercio en una de cuatro categorías contables (administrativo, operativo, financiero, comercial).
license: MIT
---

# Clasificar gasto contable

Esta skill agrupa una tool (`clasificar_gasto_categoria`) y la guía de
reglas para usarla correctamente.

## Categorías permitidas

Las cuatro categorías que el clasificador puede devolver son:

- **administrativo** — alquiler de oficina, servicios públicos (luz,
  agua, internet, gas), materiales de papelería.
- **operativo** — insumos para producción/venta (mercadería, embalaje),
  transporte y logística, mantenimiento de equipos.
- **financiero** — intereses bancarios, comisiones de tarjetas,
  cargos por transferencias, gastos de cuentas bancarias.
- **comercial** — publicidad, campañas de marketing, comisiones de
  vendedores, eventos promocionales.

## Reglas de uso

1. La tool `clasificar_gasto_categoria` recibe `descripcion` y `monto`
   del gasto. Devuelve la categoría elegida.
2. Si la descripción no encaja claramente en ninguna, devolverá
   `sin_clasificar`. En ese caso, **no inventes** una nueva
   categoría — reportá el caso al usuario para revisión manual.
3. Para reportar un conjunto de gastos clasificados, usá el formato:

       - <descripción> ($<monto>) → <categoria>

4. Nunca uses categorías fuera de las cuatro listadas, aunque la
   descripción del gasto sugiera otra cosa.
