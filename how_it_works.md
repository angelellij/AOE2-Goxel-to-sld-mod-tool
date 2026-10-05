# Cómo funciona el pipeline .gox → .sld

## Flujo general

1. `scripts/gox_reader.py` lee el `.gox` (voxels con color RGBA).
2. `scripts/voxel_render.py` renderiza el modelo con una cámara fija (60° / 45°) y devuelve las pasadas `diffuse`, `normals`, `height`, `ao`, `alpha`, `marker` y `box_crop_px`. `marker` marca por geometría las caras de voxel azul puro.
3. `scripts/build_psd.py::build_layers` recorta cada pasada al tamaño del tile con `place_on_tile_canvas`, agrega un margen de `TILE_PAD` (2 px) a todas las capas, arma el diamante y la máscara de player color, y devuelve las capas.
4. `scripts/build_psd.py::write_psd` escala todo a 2x (`AUTHOR_SCALE`), escribe el PSD de 7 capas y devuelve la máscara del diamante para el parche de sombra.
5. `build_sld.py` convierte el PSD a `.sld` con DESpriteTool (vía Wine), parchea el canal de sombra con `scripts/patch_shadow.py` y lo instala en el mod de test.

## Capas del PSD

- **Diffuse:** silueta del edificio con alpha binario (255 o 0, binarizado en `>= 128`). Player color pintado en `#565656`. El interior del diamante queda transparente; sólo el borde del diamante va en `#333333`.
- **Damage:** vacío.
- **AmbientOcclusion:** silueta del edificio (alpha = píxeles ocupados), RGB blanco. No incluye el diamante.
- **Height y Normals:** vacíos.
- **Background:** vacío.
- **Decal:** no se escribe (queda el default del template).
- **Playercolor (canal):** máscara de los píxeles de player color.

## Player color

- Los `.gox` marcan la zona de player color con voxels azul puro `(0, 0, 255)`. El sombreado por cara sólo escala el color hacia abajo, así que el tono sigue siendo R=0, G=0.
- `voxel_render` marca esas caras en la pasada `marker` por geometría; no se adivina por color.
- `build_layers` convierte la máscara en una lista de tuplas `(x, y)` (`player_pixels`), pinta esos píxeles en el Diffuse con `#565656` y arma `player_color.png` con 255 en esos mismos píxeles.
- La máscara de player color y la silueta se marcan como ocupadas antes de calcular el AO.

## Diamante (base del edificio)

- El diamante se calcula desde `tile_size` (`voxel_render.tile_params`) con un margen de 1 px por lado, en escala de tile.
- **Borde:** cuatro rectas de 1 px (Bresenham) más la misma recta desplazada 1 px hacia abajo, es decir, 2 px de alto parejos por columna. Se pinta en `#333333` sólo donde no hay edificio. Es lo que hace clickeable la base.
- **Interior:** transparente en el Diffuse. Su oscurecido translúcido viene del canal de sombra.
- **Máscara de sombra:** el polígono lleno del diamante (`diamond`). `write_psd` la escala a 2x y la devuelve; `build_sld.py` la pasa a `patch_shadow.patch_sld_shadow`.

## Escalado

- El Diffuse y el AO se escalan a 2x con NEAREST en el alpha (el alpha no tiene interpolación, así no aparecen bordes semitransparentes).
- El RGB de las demás capas se escala con LANCZOS.
- LANCZOS sobre el Diffuse dejaba un halo oscuro junto a bordes brillantes. El alpha con BILINEAR creaba bordes semitransparentes negros; por eso el alpha es binario y se escala con NEAREST.

## Hallazgos sobre el formato SLD (openage)

- Cabecera de 16 bytes (`SLDX`, versión 4, número de frames en el offset 6). Los frames van en secuencia, sin tabla de offsets.
- Encabezado de frame de 12 bytes: ancho, alto, centro x, centro y, `frame_type` (offset 8), campo desconocido, índice.
- Cada layer empieza con un largo de 4 bytes que incluye el layer, y los layers van alineados a 4 bytes.
- Orden de layers por bit del `frame_type`: main (bit 0), shadow (bit 1), layer no documentado (bit 2), damage (bit 3), player color (bit 4).
- El layer no documentado tiene un encabezado con un rectángulo (x1, y1, x2, y2). Nuestro lumber camp lo genera a partir del Diffuse. Su función no está documentada; es el candidato a área de selección.

## Abierto (de `errores.md`)

- Empalizadas: las esquinas tienen banderas; las puertas en diagonal (abierta) están rotadas; las puertas 2x1 no tienen la puerta dibujada.
- Foundation de puerta de piedra: no usa los assets del mod ni la puerta cerrada; la 2x1 no tiene la parte de la puerta.
- Puerta de piedra fortificada: mismos problemas que la de piedra, más las banderas.
- Monasterio, castillo, TC: arreglar la construcción (lo tiene que arreglar un humano).
- Factoría y Krepost: falta foundation.
- Fortified church: falta todo.

## Notas de depuración

- `python3 build_sld.py --name <edificio> --debug` deja en `debug/` las capas por frame (`_Diffuse`, `_PlayerColor`, `_Diamond`, `_AmbientOcclusion`, `_Background`, etc.) y el render crudo de Goxel (`_raw_gox_Diffuse`, `_raw_gox_BlueMarker`).
- `PATCH_SHADOW` en `build_sld.py` activa el parche de sombra.
