# SPDX-License-Identifier: GPL-3.0-or-later
"""Live updates: re-solve a rig shortly after its boxes, floors or settings change."""

import time

import bpy
from bpy.app.handlers import persistent

from . import rig, solve

DELAY = 0.12          # quick pass: path, overlay and camera, while things are still moving
SETTLE = 0.6          # full pass with the hands once edits stop
_pending = set()
_settle = set()
_state = {"busy": False, "timer": False, "last": 0.0}


def request(cam):
    """Ask for a rig to be re-baked soon (edits arrive in bursts while dragging)."""
    if cam is None or not cam.stride.is_rig or not cam.stride.live:
        solve._plans.pop(getattr(cam, "name", ""), None)
        return
    _pending.add(cam.name)
    _state["last"] = time.monotonic()
    if not _state["timer"]:
        _state["timer"] = True
        bpy.app.timers.register(_flush, first_interval=DELAY)


def _run(names, light):
    for name in names:
        cam = bpy.data.objects.get(name)
        if cam is None or not rig.is_rig(cam):
            continue
        _state["busy"] = True
        try:
            solve.update(cam, light=light)
        except Exception as e:  # noqa: BLE001 - never kill the timer loop
            print(f"Stride: could not update {name}: {e}")
        finally:
            _state["busy"] = False


def _flush():
    """Quick pass for what changed, then wait for the edits to settle before posing the hands."""
    names = list(_pending)
    _pending.clear()
    if names:
        _run(names, light=True)
        _settle.update(names)
        _redraw()
    idle = time.monotonic() - _state["last"]
    if idle < SETTLE:
        return DELAY          # keep ticking so new edits get their quick pass promptly
    names = list(_settle)
    _settle.clear()
    _run(names, light=False)
    _redraw()
    _state["timer"] = False
    return None


def flush_all():
    """Run everything queued right now (tests, scripts)."""
    names = list(_pending | _settle)
    _pending.clear()
    _settle.clear()
    _run(names, light=False)


def _redraw():
    wm = bpy.context.window_manager
    for win in getattr(wm, "windows", ()):
        for area in win.screen.areas:
            if area.type in {"VIEW_3D", "TIMELINE", "DOPESHEET_EDITOR", "GRAPH_EDITOR"}:
                area.tag_redraw()


def _watched():
    """Objects and meshes whose edits move a rig: boxes and floors."""
    out = {}
    for cam in rig.all_rigs():
        r = cam.stride
        for it in list(r.points) + list(r.floors):
            ob = it.obj
            if ob is None:
                continue
            out[ob.name] = cam
            if ob.data is not None:
                out[("ME", ob.data.name)] = cam
        for it in r.looks:
            if it.target is not None:
                out[it.target.name] = cam
    return out


@persistent
def _on_depsgraph(scene, depsgraph):
    if _state["busy"]:
        return
    watched = None
    for up in depsgraph.updates:
        idb = up.id
        if not (up.is_updated_transform or up.is_updated_geometry):
            continue
        if isinstance(idb, bpy.types.Object):
            key = idb.original.name
        elif isinstance(idb, bpy.types.Mesh):
            key = ("ME", idb.original.name)
        else:
            continue
        if watched is None:
            watched = _watched()
            if not watched:
                return
        cam = watched.get(key)
        if cam is not None:
            solve._plans.pop(cam.name, None)
            request(cam)


@persistent
def _on_load(_dummy):
    solve._plans.clear()
    _pending.clear()


@persistent
def _on_undo(scene, _dummy=None):
    # undo restores boxes and keys together; only the drawing cache is stale
    solve._plans.clear()
    from . import overlay
    overlay.invalidate()


HANDLERS = (
    ("depsgraph_update_post", _on_depsgraph),
    ("load_post", _on_load),
    ("undo_post", _on_undo),
    ("redo_post", _on_undo),
)


def register():
    for name, fn in HANDLERS:
        getattr(bpy.app.handlers, name).append(fn)


def unregister():
    for name, fn in HANDLERS:
        lst = getattr(bpy.app.handlers, name)
        if fn in lst:
            lst.remove(fn)
    if bpy.app.timers.is_registered(_flush):
        bpy.app.timers.unregister(_flush)
    _state["timer"] = False
    _pending.clear()
    _settle.clear()
