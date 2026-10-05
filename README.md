# AOE2 Checker mod tool

Convierte los modelos voxel de `files-gox/*.gox` en gráficos `.sld` reales de
AoE2:DE (edificio vivo, animación de destrucción y fundación/construcción) y
los instala directo en el mod de prueba.

`build_sld.py` está en la raíz del repo (es el comando principal). Se corre
desde ahí:

## Construir e instalar

```bash
# Todo: cada edificio vivo, cada destrucción, cada fundación.
uv run build_sld.py

# Un edificio puntual (repetible), sin destrucción ni fundación.
uv run build_sld.py --name monastery --no-des --no-foun

# Varios edificios puntuales, con destrucción pero sin fundación.
uv run build_sld.py --name monastery --name castle --no-foun

# Cantidad de workers en paralelo (default: 16, un núcleo por worker).
uv run build_sld.py --workers 8
```

`--name` sin destrucción/fundación aplicables para ese edificio simplemente
no hace nada en ese paso (no tira error).

## Config

- `config/buildings.json` y `config/areas.json` son **archivos de
  configuración hand-editables**, no algo que se regenere solo. `build_sld.py`
  los lee tal cual están - nunca los pisa.
- `gen_building_config.py` es una herramienta aparte para rellenar/actualizar
  `config/buildings.json` a partir de `rename.py` y de los `.gox` reales.
  Correla vos manualmente solo cuando agregás un `.gox` nuevo o cambiás las
  dimensiones de uno existente:

  ```bash
  uv run scripts/gen_building_config.py
  ```

  Preserva tus overrides existentes (`tile_size`, `frame_count`,
  `camera_angle_x/y`) y solo completa lo que falta; si el resultado nuevo
  tuviera menos de la mitad de las entradas que ya había, se niega a escribir
  (probable bug de rutas) salvo que le pases `--force`.

## Documentación del pipeline

El detalle técnico completo (por qué cada cosa está hecha así, bugs
encontrados y arreglados, decisiones de diseño) está en
`SLD_PIPELINE_PLAN.md`.

`scripts/readme` documenta el proceso manual viejo (Goxel + SLX Studio),
reemplazado por este pipeline automático.
