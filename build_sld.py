import itertools
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "scripts"))

import DIRS
import build_psd
import building_config
import patch_shadow

# SD mode (uhd false): author the PSDs at 1x and have DESpriteTool convert
# them as-is, without the extra x1 downscale, so no _x2 is ever built.
UHD = DIRS.SETTINGS.get("uhd", True)
build_psd.AUTHOR_SCALE = 2 if UHD else 1

_display_num_counter = itertools.count(100)
_display_num_lock = threading.Lock()


def _next_display_num():
    with _display_num_lock:
        return next(_display_num_counter)


def _sprite_tool_command(relative_batch_dir):
    """DESpriteTool runs natively on Windows; on Linux it goes through Wine,
    inside a virtual X display (xvfb-run) so it can run headless and in
    parallel."""
    if DIRS.WINDOWS:
        return [os.path.join(DIRS.SPRITES_TOOL, "DESpriteTool.exe"), relative_batch_dir]
    return ["xvfb-run", "-n", str(_next_display_num()), "wine", "DESpriteTool.exe", relative_batch_dir]


def convert_sprites(src_dir, building_name, attempts=3):
    batch_dir = f"{DIRS.SPRITES_TOOL}/buildings/aoe2checker_build/{building_name}_batch"
    dest_dir = f"{batch_dir}/{building_name}"
    relative_batch_dir = f"buildings/aoe2checker_build/{building_name}_batch"

    last_error = None
    for attempt in range(1, attempts + 1):
        if os.path.isdir(batch_dir):
            shutil.rmtree(batch_dir)
        os.makedirs(dest_dir)
        for fname in os.listdir(src_dir):
            if fname.endswith(".psd"):
                shutil.copy(f"{src_dir}/{fname}", dest_dir)

        with open(f"{batch_dir}/settings.json", "w") as f:
            f.write("{}" if UHD else '{"GenerateX1Assets": false}')

        try:
            subprocess.run(
                _sprite_tool_command(relative_batch_dir),
                cwd=DIRS.SPRITES_TOOL,
                check=True,
                capture_output=True,
                text=True,
            )
            sld_files = [f for f in os.listdir(dest_dir) if f.endswith(".sld")]
            if not UHD:
                # without x1 generation DESpriteTool names its only output
                # "<name>.sld"; built from a 1x PSD, it is the x1 asset
                renamed = []
                for f in sld_files:
                    if not re.search(r"_x[12]\.sld$", f):
                        os.replace(f"{dest_dir}/{f}", f"{dest_dir}/{f[:-4]}_x1.sld")
                        f = f[:-4] + "_x1.sld"
                    renamed.append(f)
                sld_files = renamed
            if not sld_files:
                raise RuntimeError(
                    f"DESpriteTool produced no .sld for {building_name} - check "
                    f"{dest_dir} and its settings.json"
                )
            return dest_dir, sld_files
        except (subprocess.CalledProcessError, RuntimeError) as e:
            last_error = e
            if attempt < attempts:
                print(f"[{building_name}] conversion attempt {attempt}/{attempts} failed ({e}), retrying...")
                time.sleep(1)
    raise last_error


def install(dest_dir, sld_files, target_names, mod_name):
    graphics_dir = f"{DIRS.AOEMODS}{mod_name}{DIRS.AOEGRAPHICS}"
    os.makedirs(graphics_dir, exist_ok=True)
    info_path = f"{DIRS.AOEMODS}{mod_name}/info.json"
    if not os.path.isfile(info_path):
        # the game only lists a local mod that has an info.json
        with open(info_path, "w", encoding="utf-8") as f:
            json.dump({"Author": "", "CacheStatus": 0, "Description": "", "Title": mod_name}, f)
    installed = []
    for sld_file in sld_files:
        variant = sld_file.rsplit("_", 1)[-1].split(".")[0]
        if variant == "x2" and not UHD:
            continue
        src = f"{dest_dir}/{sld_file}"
        for target in target_names:
            base = target[:-3] if target.endswith("_x1") else target
            out_name = f"{base}_{variant}.sld"
            for copy_attempt in range(3):
                try:
                    shutil.copy(src, f"{graphics_dir}{out_name}")
                    break
                except FileNotFoundError:
                    if copy_attempt == 2:
                        raise
                    time.sleep(0.5)
            installed.append(out_name)
    return installed


