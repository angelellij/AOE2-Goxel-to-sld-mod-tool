# Regla: no tocar archivos .gox

**No modificar ningún archivo `.gox` (en `files-gox/` ni en otro lado) sin que Javier lo pida explícitamente.**

Esto incluye recolorear, mover voxels, reescribir cajas (IMG) o regenerar composites. Si algo parece estar mal en un `.gox`, se reporta y se espera la orden. No se decide por Javier.

## Qué pasó (2026-10-04)

- Recoloreé el tan `(217,160,102)` de z=0 a gris de muro `(132,126,135)` en `stone_gate1_full.gox`, `stone_gate1_full0.gox`, `fortified_gate1_full.gox` y `fortified_gate1_full0.gox` (32 voxels en cada uno). No me lo pidió.
- `stone_gate1_full0.gox` y `fortified_gate1_full0.gox` son archivos que Javier editó en Goxel. Los toqué igual.
- Lo revertí: los 32 voxels volvieron a tan en las mismas posiciones (`x -22..-19` y `2..5`, `y -14..-11`, `z=0`). Verificado leyendo los cuatro archivos.
- El problema real que Javier señaló: el error está en el archivo que toma el pipeline, no en los colores. Pendiente de revisar.

## Reglas de trabajo (pedido de Javier)

- **Cada vez que se corrige algo, correr el debug** (`build_sld.py --name <edificio> --no-des --debug`) y revisar los Diffuse de cada frame antes de decir que está arreglado.
- No dar nada por resuelto sin ver el debug del frame afectado.

## Muro de empalizada (`palisade` / `palisadef`)

- Foundation nueva `palisadef` → `b_dark_wall_palisade_constr_x1` (nombre elegido por patrón de la vanilla; no confirmado en el juego).
- `wall_style: true`, sin frame base (`base_frame: false`), etapas 9/33/66.
- El SLD instalado tiene 20 frames: 4 estadios (9/33/66/100) × 5 repeticiones.
- Pendiente: confirmar en el juego qué se ve en el tercer estadio. El debug del 66% muestra las paredes; el 9% y el 33% salen casi iguales porque el corte por altura solo incluye el nivel z=0 en ambos.

## Corrección: `palisadef` quitado

- Revisé `238283_Power - Checker buildings` (mod real, solo nombres y tamaños). No trae ningún gráfico de construcción para el muro de empalizada oscuro: solo `b_dark_wall_palisade_x1.smx` y `_flag_`. Tampoco trae construcción de la puerta oscura.
- Por eso se quitó la entrada `palisadef` y su SLD (`b_dark_wall_palisade_constr_x1.sld`) de la mod de prueba. Un gráfico con nombre inventado no coincide con la mod real.
- Pendiente: entender qué construcción usa el juego para el muro en la mod real (sin gráfico propio) y por qué el tercer estadio de la mod de prueba se ve invisible.

## Puertas diagonales NE/SE (`palisade_ne/se_closedf`)

- Problema: el 25% era idéntico a la base (con 4 niveles de altura, el corte del 25% solo incluía z=0), así que el juego mostraba base hasta el salto al vivo.
- Fix: `stage_extra_levels: 1` en ambas foundations. El corte pasa a `zmin + fracción × (span + 1)`, así el 25% incluye z=1.
- Verificado con debug: 25% ya tiene tramos de empalizada, 50% más completo.
- Pendiente: confirmar en el juego.

## Puertas horizontales ne/se: último estadio a 60%

- `stage_fractions` pasa a `[0.20, 0.45, 0.60]` en `palisade_ne_closedf` y `palisade_se_closedf`. El último frame (60%) queda más bajo que el 70% anterior.
- Pendiente (Javier): el costado de la puerta sobresale de la línea de empalizada. Eso viene del composite `palisade_gate1_full` y no se arregla sin tocar el gox, así que no se cambió.
