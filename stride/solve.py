# SPDX-License-Identifier: GPL-3.0-or-later
"""From a rig's settings to keyframes: plan the walk, move body and head, pose the hands, bake."""

import math

import bpy
import numpy as np

from . import bake, floor, motion, walk

_plans = {}       # rig camera name -> last solved Plan (for the viewport overlay)


def fps(scene):
    return scene.render.fps / scene.render.fps_base


def points(cam):
    out = []
    for it in cam.stride.points:
        ob = it.obj
        if ob is None:
            continue
        yaw = ob.matrix_world.to_euler("XYZ").z + math.pi / 2
        use_yaw = (it.role == "START" and cam.stride.use_start_facing) or \
                  (it.role == "END" and cam.stride.use_end_facing)
        out.append(walk.Point(co=tuple(ob.matrix_world.translation), wait=it.wait if it.role == "WAY" else 0.0,
                              speed=it.speed, yaw=yaw if use_yaw else None))
    return out


def gait(cam):
    r = cam.stride
    return walk.Gait(speed=r.speed, step=r.step, eye=max(r.eye - r.crouch, 0.2), bob=r.bob, sway=r.sway,
                     roll=r.roll, accel=r.accel, stairs=r.stairs, stair_rhythm=r.stair_rhythm,
                     start_delay=r.start_delay)


def head(cam):
    r = cam.stride
    return motion.Head(look_ahead=r.look_ahead, lag=r.head_lag, pitch=r.pitch, follow_slope=r.follow_slope,
                       watch_step=r.watch_step, shake=r.shake, breathing=r.breathing, seed=r.seed)


def looks(cam, scene):
    f = fps(scene)
    r = cam.stride
    out = []
    for it in r.looks:
        target = tuple(it.target.matrix_world.translation) if it.target is not None else None
        if it.kind == "AT" and target is None:
            continue
        out.append(motion.Look(start=(it.frame - r.frame_start) / f, duration=it.duration, kind=it.kind,
                               amount=it.amount, target=target))
    return out


def floors(cam):
    return [it.obj for it in cam.stride.floors if it.obj is not None]


def plan(cam, depsgraph=None):
    depsgraph = depsgraph or bpy.context.evaluated_depsgraph_get()
    pts = points(cam)
    if len(pts) < 2:
        return None
    ground = floor.Ground(floors(cam), depsgraph)
    p = walk.solve(pts, gait(cam), ground if ground else None)
    _plans[cam.name] = p
    return p


def cached_plan(cam):
    p = _plans.get(cam.name)
    if p is None:
        try:
            p = plan(cam)
        except Exception:  # noqa: BLE001 - the overlay must never break drawing
            return None
    return p


def frame_range(cam, scene, pl, extra_end=0.0):
    """First and last frame to bake: the walk, the hold at the end, and every move and action."""
    r = cam.stride
    f = fps(scene)
    end_t = pl.duration + r.end_hold
    for it in r.looks:
        end_t = max(end_t, (it.frame - r.frame_start) / f + it.duration)
    for it in r.clips:
        end_t = max(end_t, (it.frame - r.frame_start) / f + it.duration + 0.5)
    end_t = max(end_t, extra_end)
    last = r.frame_start + int(math.ceil(end_t * f))
    if scene.frame_end > last:
        last = min(scene.frame_end, last + int(60 * f))
    return r.frame_start, last


def update(cam, scene=None, depsgraph=None, light=False):
    """Solve and bake one rig. Returns (plan, frames) or (None, None).

    ``light`` skips posing the hands (used while boxes are being dragged).
    """
    scene = scene or bpy.context.scene
    depsgraph = depsgraph or bpy.context.evaluated_depsgraph_get()
    pl = plan(cam, depsgraph)
    if pl is None:
        return None, None
    first, last = frame_range(cam, scene, pl)
    nums = np.arange(first, last + 1)
    times = (nums - first) / fps(scene)

    from . import animate
    hands = animate.Hands(cam, scene) if cam.stride.arms is not None else None
    if light and hands is not None and not hands.uses:
        light = False         # nothing for the hands to do but swing: cheap enough to keep live
    extra = hands.head_offset if hands is not None else None
    frames = motion.simulate(pl, head(cam), looks(cam, scene), times, extra_head=extra)

    bake.bake_object(cam, nums, [f.camera for f in frames], "POV Camera Walk")
    if hands is not None and not light:
        hands.bake(nums, frames)
    elif hands is not None:
        # keep the arms with the body while dragging; their poses catch up on the full pass
        bake.bake_object(cam.stride.arms, nums, [f.body for f in frames], "POV Arms Body")
    return pl, frames