PATCH_SHADOW = True


def patch_sld_shadow_if_enabled(sld_path, mask):
    if PATCH_SHADOW:
        patch_shadow.patch_sld_shadow(sld_path, mask)


def build_and_install(building_name, tile_size=None, mod_name=DIRS.MOD_SLD_TEST, debug_dir=None):
    config = building_config.load(building_name)
    if config is None:
        raise ValueError(
            f"no {building_name!r} entry in {building_config.CONFIG_PATH} - add it there"
        )
    with tempfile.TemporaryDirectory(prefix=f"{building_name}_psd_") as psd_dir:
        first_path = f"{psd_dir}/{building_name}_0000.psd"

        footprint_guide = None
        if config.get("empty"):
            build_psd.write_blank_psd(first_path)
            footprint_guide = np.zeros((64, 64), dtype=np.uint8)
        else:
            tile_size = tile_size or config["tile_size"]
            if tile_size is None:
                raise ValueError(f"{building_name}'s config has no tile_size set - fix config/buildings.json")

            angle_x = config.get("camera_angle_x", 60)
            angle_y = config.get("camera_angle_y", 45)
            margin = config.get("margin", 0)
            gox_name = config.get("gox") or building_name
            model = None
            if config.get("box_from") or config.get("rotate_90"):
                from gox_reader import read_gox
                model = read_gox(f"{DIRS.GOX_DIR}/{gox_name}.gox")
                if config.get("box_from"):
                    model.box = read_gox(f"{DIRS.GOX_DIR}/{config['box_from']}.gox").box
                if config.get("rotate_90"):
                    model.voxels = build_psd._rotate_voxels_90(model.voxels)
            layers = build_psd.build_layers(
                building_name, tile_size, angle_x=angle_x, angle_y=angle_y, margin=margin, gox_name=gox_name,
                model=model, debug_dir=debug_dir,
            )
            _canvas_size, footprint_guide = build_psd.write_psd(
                layers, first_path, building_name, tile_size, debug_dir=debug_dir,
            )

        frame_count = config.get("frame_count", 1)
        for i in range(1, frame_count):
            shutil.copy(first_path, f"{psd_dir}/{building_name}_{i:04d}.psd")
        print(f"[{building_name}] wrote {frame_count} frame(s) to {psd_dir}")

        dest_dir, sld_files = convert_sprites(psd_dir, building_name)
        print(f"[{building_name}] converted: {sld_files}")

        if footprint_guide is not None:
            for sld_file in sld_files:
                if sld_file.endswith("_x1.sld"):
                    patch_sld_shadow_if_enabled(f"{dest_dir}/{sld_file}", footprint_guide)

        target_names = building_config.target_names(config)
        installed = install(dest_dir, sld_files, target_names, mod_name)
        print(f"[{building_name}] installed into {mod_name!r}: {installed}")
        return installed


RESOURCE_CONFIG_PATH = DIRS.RESOURCES_CONFIG


def load_resource_config(key):
    with open(RESOURCE_CONFIG_PATH) as f:
        all_config = json.load(f)
    return all_config.get(key)


def _resource_model(config, key):
    from gox_reader import read_gox
    model = read_gox(f"{DIRS.GOX_DIR}/{config.get('gox') or key}.gox")
    brightness = config.get("brightness", 1.0)
    if brightness != 1.0:
        # darken every voxel's RGB; pure-blue player-color markers stay as they are
        model.voxels = {
            pos: c if (c[0] == 0 and c[1] == 0 and c[2] > 0)
            else (*(min(255, round(ch * brightness)) for ch in c[:3]), c[3])
            for pos, c in model.voxels.items()
        }
    return model


