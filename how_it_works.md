# Cómo funciona el pipeline .gox → .sld

## Flujo general

1. `scripts/DIRS.py` lee `settings.toml` (o `default_settings.toml` si no existe) y arma todas las rutas: modelos, configs, carpeta de mods y DESpriteTool.
2. `scripts/gox_reader.py` lee el `.gox` (voxels con color RGBA y la caja de Goxel).
3. `scripts/voxel_render.py` renderiza el modelo con la cámara de su entrada en la config (por defecto 60° / 45°) y devuelve las pasadas `diffuse`, `normals`, `height`, `ao`, `alpha`, `marker` y `box_crop_px`. `marker` marca por geometría las caras de voxel azul puro.
4. `scripts/build_psd.py::build_layers` ubica cada pasada en el canvas del tile con `place_on_tile_canvas`, agrega un margen de `TILE_PAD` (2 px), arma el diamante y la máscara de player color, y devuelve las capas.
5. `scripts/build_psd.py::write_psd` escala todo por `AUTHOR_SCALE` (2 en UHD, 1 en SD), escribe el PSD de 7 capas y devuelve la máscara del diamante para el parche de sombra.
6. `build_sld.py` convierte el PSD a `.sld` con DESpriteTool (directo en Windows, con Wine y `xvfb-run` en Linux), parchea el canal de sombra con `scripts/patch_shadow.py` y lo instala en la mod configurada, con el nombre de cada gráfico del juego que reemplaza.

## Configuración

- `settings.toml` (raíz, ignorado por git): carpeta de mods, nombres de las mods, `uhd`, carpeta de modelos, rutas de `buildings.json` / `resources.json` y `thumbnail`. `default_settings.toml` es la plantilla y el respaldo.
- `config/buildings.json`: una entrada por edificio. Es la única fuente de nombres de gráficos y de parámetros (modelo, cámara, `tile_size`, `frame_count`, construcción).
- `config/areas.json`: grupos de civilizaciones; cada gráfico se instala una vez por civ del grupo.
- `config/resources.json`: recursos, con sus gráficos del juego, `frame_count` y `brightness`.

## SD y UHD

- **UHD (`uhd = true`):** el PSD se arma a 2x. DESpriteTool genera el `_x2.sld` desde el PSD y reduce a la mitad para el `_x1.sld`.
- **SD (`uhd = false`):** el PSD se arma a 1x y DESpriteTool se corre con `GenerateX1Assets: false`. Su única salida sale sin sufijo (`<nombre>.sld`) y se renombra a `_x1.sld`. No se genera ningún `_x2`.
- El parche de sombra siempre recibe la máscara a 2x y la reduce; en SD se le pasa una copia duplicada a 2x de la máscara de 1x.

## Capas del PSD

- **Diffuse:** silueta del edificio con alpha binario (255 o 0, binarizado en `>= 128`). Player color pintado en `#565656`. El interior del diamante queda transparente; sólo el borde del diamante va en `#333333`.
- **Damage:** vacío.
- **AmbientOcclusion:** silueta del edificio (alpha = píxeles ocupados), RGB blanco. No incluye el diamante.
- **Height y Normals:** vacíos.
- **Background:** vacío.
- **Decal:** no se escribe (queda el default del template).
- **Playercolor (canal):** máscara de los píxeles de player color.

## Color

- Sombreado plano por cara en `voxel_render.shade_for`: arriba 1,0 (el color exacto del `.gox`), un lateral 0,75, el otro 0,6. No hay otros ajustes de exposición, contraste ni gamma.
- Los recursos pueden oscurecerse con `brightness` en `resources.json` (todos usan 0,9): se multiplica el color de cada voxel antes de renderizar, sin tocar el `.gox`.

## Player color

- Los `.gox` marcan la zona de player color con voxels azul puro `(0, 0, 255)`. El sombreado por cara sólo escala el color hacia abajo, así que el tono sigue siendo R=0, G=0.
- `voxel_render` marca esas caras en la pasada `marker` por geometría; no se adivina por color.
- `build_layers` pinta esos píxeles en el Diffuse con `#565656` y arma la máscara del canal de player color con 255 en esos mismos píxeles.

## Diamante (base del edificio)

