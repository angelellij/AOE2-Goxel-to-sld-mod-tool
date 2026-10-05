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

_display_num_counter = itertools.count(100)
_display_num_lock = threading.Lock()


def _next_display_num():
    with _display_num_lock:
        return next(_display_num_counter)


def convert_via_wine(src_dir, building_name, attempts=3):
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
            f.write("{}")

        display_num = _next_display_num()
        try:
            subprocess.run(
                ["xvfb-run", "-n", str(display_num), "wine", "DESpriteTool.exe", relative_batch_dir],
                cwd=DIRS.SPRITES_TOOL,
                check=True,
                capture_output=True,
                text=True,
            )
            sld_files = [f for f in os.listdir(dest_dir) if f.endswith(".sld")]
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
    installed = []
    for sld_file in sld_files:
        variant = sld_file.rsplit("_", 1)[-1].split(".")[0]
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
            f"no config/buildings/{building_name}.json - run "
            f"gen_building_config.py, or check its gap report if "
            f"{building_name!r} isn't in rename.py yet"
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
            if config.get("box_from"):
                from gox_reader import read_gox
                model = read_gox(f"{DIRS.MAIN}/{DIRS.GOX}/{gox_name}.gox")
                model.box = read_gox(f"{DIRS.MAIN}/{DIRS.GOX}/{config['box_from']}.gox").box
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

        dest_dir, sld_files = convert_via_wine(psd_dir, building_name)
        print(f"[{building_name}] converted: {sld_files}")

        if footprint_guide is not None:
            for sld_file in sld_files:
                if sld_file.endswith("_x1.sld"):
                    patch_sld_shadow_if_enabled(f"{dest_dir}/{sld_file}", footprint_guide)

        target_names = building_config.target_names(config)
        installed = install(dest_dir, sld_files, target_names, mod_name)
        print(f"[{building_name}] installed into {mod_name!r}: {installed}")
        return installed


RESOURCE_CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config", "resources.json")


def load_resource_config(key):
    with open(RESOURCE_CONFIG_PATH) as f:
        all_config = json.load(f)
    return all_config.get(key)


def build_and_install_resource(key, mod_name=DIRS.MOD_SLD_TEST, frame_count=10, debug_dir=None):
    config = load_resource_config(key)
    if config is None:
        raise ValueError(f"no {key!r} entry in config/resources.json - run gen_resource_config.py")
    tile_size = config["tile_size"]
    gox_name = config.get("gox") or key

    with tempfile.TemporaryDirectory(prefix=f"{key}_psd_") as psd_dir:
        first_path = f"{psd_dir}/{key}_0000.psd"
        layers = build_psd.build_layers(key, tile_size, gox_name=gox_name)
        _canvas_size, footprint_guide = build_psd.write_psd(layers, first_path, key, tile_size, debug_dir=debug_dir)

        for i in range(1, frame_count):
            shutil.copy(first_path, f"{psd_dir}/{key}_{i:04d}.psd")
        print(f"[{key}] wrote {frame_count} frame(s) to {psd_dir}")

        dest_dir, sld_files = convert_via_wine(psd_dir, key)
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
        raise ValueError(f"no config for {building_name!r} - run gen_building_config.py")
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

        dest_dir, sld_files = convert_via_wine(psd_dir, d_key)
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
        raise ValueError(f"no config for {building_name!r} - run gen_building_config.py")
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
            dest_dir, sld_files = convert_via_wine(psd_dir, d_key)
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
        raise ValueError(f"no {f_key!r} entry in config/buildings.json - no foundation target to install as")
    target_names = building_config.target_names(f_config)

    config = building_config.load(building_name)
    if config is None:
        raise ValueError(f"no config for {building_name!r} - run gen_building_config.py")
    tile_size = config["tile_size"]
    angle_x = config.get("camera_angle_x", 60)
    angle_y = config.get("camera_angle_y", 45)
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

        dest_dir, sld_files = convert_via_wine(psd_dir, f_key)
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

    families = foundation_families()
    if only_names is not None:
        families = {f_key: name for f_key, name in families.items() if name in only_names}
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
            f"usage: {sys.argv[0]} [--name BUILDING]... [--no-des] [--no-foun] [--debug] [--workers N]\n"
            "No args builds everything: every living building, every destructible "
            "building's destruction animation, and every foundation family, all read "
            "from config/buildings.json as-is.\n"
            "--name restricts to specific building(s) (repeatable) instead of the whole set.\n"
            "--debug dumps every layer (Diffuse/Damage/AmbientOcclusion/Height/Normals/"
            "PlayerColor/FootprintGuide) as PNGs under debug/ next to this script, named "
            "after the frame they belong to - the exact pixels handed to the PSD, before "
            "conversion, for inspecting without opening a PSD editor.\n"
            "\n"
            "config/buildings.json is a hand-editable config, not regenerated by this "
            "script. After adding a new .gox or changing one you want picked up, run "
            "gen_building_config.py yourself (it preserves your existing tile_size/"
            "frame_count/camera_angle overrides, only fills in missing ones)."
        )
        sys.exit(1)

    debug_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "debug") if debug else None
    if debug_dir is not None:
        print(f"--debug: dumping layer PNGs to {debug_dir}")

    all_config = building_config.load_all()

    living_names = names or sorted(
        k for k, v in all_config.items() if not v.get("empty") and not v.get("foundation")
    )
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
            workers=workers, only_names=set(names) if names else None, debug_dir=debug_dir,
        )
        total = len(ok) + len(failed)
        _report("Foundations", ok, failed, total)
