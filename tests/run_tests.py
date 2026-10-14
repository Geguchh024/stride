# SPDX-License-Identifier: GPL-3.0-or-later
"""Headless test suite.

    blender -b --factory-startup --python tests/run_tests.py

Exits with a non-zero status when any test fails.
"""

import math
import os
import sys
import tempfile
import time
import traceback

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import bpy  # noqa: E402
import numpy as np  # noqa: E402
from mathutils import Vector  # noqa: E402

import stride  # noqa: E402

stride.register()
from stride import (anatomy, arms, clips, handlers, handmesh, handposes, items, mathkit, motion, ops,  # noqa: E402,F401
                    pose, props, rig, solve, walk)

TMP = tempfile.mkdtemp(prefix="stride_tests_")
results = []


def test(fn):
    results.append(fn)
    return fn


def reset():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    solve._plans.clear()


def new_rig(length=6.0, yaw=math.pi / 2):
    cam = rig.create(bpy.context, (0.0, 0.0, 0.0), yaw, length=length)
    bpy.context.view_layer.update()
    return cam


def add_clip(cam, clip_id, frame=10, duration=None, mirror=False):
    props._suspend["on"] = True
    try:
        it = cam.stride.clips.add()
        it.clip = clip_id
        it.frame = frame
        it.duration = duration or clips.CLIP_BY_ID[clip_id].default_duration
        it.mirror = mirror
    finally:
        props._suspend["on"] = False
    return it


def cam_at(cam, frame):
    bpy.context.scene.frame_set(frame)
    return cam.matrix_world.copy()


# -- the walk (no bpy objects) -----------------------------------------------------------

@test
def straight_walk_timing():
    g = walk.Gait(speed=1.4, accel=1.0, start_delay=0.0)
    pl = walk.solve([walk.Point((0, 0, 0)), walk.Point((0, 10, 0))], g)
    assert abs(pl.length - 10.0) < 0.01, pl.length
    # cruising at speed with a 1 m/s² start and stop: 10/1.4 + 1.4/1.0
    expect = 10 / 1.4 + 1.4 / 1.0
    assert abs(pl.duration - expect) < 0.15, (pl.duration, expect)
    assert pl.v.max() <= 1.4 + 1e-6
    assert pl.s_at(pl.duration + 5) == pl.length
    assert pl.speed_at(-1) == 0 and pl.speed_at(pl.duration + 1) == 0


@test
def waits_and_waypoints():
    g = walk.Gait(start_delay=1.0)
    pts = [walk.Point((0, 0, 0)), walk.Point((2, 4, 0), wait=2.0), walk.Point((0, 8, 0))]
    pl = walk.solve(pts, g)
    plain = walk.solve([walk.Point((0, 0, 0)), walk.Point((2, 4, 0)), walk.Point((0, 8, 0))],
                       walk.Gait(start_delay=1.0))
    assert pl.duration > plain.duration + 2.0, (pl.duration, plain.duration)
    # the path passes through the waypoint
    d = np.min(np.linalg.norm(pl.xy - np.array([2.0, 4.0]), axis=1))
    assert d < 0.03, d
    # standing at the start for the delay
    assert pl.s_at(0.9) == 0.0
    # standing at the waypoint while waiting
    i = int(np.argmin(np.linalg.norm(pl.xy - np.array([2.0, 4.0]), axis=1)))
    s_wp = pl.s[i]
    times = np.linspace(0, pl.duration, 2000)
    at_wp = [t for t in times if abs(pl.s_at(t) - s_wp) < 0.03]
    assert max(at_wp) - min(at_wp) > 1.9


@test
def ground_without_floor_interpolates_boxes():
    pl = walk.solve([walk.Point((0, 0, 0)), walk.Point((0, 10, 2.0))], walk.Gait())
    mid = pl.ground_at(5.0)
    assert abs(mid - 1.0) < 0.05, mid
    assert not pl.hit.any()


@test
def footsteps_alternate():
    pl = walk.solve([walk.Point((0, 0, 0)), walk.Point((0, 7.2, 0))], walk.Gait(step=0.72))
    sides = [p.side for p in pl.plants]
    assert sides[:2] == [-1, 1] and sides[-2:] == [-1, 1], sides
    mid = sides[2:-2]
    assert all(a != b for a, b in zip(mid, mid[1:])), mid
    assert abs(pl.step - 0.72) < 0.01