def make_thumbnail(key, mod_name, resource=False, size=(1920, 1080)):
    """Writes <mod>/thumbnail.png: `key` rendered alone, centered on a white
    16:9 canvas, with the footprint diamond as a translucent shadow like in
    game and player color shown in red. Scaled up by the largest whole
    factor that fits, with NEAREST so the pixel art stays sharp."""
    from PIL import Image
    if resource:
        config = load_resource_config(key)
        layers = build_psd.build_layers(key, config["tile_size"], model=_resource_model(config, key))
    else:
        config = building_config.load(key)
        layers = build_psd.build_layers(
            key, config["tile_size"], angle_x=config.get("camera_angle_x", 60),
            angle_y=config.get("camera_angle_y", 45), margin=config.get("margin", 0),
            gox_name=config.get("gox") or key,
        )
    diffuse = layers["Diffuse"]
    w, h = diffuse.size
    rgba = np.asarray(diffuse).copy()
    player = np.asarray(layers["player_color"]).reshape(h, w) > 0
    rgba[player, 0] = np.clip(rgba[player, 0].astype(int) * 3, 0, 255)
    rgba[player, 1] //= 4
    rgba[player, 2] //= 4
    shadow = np.zeros((h, w, 4), np.uint8)
    shadow[..., 3] = (np.asarray(layers["diamond"]).reshape(h, w) > 0) * 70
    img = Image.new("RGBA", (w, h), (255, 255, 255, 255))
    img = Image.alpha_composite(img, Image.fromarray(shadow))
    img = Image.alpha_composite(img, Image.fromarray(rgba)).convert("RGB")
    content = np.any(np.asarray(img) < 250, axis=2)
    ys, xs = np.nonzero(content)
    img = img.crop((xs.min(), ys.min(), xs.max() + 1, ys.max() + 1))
    scale = max(1, int(min(size[0] * 0.6 / img.width, size[1] * 0.7 / img.height)))
    img = img.resize((img.width * scale, img.height * scale), Image.NEAREST)
    out = Image.new("RGB", size, (255, 255, 255))
    out.paste(img, ((size[0] - img.width) // 2, (size[1] - img.height) // 2))
    path = f"{DIRS.AOEMODS}{mod_name}/thumbnail.png"
    os.makedirs(os.path.dirname(path), exist_ok=True)
    out.save(path)
    print(f"[{key}] thumbnail written to {path}")
    return path


def build_and_install_resource(key, mod_name=DIRS.MOD_RESOURCES, debug_dir=None):
    config = load_resource_config(key)
    if config is None:
        raise ValueError(f"no {key!r} entry in {RESOURCE_CONFIG_PATH} - add it there")
    frame_count = config.get("frame_count", 1)
    tile_size = config["tile_size"]
    gox_name = config.get("gox") or key

    with tempfile.TemporaryDirectory(prefix=f"{key}_psd_") as psd_dir:
        first_path = f"{psd_dir}/{key}_0000.psd"
        layers = build_psd.build_layers(key, tile_size, model=_resource_model(config, key))
        _canvas_size, footprint_guide = build_psd.write_psd(layers, first_path, key, tile_size, debug_dir=debug_dir)

        for i in range(1, frame_count):
            shutil.copy(first_path, f"{psd_dir}/{key}_{i:04d}.psd")
        print(f"[{key}] wrote {frame_count} frame(s) to {psd_dir}")

        dest_dir, sld_files = convert_sprites(psd_dir, key)
        print(f"[{key}] converted: {sld_files}")

        if footprint_guide is not None:
            for sld_file in sld_files:
                if sld_file.endswith("_x1.sld"):
                    patch_sld_shadow_if_enabled(f"{dest_dir}/{sld_file}", footprint_guide)

        target_names = config["targets"]
        installed = install(dest_dir, sld_files, target_names, mod_name)
        print(f"[{key}] installed into {mod_name!r}: {installed}")
        return installed


def build_and_install_destruction(building_name, mod_name=DIRS.MOD_SLD_TEST, num_stages=10, stage_repeat=3, debug_dir=None):
    d_key = building_name + "d"
    config = building_config.load(building_name)
    if config is None:
        raise ValueError(f"no {building_name!r} entry in {building_config.CONFIG_PATH} - add it there")
    target_names = building_config.destruction_target_names(config)

    tile_size = config["tile_size"]
    angle_x = config.get("camera_angle_x", 60)
    angle_y = config.get("camera_angle_y", 45)
    margin = config.get("margin", 0)
    gox_name = config.get("gox") or building_name

    variant_count = config.get("frame_count", 1) if config.get("frame_count_is_variants") else 1

    with tempfile.TemporaryDirectory(prefix=f"{d_key}_psd_") as psd_dir, \
            tempfile.TemporaryDirectory(prefix=f"{d_key}_stages_") as stage_dir:
        stages = build_psd.build_destruction_frames(
            building_name, tile_size, num_stages, angle_x, angle_y, margin=margin, gox_name=gox_name,
        )
        stage_guides = {}
        stage_paths = []
        for stage_index, layers in enumerate(stages):
            stage_path = f"{stage_dir}/{d_key}_stage{stage_index:02d}.psd"
            _canvas_size, fg = build_psd.write_psd(
                layers, stage_path, building_name, tile_size, debug_dir=debug_dir,
            )
            stage_guides[stage_path] = fg
            repeat = stage_repeat * 3 if stage_index == len(stages) - 1 else stage_repeat
            stage_paths.extend([stage_path] * repeat)
        frame_guides = [stage_guides[p] for p in stage_paths]

        frame_i = 0
        for stage_path in stage_paths:
            shutil.copy(stage_path, f"{psd_dir}/{d_key}_{frame_i:04d}.psd")
            frame_i += 1
        for _variant in range(1, variant_count):
            frame_guides.extend([stage_guides[stage_paths[-1]]] * len(stage_paths))
            for _ in stage_paths:
                shutil.copy(stage_paths[-1], f"{psd_dir}/{d_key}_{frame_i:04d}.psd")
                frame_i += 1
        print(
            f"[{d_key}] wrote {frame_i} frame(s) ({num_stages} stages x {stage_repeat}, "
            f"last stage x{stage_repeat * 3}, x{variant_count} shape variant(s)) to {psd_dir}"
        )

        dest_dir, sld_files = convert_sprites(psd_dir, d_key)
        print(f"[{d_key}] converted: {sld_files}")

        if frame_guides:
            for sld_file in sld_files:
                if sld_file.endswith("_x1.sld"):
                    patch_sld_shadow_if_enabled(f"{dest_dir}/{sld_file}", frame_guides)

        installed = install(dest_dir, sld_files, target_names, mod_name)
        print(f"[{d_key}] installed into {mod_name!r}: {installed}")
        return installed


def build_and_install_damage_states(building_name, mod_name=DIRS.MOD_SLD_TEST, debug_dir=None):
    config = building_config.load(building_name)
    if config is None:
        raise ValueError(f"no {building_name!r} entry in {building_config.CONFIG_PATH} - add it there")
    tile_size = config["tile_size"]
    angle_x = config.get("camera_angle_x", 60)
    angle_y = config.get("camera_angle_y", 45)
    margin = config.get("margin", 0)
    gox_name = config.get("gox") or building_name

    damage_frame_count = 6

    percents = (25, 50, 75)
    stages = build_psd.build_destruction_frames(
        building_name, tile_size, num_frames=len(percents) + 1, angle_x=angle_x, angle_y=angle_y,
        margin=margin, gox_name=gox_name,
    )
    installed_all = {}
    for percent, layers in zip(percents, stages):
        d_key = f"{building_name}_destr_{percent}"
        with tempfile.TemporaryDirectory(prefix=f"{d_key}_psd_") as psd_dir:
            first_path = f"{psd_dir}/{d_key}_0000.psd"
            _canvas_size, fg = build_psd.write_psd(layers, first_path, building_name, tile_size, debug_dir=debug_dir)
            for i in range(1, damage_frame_count):
                shutil.copy(first_path, f"{psd_dir}/{d_key}_{i:04d}.psd")
            dest_dir, sld_files = convert_sprites(psd_dir, d_key)
            print(f"[{d_key}] converted: {sld_files}")
            for sld_file in sld_files:
                if sld_file.endswith("_x1.sld"):
                    patch_sld_shadow_if_enabled(f"{dest_dir}/{sld_file}", fg)
            target_names = building_config.damage_target_names(config, percent)
            installed = install(dest_dir, sld_files, target_names, mod_name)
            print(f"[{d_key}] installed into {mod_name!r}: {installed}")
            installed_all[percent] = installed
    return installed_all


def build_and_install_foundation(building_name, mod_name=DIRS.MOD_SLD_TEST, f_key=None, debug_dir=None):
    f_key = f_key or (building_name + "f")
    f_config = building_config.load(f_key)
    if f_config is None:
        raise ValueError(f"no {f_key!r} entry in {building_config.CONFIG_PATH} - no foundation target to install as")
    target_names = building_config.target_names(f_config)

    config = building_config.load(building_name)
    if config is None:
        raise ValueError(f"no {building_name!r} entry in {building_config.CONFIG_PATH} - add it there")
    tile_size = config["tile_size"]
    angle_x = config.get("camera_angle_x", 60)
    angle_y = f_config.get("camera_angle_y", config.get("camera_angle_y", 45))
    margin = config.get("margin", 0)

    stage_repeat = config.get("frame_count", 1) if f_config.get("wall_style") else 1

    foundation_name = f_key[:-1]
    with tempfile.TemporaryDirectory(prefix=f"{f_key}_psd_") as psd_dir, \
            tempfile.TemporaryDirectory(prefix=f"{f_key}_stages_") as stage_dir:
        frames = build_psd.build_foundation_frames(
            building_name, tile_size, angle_x, angle_y, foundation_name=foundation_name, margin=margin,
            construction_gox=f_config.get("construction_gox"),
            footprint=tuple(f_config["footprint"]) if f_config.get("footprint") else None,
            include_full_stage=f_config.get("wall_style", False),
            stage_fractions=f_config.get("stage_fractions"),
            base_frame=f_config.get("base_frame", True),
            stage_extra_levels=f_config.get("stage_extra_levels", 0),
            rotate_90=f_config.get("rotate_90", False),
        )
        stage_paths = []
        stage_guides = []
        for i, layers in enumerate(frames):
            path = f"{stage_dir}/stage{i:02d}.psd"
            _canvas_size, fg = build_psd.write_psd(layers, path, building_name, tile_size, debug_dir=debug_dir)
            stage_paths.append(path)
            stage_guides.append(fg)

        frame_i = 0
        frame_guides = []
        for _ in range(stage_repeat):
            for stage_path, stage_guide in zip(stage_paths, stage_guides):
                shutil.copy(stage_path, f"{psd_dir}/{f_key}_{frame_i:04d}.psd")
                frame_guides.append(stage_guide)
                frame_i += 1
        print(f"[{f_key}] wrote {frame_i} frame(s) ({len(frames)} stages cycled x{stage_repeat}) to {psd_dir}")

        dest_dir, sld_files = convert_sprites(psd_dir, f_key)
        print(f"[{f_key}] converted: {sld_files}")

        if frame_guides:
            for sld_file in sld_files:
                if sld_file.endswith("_x1.sld"):
                    patch_sld_shadow_if_enabled(f"{dest_dir}/{sld_file}", frame_guides)

        installed = install(dest_dir, sld_files, target_names, mod_name)
        print(f"[{f_key}] installed into {mod_name!r}: {installed}")
        return installed


def foundation_families(all_config=None):
    all_config = all_config or building_config.load_all()
    families = {}
    for key in sorted(all_config):
        if not all_config[key].get("foundation") or not key.endswith("f") or key.endswith("ff"):
            continue
        base = key[:-1]
        candidates = sorted(
            name for name in all_config
            if re.sub(r"\d+$", "", name) == base and not all_config[name].get("empty") and all_config[name].get("gox")
        )
        if candidates:
            families[key] = candidates[0]
    return families


def build_many_foundation(mod_name=DIRS.MOD_SLD_TEST, workers=16, only_names=None, debug_dir=None):
    from concurrent.futures import ThreadPoolExecutor, as_completed

    all_config = building_config.load_all()
    families = foundation_families(all_config)
    if only_names is not None:
        families = {f_key: name for f_key, name in families.items() if name in only_names}
    missing = [f_key for f_key in families
               if all_config[f_key].get("construction_gox")
               and not os.path.isfile(f"{DIRS.GOX_DIR}/{all_config[f_key]['construction_gox']}.gox")]
    if missing:
        print(f"Skipping {len(missing)} foundation(s) with no construction .gox in {DIRS.GOX_DIR}: {', '.join(missing)}")
        families = {f_key: name for f_key, name in families.items() if f_key not in missing}
    ok, failed = {}, {}
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {
            pool.submit(build_and_install_foundation, name, mod_name, f_key, debug_dir): f_key
            for f_key, name in families.items()
        }
        for future in as_completed(futures):
            f_key = futures[future]
            try:
                ok[f_key] = future.result()
            except Exception as e:
                failed[f_key] = e
                print(f"[{f_key}] FAILED: {e}")
    return ok, failed


def build_many_destruction(building_names, mod_name=DIRS.MOD_SLD_TEST, workers=16, debug_dir=None):
    from concurrent.futures import ThreadPoolExecutor, as_completed

    ok, failed = {}, {}
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {
            pool.submit(build_and_install_destruction, name, mod_name, 10, 3, debug_dir): name
            for name in building_names
        }
        for future in as_completed(futures):
            name = futures[future]
            try:
                ok[name] = future.result()
            except Exception as e:
                failed[name] = e
                print(f"[{name}d] FAILED: {e}")
    return ok, failed


def build_many(building_names, mod_name=DIRS.MOD_SLD_TEST, workers=16, debug_dir=None):
    from concurrent.futures import ThreadPoolExecutor, as_completed

    ok, failed = {}, {}
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {
            pool.submit(build_and_install, name, None, mod_name, debug_dir): name
            for name in building_names
        }
        for future in as_completed(futures):
            name = futures[future]
            try:
                ok[name] = future.result()
            except Exception as e:
                failed[name] = e
                print(f"[{name}] FAILED: {e}")
    return ok, failed


def _report(label, ok, failed, total):
    print(f"\n=== {label} ===")
    print(f"OK: {len(ok)}/{total}")
    if failed:
        print(f"FAILED ({len(failed)}): {', '.join(sorted(failed))}")


if __name__ == "__main__":
    argv = sys.argv[1:]

    def pop_flag(flag):
        if flag in argv:
            argv.remove(flag)
            return True
        return False

    def pop_value(flag, default, cast):
        if flag in argv:
            i = argv.index(flag)
            value = cast(argv[i + 1])
            del argv[i:i + 2]
            return value
        return default

    resources = pop_flag("--resources")
    no_destruction = pop_flag("--no-des")
    no_foundation = pop_flag("--no-foun")
    debug = pop_flag("--debug")
    workers = pop_value("--workers", 16, int)
    names = []
    while "--name" in argv:
        i = argv.index("--name")
        names.append(argv[i + 1])
        del argv[i:i + 2]

    if argv:
        print(
            f"usage: {sys.argv[0]} [--resources] [--name BUILDING]... [--no-des] [--no-foun] [--debug] [--workers N]\n"
            "--resources builds the resources in config/resources.json (into resources_mod) instead of the buildings.\n"
            "No args builds everything: every living building, every destructible "
            "building's destruction animation, and every foundation family, all read "
            "from config/buildings.json as-is.\n"
            "--name restricts to specific building(s) (repeatable) instead of the whole set.\n"
            "--debug dumps every layer (Diffuse/Damage/AmbientOcclusion/Height/Normals/"
            "PlayerColor/FootprintGuide) as PNGs under debug/ next to this script, named "
            "after the frame they belong to - the exact pixels handed to the PSD, before "
            "conversion, for inspecting without opening a PSD editor.\n"
            "\n"
            "config/buildings.json is the only source of building names and settings: "
            "to add a new .gox, add its entry there by hand."
        )
        sys.exit(1)

    debug_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "debug") if debug else None
    if debug_dir is not None:
        print(f"--debug: dumping layer PNGs to {debug_dir}")

    if resources:
        with open(RESOURCE_CONFIG_PATH) as f:
            resource_keys = names or sorted(json.load(f))
        if not names:
            skipped = [k for k in resource_keys if not os.path.isfile(f"{DIRS.GOX_DIR}/{load_resource_config(k).get('gox') or k}.gox")]
            resource_keys = [k for k in resource_keys if k not in skipped]
            if skipped:
                print(f"Skipping {len(skipped)} resource(s) with no .gox in {DIRS.GOX_DIR}: {', '.join(skipped)}")
        from concurrent.futures import ThreadPoolExecutor, as_completed
        ok, failed = {}, {}
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = {pool.submit(build_and_install_resource, k, DIRS.MOD_RESOURCES, debug_dir): k for k in resource_keys}
            for future in as_completed(futures):
                k = futures[future]
                try:
                    ok[k] = future.result()
                except Exception as e:
                    failed[k] = e
                    print(f"[{k}] FAILED: {e}")
        _report("Resources", ok, failed, len(resource_keys))
        thumb = DIRS.SETTINGS.get("thumbnail")
        if thumb and load_resource_config(thumb):
            make_thumbnail(thumb, DIRS.MOD_RESOURCES, resource=True)
        sys.exit(0)

    all_config = building_config.load_all()

    def has_gox(key):
        return os.path.isfile(f"{DIRS.GOX_DIR}/{all_config[key].get('gox') or key}.gox")

    living_names = names or sorted(
        k for k, v in all_config.items() if not v.get("empty") and not v.get("foundation")
    )
    if not names:
        # A gox_dir with only some models builds just those; the rest are skipped.
        skipped = [n for n in living_names if not has_gox(n)]
        living_names = [n for n in living_names if has_gox(n)]
        if skipped:
            print(f"Skipping {len(skipped)} building(s) with no .gox in {DIRS.GOX_DIR}: {', '.join(skipped)}")
    ok, failed = build_many(living_names, workers=workers, debug_dir=debug_dir)
    _report("Living buildings", ok, failed, len(living_names))

    if not names:
        empty_names = sorted(k for k, v in all_config.items() if v.get("empty"))
        ok, failed = build_many(empty_names, workers=workers, debug_dir=debug_dir)
        _report("Empty placeholders", ok, failed, len(empty_names))

    if not no_destruction:
        destructible_names = [n for n in living_names if all_config.get(n, {}).get("destructible")]
        ok, failed = build_many_destruction(destructible_names, workers=workers, debug_dir=debug_dir)
        _report("Destruction", ok, failed, len(destructible_names))

    if not no_foundation:
        ok, failed = build_many_foundation(
            workers=workers, only_names=set(names) if names else set(living_names), debug_dir=debug_dir,
        )
        total = len(ok) + len(failed)
        _report("Foundations", ok, failed, total)

    thumb = DIRS.SETTINGS.get("thumbnail")
    if thumb and building_config.load(thumb):
        make_thumbnail(thumb, DIRS.MOD_SLD_TEST)