- El diamante se calcula desde `tile_size` (`voxel_render.tile_params`), o desde `footprint` cuando la huella no es cuadrada (por ejemplo las puertas 4x1).
- **Borde:** cuatro rectas de 1 px (Bresenham) más la misma recta desplazada 1 px hacia abajo. Se pinta en `#333333` sólo donde no hay edificio. Es lo que hace clickeable la base.
- **Interior:** transparente en el Diffuse. Su oscurecido translúcido viene del canal de sombra (`patch_shadow.patch_sld_shadow`).

## La caja de Goxel

- La caja del `.gox` (chunk IMG) define cómo se ubica el modelo en el tile. Tiene que medir exactamente `tile_size` tiles (8 unidades por tile). Si queda en el valor por defecto de Goxel (2x2 tiles) en un modelo de 1 tile, el render lo achica a la mitad y lo corre a una esquina.
- Se corrige en el `.gox`, con `gox_writer.set_box_xy` (por ejemplo media extensión 4 y centro −12 para un modelo 1x1 en −16..−8). Goxel vuelve a la caja por defecto al guardar.

## Destrucción

- Para los edificios con `destructible: true`, el modelo se derrumba de arriba hacia abajo en varios estadios. Los nombres son los del edificio vivo con `_destruction` antes de `_x1`, salvo que la entrada tenga `destruction_targets`.

## Construcción (foundations)

- Cada entrada `<base>f` de `buildings.json` arma la construcción del edificio `<base>`. Los estadios cortan el modelo por altura (`construction_stage_voxels`).
- Claves de la entrada de foundation:
  - `construction_gox`: modelo propio para la construcción (por ejemplo `palisade_gate1_full`); su base se toma de `<construction_gox>0.gox`.
  - `footprint`: huella no cuadrada, `[ancho, alto, "ne"|"se"]`.
  - `stage_fractions`: fracciones de altura de cada estadio (por defecto 25/50/75 con `construction_gox`, 30/55 sin él).
  - `base_frame`: `false` para no agregar el frame de base antes de los estadios.
  - `stage_extra_levels`: suma niveles al cálculo del corte, para modelos con muy pocos niveles de altura.
  - `wall_style`: repite los estadios por cada variante del muro y agrega un estadio al 100%.
  - `rotate_90`: gira el modelo 90° alrededor de su propio centro (también vale en entradas de edificio vivo).
- La cantidad de frames tiene que coincidir con lo que espera el juego; si sobra o falta un frame, el juego muestra un estadio que no corresponde (por ejemplo uno invisible o igual al edificio terminado).

## Recursos

- `build_sld.py --resources` arma los recursos de `resources.json` en `resources_mod`.
- `frame_count` debe ser al menos el máximo de frames que usan sus gráficos en el juego. El juego elige una variante por índice; si el índice no existe, el recurso queda invisible (por ejemplo `n_tree_rainforest` usa 69).

## Thumbnail

- Si `thumbnail` tiene una clave, al final del build se renderiza ese edificio o recurso solo, sobre blanco a 1920x1080, con el diamante como sombra translúcida y el player color en rojo, y se guarda como `thumbnail.png` de la mod.

## Hallazgos sobre el formato SLD (openage)

- Cabecera de 16 bytes (`SLDX`, versión 4, número de frames en el offset 6). Los frames van en secuencia, sin tabla de offsets.
- Encabezado de frame de 12 bytes: ancho, alto, centro x, centro y, `frame_type` (offset 8), campo desconocido, índice.
- Cada layer empieza con un largo de 4 bytes que incluye el layer, y los layers van alineados a 4 bytes.
- Orden de layers por bit del `frame_type`: main (bit 0), shadow (bit 1), layer no documentado (bit 2), damage (bit 3), player color (bit 4).
- El layer no documentado tiene un encabezado con un rectángulo (x1, y1, x2, y2). Su función no está documentada; es el candidato a área de selección.

## Notas de depuración

- `uv run build_sld.py --name <edificio> --debug` deja en `debug/` las capas por frame (`_Diffuse`, `_PlayerColor`, `_Diamond`, `_AmbientOcclusion`, etc.), el render crudo (`_raw_gox_Diffuse`, `_raw_gox_BlueMarker`) y los estadios de construcción (`stageNN_*`).
- `PATCH_SHADOW` en `build_sld.py` activa el parche de sombra.