@test
def mathkit_helpers():
    assert mathkit.min_jerk(0) == 0 and mathkit.min_jerk(1) == 1 and abs(mathkit.min_jerk(0.5) - 0.5) < 1e-9
    x = np.linspace(0, 20, 500)
    n = mathkit.noise1(x)
    assert np.abs(n).max() <= 1.0 and n.std() > 0.05
    d = mathkit.damp(np.r_[np.zeros(10), np.ones(200)], 1 / 24, 0.2)
    assert d[9] == 0 and abs(d[-1] - 1) < 1e-3 and np.all(np.diff(d) >= -1e-9)
    cr = mathkit.catmull_rom([(0, 0), (1, 1), (2, 0)], per_segment=10)
    assert np.allclose(cr[0], (0, 0)) and np.allclose(cr[-1], (2, 0)) and np.allclose(cr[10], (1, 1))


@test
def look_moves():
    pl = walk.solve([walk.Point((0, 0, 0)), walk.Point((0, 0.001, 0))], walk.Gait())
    head = motion.Head(shake=0.0, breathing=0.0)
    times = np.arange(0, 6, 1 / 24)
    lk = motion.Look(start=1.0, duration=3.0, kind="LEFT", amount=60.0)
    frames = motion.simulate(pl, head, [lk], times)
    yaw = np.array([f.head_rot[0] for f in frames])
    assert abs(math.degrees(yaw[int(2.5 * 24)]) - 60) < 3, math.degrees(yaw[int(2.5 * 24)])
    assert abs(math.degrees(yaw[int(5.5 * 24)])) < 2
    # the camera turns left (towards +X rotated CCW): its view direction gains -X when facing +Y
    view = frames[int(2.5 * 24)].camera.to_3x3() @ Vector((0, 0, -1))
    assert view.x < -0.7, view


@test
def turn_to_end_arrow():
    end_yaw = 0.0                     # face +X after walking along +Y
    pts = [walk.Point((0, 0, 0)), walk.Point((0, 4, 0), yaw=end_yaw)]
    pl = walk.solve(pts, walk.Gait())
    head = motion.Head(shake=0.0, breathing=0.0)
    times = np.arange(0, pl.duration + 3.0, 1 / 24)
    fr = motion.simulate(pl, head, [], times)[-1]
    view = fr.camera.to_3x3() @ Vector((0, 0, -1))
    assert view.x > 0.95, view


# -- rig, floors and baking -------------------------------------------------------------------

