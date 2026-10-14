# SPDX-License-Identifier: GPL-3.0-or-later
"""Viewport drawing: the path on the floor, footsteps, a mark every second, and box labels."""

import math

import blf
import bpy
import gpu
import numpy as np
from bpy_extras.view3d_utils import location_3d_to_region_2d
from gpu_extras.batch import batch_for_shader
from mathutils import Vector

from . import floor, rig, solve

PATH = (0.25, 0.85, 1.0, 0.95)
OFF_FLOOR = (1.0, 0.3, 0.25, 0.95)
STEP_L = (1.0, 1.0, 1.0, 0.30)
STEP_R = (0.85, 0.95, 1.0, 0.22)
TICK = (1.0, 0.85, 0.3, 0.95)
HERE = (1.0, 0.85, 0.3, 0.9)
LABEL = {"START": ((0.35, 1.0, 0.45, 1.0), "Start"), "END": ((1.0, 0.4, 0.35, 1.0), "End"),
         "WAY": ((1.0, 0.85, 0.3, 1.0), None)}

_handles = []
_cache = {}      # rig name -> (plan id, batches, labels)


def _shaders():
    return gpu.shader.from_builtin("POLYLINE_UNIFORM_COLOR"), gpu.shader.from_builtin("UNIFORM_COLOR")


def _time_ticks(pl):
    """Path positions at every whole second of walking (waits counted once)."""
    out = []
    t = 1.0
    while t < pl.duration:
        s = pl.s_at(t)
        if not out or abs(out[-1][1] - s) > 0.05:
            out.append((t, s))
        t += 1.0
    return out


def _build(cam, pl):
    lift = 0.02
    xyz = np.column_stack([pl.xy, pl.ground + lift])
    seg_ok, seg_bad = [], []
    for i in range(len(xyz) - 1):
        (seg_ok if pl.hit[i] or not len(pl.hit) or not pl.hit.any() else seg_bad).extend((xyz[i], xyz[i + 1]))
    steps_l, steps_r = [], []
    for p in pl.plants:
        tris = floor.footprint_tris(p.co, p.yaw, p.side)
        (steps_l if p.side < 0 else steps_r).extend(tris)
    ticks, labels = [], []
    for t, s in _time_ticks(pl):
        x, y = pl.xy_at(s)
        z = pl.ground_at(s) + lift
        a = pl.yaw_at(s)
        side = Vector((math.sin(a), -math.cos(a), 0.0)) * 0.22
        c = Vector((x, y, z))
        ticks.extend((c - side, c + side))
        labels.append((c + side * 1.4, f"{t:g}s", TICK))
    for it in cam.stride.points:
        if it.obj is None:
            continue
        col, text = LABEL[it.role]
        if text is None:
            text = str(list(cam.stride.points).index(it))
            if it.wait > 0:
                text += f"  wait {it.wait:g}s"
        labels.append((it.obj.matrix_world.translation + Vector((0, 0, 1.95)), text, col))
    return {"ok": seg_ok, "bad": seg_bad, "left": steps_l, "right": steps_r, "ticks": ticks}, labels


def _draw_3d():
    ctx = bpy.context
    sc = ctx.scene
    if sc is None or not sc.stride.show_path:
        return
    rigs = rig.all_rigs(sc)
    if not rigs:
        return
    line, flat = _shaders()
    region = ctx.region
    gpu.state.blend_set("ALPHA")
    gpu.state.depth_test_set("NONE")
    for cam in rigs:
        if cam.hide_get() and not cam.stride.points:
            continue
        pl = solve.cached_plan(cam)
        if pl is None:
            continue
        key = id(pl)
        if _cache.get(cam.name, (None,))[0] != key:
            _cache[cam.name] = (key, *_build(cam, pl))
        _key, geo, _labels = _cache[cam.name]
        if sc.stride.show_steps:
            for k, col in (("left", STEP_L), ("right", STEP_R)):
                if geo[k]:
                    flat.uniform_float("color", col)
                    batch_for_shader(flat, "TRIS", {"pos": geo[k]}).draw(flat)
        line.uniform_float("viewportSize", (region.width, region.height))
        for k, col, w in (("ok", PATH, 2.5), ("bad", OFF_FLOOR, 3.0), ("ticks", TICK, 2.0)):
            if geo[k] and (k != "ticks" or sc.stride.show_time):
                line.uniform_float("lineWidth", w)
                line.uniform_float("color", col)
                batch_for_shader(line, "LINES", {"pos": geo[k]}).draw(line)
        # where the walker is on the current frame
        f = solve.fps(sc)
        t = (sc.frame_current - cam.stride.frame_start) / f
        s = pl.s_at(t)
        x, y = pl.xy_at(s)
        z = pl.ground_at(s) + 0.02
        ring = [Vector((x + 0.3 * math.cos(a), y + 0.3 * math.sin(a), z))
                for a in (math.tau * i / 32 for i in range(33))]
        line.uniform_float("lineWidth", 3.0)
        line.uniform_float("color", HERE)
        batch_for_shader(line, "LINE_STRIP", {"pos": ring}).draw(line)
    gpu.state.blend_set("NONE")


def _draw_2d():
    ctx = bpy.context
    sc = ctx.scene
    if sc is None or not sc.stride.show_path:
        return
    region, rv3d = ctx.region, ctx.region_data
    if rv3d is None:
        return
    font = 0
    blf.size(font, 13 * ctx.preferences.view.ui_scale)
    for name, (_key, _geo, labels) in list(_cache.items()):
        cam = bpy.data.objects.get(name)
        if cam is None or not rig.is_rig(cam) or cam.name not in sc.objects:
            continue
        for co, text, col in labels:
            if text.endswith("s") and text[:-1].replace(".", "").isdigit() and not sc.stride.show_time:
                continue
            p = location_3d_to_region_2d(region, rv3d, co)
            if p is None:
                continue
            blf.color(font, *col)
            w, _h = blf.dimensions(font, text)
            blf.position(font, p.x - w / 2, p.y, 0)
            blf.draw(font, text)


def invalidate(name=None):
    if name is None:
        _cache.clear()
    else:
        _cache.pop(name, None)


def register():
    _handles.append((bpy.types.SpaceView3D.draw_handler_add(_draw_3d, (), "WINDOW", "POST_VIEW"), "WINDOW"))
    _handles.append((bpy.types.SpaceView3D.draw_handler_add(_draw_2d, (), "WINDOW", "POST_PIXEL"), "WINDOW"))


def unregister():
    for h, region in _handles:
        bpy.types.SpaceView3D.draw_handler_remove(h, region)
    _handles.clear()
    _cache.clear()