@test
def create_and_bake_walk():
    reset()
    cam = new_rig(6.0)
    pl, frames = solve.update(cam)
    assert pl is not None and abs(pl.length - 6.0) < 0.05
    sc = bpy.context.scene
    first, last = solve.frame_range(cam, sc, pl)
    assert len(frames) == last - first + 1
    # the keys reproduce the solved camera
    for i in (0, len(frames) // 2, len(frames) - 1):
        m = cam_at(cam, first + i)
        assert (m.translation - frames[i].camera.translation).length < 1e-3
        a = m.to_3x3() @ Vector((0, 0, -1))
        b = frames[i].camera.to_3x3() @ Vector((0, 0, -1))
        assert a.angle(b) < 1e-3
    end = cam_at(cam, last)
    assert abs(end.translation.y - 6.0) < 0.05 and abs(end.translation.z - 1.62) < 0.03, end.translation
    # nothing the walk adds renders
    for it in cam.stride.points:
        assert it.obj.hide_render
    for it in cam.stride.floors:
        assert it.obj.hide_render


@test
def stairs_lift_the_camera():
    reset()
    cam = new_rig(2.0)
    rig.add_stairs(cam, Vector((0, 0, 0)), 0.0, steps=10, rise=0.17, run=0.28, width=1.4, before=2.0, after=3.0)
    end = cam.stride.points[-1].obj
    end.location = (0, 2.0 + 2.8 + 2.0, 1.7)
    bpy.context.view_layer.update()
    pl, frames = solve.update(cam)
    assert pl.hit.all()
    z0, z1 = frames[0].camera.translation.z, frames[-1].camera.translation.z
    assert abs((z1 - z0) - 1.7) < 0.05, (z0, z1)
    on_stairs = pl.v[(pl.s > 2.6) & (pl.s < 4.2)].mean()
    flat = pl.v[(pl.s > 5.2) & (pl.s < 5.8)].max()
    assert on_stairs < flat * 0.75, (on_stairs, flat)


@test
def floor_edit_updates_walk():
    reset()
    cam = new_rig(6.0)
    fl = cam.stride.floors[0].obj
    pl0 = solve.plan(cam)
    for v in fl.data.vertices:
        if v.co.y > 3.0:
            v.co.z = 0.5
    fl.data.update()
    bpy.context.view_layer.update()
    pl1 = solve.plan(cam)
    assert abs(pl1.ground_at(5.0) - 0.5) < 0.01 and abs(pl0.ground_at(5.0)) < 0.01


@test
def live_update_on_box_move():
    reset()
    cam = new_rig(6.0)
    solve.update(cam)
    end = cam.stride.points[-1].obj
    end.location.x = 3.0
    bpy.context.view_layer.update()
    # the depsgraph handler queues the rig; run the queued update now (timers don't run headless)
    assert cam.name in handlers._pending
    handlers.flush_all()
    m = cam_at(cam, solve.frame_range(cam, bpy.context.scene, solve.cached_plan(cam))[1])
    assert abs(m.translation.x - 3.0) < 0.05, m.translation


@test
def operators():
    reset()
    win = bpy.context.window_manager.windows[0] if bpy.context.window_manager.windows else None
    with bpy.context.temp_override(window=win) if win else _null():
        assert bpy.ops.stride.create() == {"FINISHED"}
        cam = rig.all_rigs()[0]
        assert bpy.ops.stride.add_waypoint() == {"FINISHED"}
        assert len(cam.stride.points) == 3 and cam.stride.points[1].role == "WAY"
        bpy.context.scene.stride.stairs_steps = 4
        assert bpy.ops.stride.add_floor(kind="STAIRS") == {"FINISHED"}
        assert len(cam.stride.floors) == 2
        bpy.context.scene.stride.new_look = "AROUND"
        assert bpy.ops.stride.add_look() == {"FINISHED"}
        assert cam.stride.looks[0].kind == "AROUND" and cam.stride.looks[0].duration == 4.5
        assert bpy.ops.stride.fit_range() == {"FINISHED"}
        assert bpy.ops.stride.footstep_markers() == {"FINISHED"}
        steps = [m for m in bpy.context.scene.timeline_markers if m.name.startswith("step ")]
        assert len(steps) >= 6 and {m.name for m in steps} == {"step L", "step R"}
        frames = sorted(m.frame for m in steps)
        assert all(b > a for a, b in zip(frames, frames[1:]))
        cam.stride.point_index = 1
        assert bpy.ops.stride.remove_point() == {"FINISHED"}
        assert len(cam.stride.points) == 2
        assert bpy.ops.stride.delete("EXEC_DEFAULT") == {"FINISHED"}
        assert not rig.all_rigs()
        assert not [o for o in bpy.data.objects if o.name.startswith("POV")]


class _null:
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


@test
def walking_styles():
    reset()
    cam = new_rig(6.0)
    cam.stride.style = "RUN"
    assert abs(cam.stride.speed - 4.2) < 1e-5
    pl, _ = solve.update(cam)
    cam.stride.style = "STROLL"
    pl2, _ = solve.update(cam)
    assert pl2.duration > pl.duration * 2


# -- arms --------------------------------------------------------------------------------------

@test
def arm_mesh_and_weights():
    data = arms._arm_data("AVERAGE")
    w = data["weights"]
    total = sum(w.values())
    assert np.allclose(total, 1.0, atol=1e-4)
    for bone in ("hand", "index.03", "thumb.03", "forearm_twist", "upper_arm"):
        assert w[bone].max() > 0.9, bone
    assert (data["masks"]["nail"] > 0.5).sum() > 150
    # a closed, consistently wound surface: every edge shared by two faces
    q = data["quads"]
    e = np.sort(np.vstack([q[:, [0, 1]], q[:, [1, 2]], q[:, [2, 3]], q[:, [3, 0]]]), axis=1)
    _, counts = np.unique(e, axis=0, return_counts=True)
    assert (counts == 2).mean() > 0.999


@test
def arm_ik_reaches():
    reset()
    cam = new_rig()
    rig_ob = arms.add(cam, watch=True)
    sk = pose.Skeleton(rig_ob)
    for side, target in (("R", Vector((0.12, 0.36, -0.30))), ("L", Vector((-0.10, 0.40, -0.25)))):
        basis, poses = {}, {}
        rot = pose.frame_from((0.0, 1.0, 0.3), (0.0, 0.0, -1.0) if side == "R" else (0.3, 0.0, -1.0))
        sk.solve_arm(side, target, rot, (0.6 if side == "R" else -0.6, -0.3, -1.0), sk.fingers("FIST"),
                     basis, poses)
        hand = poses["hand." + side]
        assert (hand.translation - target).length < 1e-3, (side, hand.translation)
        assert (hand.to_3x3() @ Vector((0, 1, 0))).angle(rot @ Vector((0, 1, 0))) < 1e-3
        # Blender agrees with the Python skeleton
        for pb in rig_ob.pose.bones:
            pb.rotation_quaternion = basis.get(pb.name, pose.IDENTITY)
        bpy.context.view_layer.update()
        blender = rig_ob.pose.bones["hand." + side].matrix
        assert (blender.translation - target).length < 1e-3
        tip = rig_ob.pose.bones["index.03." + side].matrix
        assert (tip.translation - poses["index.03." + side].translation).length < 1e-4
    assert any(o.get("stride_watch") for o in rig_ob.children)


@test
def sleeves_stay_on_the_arms():
    """Every sleeve, posed and with its thickness, stays within reach of the body."""
    reset()
    cam = new_rig(4.0)
    arms.add(cam)
    add_clip(cam, "WAVE", frame=10)
    solve.update(cam)
    sc = bpy.context.scene
    from stride import materials
    for sleeve in [s[0] for s in materials.SLEEVES if s[6] != "none"]:
        cam.stride.sleeve = sleeve
        for frame in (1, 40):
            sc.frame_set(frame)
            dg = bpy.context.evaluated_depsgraph_get()
            body = cam.stride.arms.matrix_world.translation
            for ob in arms.sleeve_meshes(cam):
                me = ob.evaluated_get(dg).to_mesh()
                co = np.empty(len(me.vertices) * 3)
                me.vertices.foreach_get("co", co)
                ob.evaluated_get(dg).to_mesh_clear()
                world = np.array(ob.matrix_world) @ np.c_[co.reshape(-1, 3), np.ones(len(co) // 3)].T
                reach = np.linalg.norm(world[:3].T - np.array(body), axis=1).max()
                assert reach < 1.2, (sleeve, frame, ob.name, reach)


@test
def every_action_bakes():
    reset()
    cam = new_rig(10.0)
    arms.add(cam)
    t = 0
    for c in clips.CLIPS:
        add_clip(cam, c.id, frame=10 + t)
        t += int(c.default_duration * 24) + 12
    add_clip(cam, "PHONE", frame=10 + t, mirror=True)
    t0 = time.time()
    pl, frames = solve.update(cam)
    took = time.time() - t0
    assert took < 15.0, took
    rig_ob = cam.stride.arms
    bag = solve.bake.channelbag(rig_ob, "x")
    paths = {fc.data_path for fc in bag.fcurves}
    assert 'pose.bones["index.02.R"].rotation_quaternion' in paths
    # props appear only while their action runs
    cig = next(o for o in items.owned(cam) if o["stride_item"] == "CIGARETTE")
    smoke_use = next(it for it in cam.stride.clips if it.clip == "SMOKE")
    sc = bpy.context.scene
    sc.frame_set(smoke_use.frame + 48)
    assert not cig.hide_render
    sc.frame_set(smoke_use.frame + int(smoke_use.duration * 24) + 30)
    assert cig.hide_render
    for c in clips.CLIPS:
        for item_id, _grip in c.props.values():
            assert any(o["stride_item"] == item_id for o in items.owned(cam)), item_id


@test
def smoking_glows_and_exhales():
    reset()
    cam = new_rig(4.0)
    arms.add(cam)
    use = add_clip(cam, "SMOKE", frame=10, duration=7.0)
    solve.update(cam)
    sc = bpy.context.scene
    cig = next(o for o in items.owned(cam) if o["stride_item"] == "CIGARETTE")
    smoke = next(o for o in items.owned(cam) if o["stride_item"] == "SMOKE")
    f = solve.fps(sc)
    sc.frame_set(use.frame + int(2.5 * f))     # mid drag
    glow = cig["ember"]
    sc.frame_set(use.frame + int(5.0 * f))     # lowered, breathing out
    assert glow > 0.9 and cig["ember"] < 0.3, (glow, cig["ember"])
    assert smoke["density"] > 0.05 and not smoke.hide_render
    # the filter is at the lips during the drag
    sc.frame_set(use.frame + int(2.4 * f))
    head = cam.matrix_world @ motion.CAMERA_BASE.inverted()
    mouth = head @ Vector(clips.MOUTH)
    assert (cig.matrix_world.translation - mouth).length < 0.01, (cig.matrix_world.translation - mouth).length


@test
def clip_time_warp():
    c = clips.CLIP_BY_ID["SMOKE"]
    scale, cycles = clips.expand(c, c.length)
    assert scale == 1.0 and cycles == 0
    span = c.loop[1] - c.loop[0]
    scale, cycles = clips.expand(c, c.length + 2 * span)
    assert cycles == 2 and abs(scale - 1.0) < 1e-9
    # the end of a long use plays the clip's ending
    d = c.length + 2 * span
    assert abs(clips.warp(c, d, d) - c.length) < 1e-9
    assert abs(clips.warp(c, c.loop[1] + span * 0.5, d) - (c.loop[0] + span * 0.5)) < 1e-9


@test
def action_library_is_consistent():
    ids = set()
    for c in clips.CLIPS:
        assert c.id not in ids, c.id
        ids.add(c.id)
        assert c.category in {k[0] for k in clips.CATEGORIES}, c.id
        for side, keys in c.hands.items():
            ts = [k.t for k in keys]
            assert ts == sorted(ts), (c.id, side)
            # hands come up from rest and go back to it, so actions can follow each other
            assert keys[0].at is None and keys[0].prop_to is None, (c.id, side)
            assert keys[-1].at is None and keys[-1].prop_to is None, (c.id, side)
            assert keys[-1].t <= c.length + 1e-9, (c.id, side)
            for k in keys:
                assert k.pose in handposes.POSES, (c.id, k.pose)
        for side, (item_id, grip) in c.props.items():
            assert item_id in items.BUILDERS and grip in items.GRIPS, c.id
        if c.loop:
            assert 0 <= c.loop[0] < c.loop[1] <= c.length, c.id


@test
def poses_are_complete():
    for name, p in handposes.POSES.items():
        assert set(p) == {"thumb", *handposes.FINGERS}, name
        q = handposes.quats(name)
        assert len(q) == 14
    m = handposes.mix("OPEN", "FIST", 0.5)
    assert abs(m["index"][0] - (2 + 85) / 2) < 1e-9


@test
def saved_file_plays_without_addon():
    reset()
    cam = new_rig(5.0)
    arms.add(cam)
    add_clip(cam, "WAVE", frame=10)
    solve.update(cam)
    path = os.path.join(TMP, "walk.blend")
    bpy.ops.wm.save_as_mainfile(filepath=path)
    sc = bpy.context.scene
    sc.frame_set(40)
    want = cam.matrix_world.copy()
    want_hand = (cam.stride.arms.matrix_world @ cam.stride.arms.pose.bones["hand.R"].matrix).translation
    stride.unregister()
    try:
        bpy.ops.wm.open_mainfile(filepath=path)
        sc = bpy.context.scene
        sc.frame_set(40)
        cam2 = bpy.data.objects["POV Camera"]
        arm2 = bpy.data.objects["POV Arms"]
        assert (cam2.matrix_world.translation - want.translation).length < 1e-4
        got_hand = (arm2.matrix_world @ arm2.pose.bones["hand.R"].matrix).translation
        assert (got_hand - want_hand).length < 1e-4
    finally:
        stride.register()


def main():
    failed = 0
    for fn in results:
        t = time.time()
        try:
            fn()
            print(f"PASS {fn.__name__} ({time.time() - t:.1f}s)")
        except Exception:
            failed += 1
            print(f"FAIL {fn.__name__}")
            traceback.print_exc()
    print(f"\n{len(results) - failed}/{len(results)} passed")
    sys.exit(1 if failed else 0)


main()
