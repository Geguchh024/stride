# SPDX-License-Identifier: GPL-3.0-or-later
"""Posing the arms over time: hand actions on top of a walking arm swing, then baking.

Every frame: each hand is either at rest (hanging, swinging with the walk)
or following the keys of the action that holds it; the arm is solved to
reach, fingers take their pose, props follow the grip, and it is all keyed.
"""

import math
from dataclasses import dataclass

import numpy as np
from mathutils import Matrix, Quaternion, Vector

from . import bake, clips, handposes, items, motion, pose
from . import mathkit as mk

SMOKE_LIFE = 3.2


@dataclass
class State:
    wrist: Vector
    rot: Quaternion
    elbow: Vector
    fingers: dict
    lift: float = 0.0     # how much 'Hands in View' applies (0 at rest and at the mouth)


@dataclass
class Use:
    """One use of an action on the timeline."""
    clip: clips.Clip
    start: float
    duration: float
    mirror: bool
    head: float

    @property
    def end(self):
        return self.start + self.duration

    def side(self, track_side):
        return {"R": "L", "L": "R"}[track_side] if self.mirror else track_side

    def time(self, t):
        return clips.warp(self.clip, t - self.start, self.duration)


def _mirror(v):
    return Vector((-v[0], v[1], v[2]))


class Hands:
    def __init__(self, cam, scene):
        from . import solve
        self.cam = cam
        self.rig_ob = cam.stride.arms
        self.sk = pose.Skeleton(self.rig_ob)
        r = cam.stride
        f = solve.fps(scene)
        self.sway = r.hand_sway
        self.in_view = r.in_view
        # the camera's half field of view, up and down
        data = cam.data
        aspect = scene.render.resolution_y * scene.render.pixel_aspect_y / max(
            scene.render.resolution_x * scene.render.pixel_aspect_x, 1)
        sensor = data.sensor_width if data.sensor_fit != "VERTICAL" else data.sensor_height / max(aspect, 1e-6)
        self.half_v = math.atan(sensor * aspect / 2 / max(data.lens, 1e-3))
        self.uses = []
        for it in r.clips:
            c = clips.CLIP_BY_ID.get(it.clip)
            if c is not None:
                self.uses.append(Use(c, (it.frame - r.frame_start) / f, it.duration, it.mirror, it.head))
        self.uses.sort(key=lambda u: u.start)
        self._anchors = {}
        self._fingers = {}

    # -- head -------------------------------------------------------------------------

    def head_offset(self, t):
        yaw = pitch = 0.0
        for u in self.uses:
            if u.clip.head and u.start <= t <= u.end:
                y, p = motion.eval_keys(u.clip.head, u.time(t))
                yaw += (-y if u.mirror else y) * u.head
                pitch += p * u.head
        return yaw, pitch

    # -- hand states -------------------------------------------------------------------

    def finger_pose(self, name):
        q = self._fingers.get(name)
        if q is None:
            q = self._fingers[name] = handposes.POSES[name]
        return q

    def rest(self, side, fr, pose_name="LIMP"):
        sign = 1.0 if side == "R" else -1.0
        swing = 0.10 * min(fr.gait, 1.2) * math.cos(math.pi * fr.phase) * sign
        wrist = Vector((sign * 0.205, 0.01 + swing, -0.745 + 0.3 * abs(swing)))
        fingers = Vector((sign * 0.05, 0.12 + swing * 0.8, -1.0))
        palm = Vector((-sign, -0.3, 0.0))
        rot = pose.frame_from(fingers, palm).to_quaternion()
        return State(wrist, rot, Vector((sign * 0.25, -1.0, -0.3)), self.finger_pose(pose_name))

    def anchor(self, item_id, grip_id, pose_name, side):
        """Where a prop's tip sits in the hand bone's frame for a finger pose."""
        key = (item_id, grip_id, pose_name, side)
        a = self._anchors.get(key)
        if a is None:
            fingers = self.sk.fingers(pose_name)
            basis = {}
            for name, q in fingers.items():
                basis[name + "." + side] = q if side == "R" else pose.mirror_quat(q)
            poses = self.sk.fk(basis)
            g = items.grip_matrix(items.GRIPS[grip_id], poses, side, self.sk.length)
            tip = g @ Vector(items.TIPS.get(item_id, (0, 0, 0)))
            a = self._anchors[key] = poses["hand." + side].inverted() @ tip
        return a

    def key_state(self, use, track_side, key, fr, head_rel):
        side = use.side(track_side)
        if key.at is None and key.prop_to is None:
            return self.rest(side, fr, key.pose)
        flip = side != track_side
        fingers = Vector(key.fingers)
        palm = Vector(key.palm)
        elbow = Vector(key.elbow)
        if flip:
            fingers, palm, elbow = _mirror(fingers), _mirror(palm), _mirror(elbow)
        rot3 = pose.frame_from(fingers, palm)
        if key.prop_to is not None:
            target = Vector(key.prop_to)
            if flip:
                target = _mirror(target)
            target = head_rel @ target
            prop = use.clip.props.get(track_side)
            if prop is not None:
                local = self.anchor(prop[0], prop[1], key.pose, side)
                wrist = target - rot3 @ local
            else:
                wrist = target
        else:
            at = Vector(key.at)
            if flip:
                at = _mirror(at)
            wrist = head_rel @ at if key.head else at
        lift = 0.0 if (key.prop_to is not None or key.head) else 1.0
        return State(wrist, rot3.to_quaternion(), elbow, self.finger_pose(key.pose), lift)

    def track_state(self, use, track_side, keys, t, fr, head_rel):
        tc = use.time(t)
        if tc <= keys[0].t:
            return self.key_state(use, track_side, keys[0], fr, head_rel)
        for k0, k1 in zip(keys, keys[1:]):
            if tc <= k1.t:
                span = k1.t - k0.t
                u = mk.min_jerk((tc - k0.t) / span) if span > 1e-9 else 1.0
                a = self.key_state(use, track_side, k0, fr, head_rel)
                b = self.key_state(use, track_side, k1, fr, head_rel)
                if a.rot.dot(b.rot) < 0:
                    b.rot.negate()
                return State(a.wrist.lerp(b.wrist, u), a.rot.slerp(b.rot, u), a.elbow.lerp(b.elbow, u),
                             handposes.mix(a.fingers, b.fingers, u), a.lift + (b.lift - a.lift) * u)
        return self.key_state(use, track_side, keys[-1], fr, head_rel)

    def lift_into_view(self, wrist, head_rel, amount):
        """Swing a wrist up about the eyes until the hand sits inside the bottom of the frame.

        The hand is about 8 cm past the wrist, so aim for the hand's centre.
        """
        inv = head_rel.inverted()
        p = inv @ wrist
        dist = math.hypot(p.y, p.z)
        if p.y <= 0.05 or dist < 1e-6:
            return wrist
        below = math.atan2(-p.z, p.y)
        limit = self.half_v * 0.62
        if below <= limit:
            return wrist
        a = (below - limit) * amount
        c, s = math.cos(a), math.sin(a)
        q = Vector((p.x, p.y * c - p.z * s, p.y * s + p.z * c))
        return head_rel @ q

    def holder(self, side, t):
        """The action (and its track side) holding a hand at time t, latest start first."""
        for u in reversed(self.uses):
            if u.start <= t <= u.end:
                for ts in u.clip.hands:
                    if u.side(ts) == side:
                        return u, ts
        return None, None

    # -- baking ---------------------------------------------------------------------------

    def bake(self, nums, frames):
        sk = self.sk
        rig_ob = self.rig_ob
        n = len(frames)
        dt = frames[1].t - frames[0].t if n > 1 else 1 / 24
        body_yaw = np.unwrap([math.atan2(f.body.col[1][1], f.body.col[1][0]) for f in frames])
        yaw_rate = mk.damp(np.gradient(body_yaw, dt) if n > 1 else np.zeros(n), dt, 0.15)

        bone_q = {name: np.empty((n, 4)) for name in sk.names}
        prop_m = {}
        prop_vis = {}
        channels = {}
        for i, fr in enumerate(frames):
            t = fr.t
            head_rel = fr.body.inverted() @ fr.head
            basis, poses = {}, {}
            for side in ("R", "L"):
                use, ts = self.holder(side, t)
                if use is None:
                    st = self.rest(side, fr)
                else:
                    st = self.track_state(use, ts, use.clip.hands[ts], t, fr, head_rel)
                    if st.lift > 0 and self.in_view > 0:
                        st.wrist = self.lift_into_view(st.wrist, head_rel, st.lift * self.in_view)
                    # held hands bob a little with the steps and lag behind turns
                    sw = self.sway * min(fr.gait, 1.2)
                    st.wrist = st.wrist + Vector((
                        0.004 * sw * math.sin(math.pi * fr.phase + 0.5)
                        + mk.clamp(0.035 * yaw_rate[i], -0.04, 0.04) * self.sway,
                        0.0,
                        -0.005 * sw * math.cos(mk.TAU * fr.phase + 0.9)))
                fingers = sk.fingers(st.fingers)
                sk.solve_arm(side, st.wrist, st.rot.to_matrix(), st.elbow, fingers, basis, poses)
                if use is not None:
                    prop = use.clip.props.get(ts)
                    if prop is not None:
                        prop_m.setdefault(prop[0], [None] * n)[i] = items.grip_matrix(
                            items.GRIPS[prop[1]], poses, side, sk.length)
                        prop_vis.setdefault(prop[0], np.zeros(n, bool))[i] = True
            for name in sk.names:
                q = basis.get(name, pose.IDENTITY)
                if i and np.dot(bone_q[name][i - 1], q) < 0:
                    q = -q
                bone_q[name][i] = q
            # prop channels (ember glow, screen, light, breath)
            for u in self.uses:
                if not (u.start <= t <= u.end) or not u.clip.events:
                    continue
                tc = u.time(t)
                tp = u.time(frames[i - 1].t) if i else -1.0
                by_channel = {}
                for te, item, ch, v in u.clip.events:
                    by_channel.setdefault((item, ch), []).append((te, v))
                for (item, ch), evs in by_channel.items():
                    if ch in ("puff", "breath"):
                        for te, v in evs:
                            if (tp < te <= tc) or (tc < tp and te <= tc):
                                channels.setdefault(("SMOKE", "starts"), []).append((t, ch, fr.head.copy()))
                        continue
                    arr = channels.setdefault((item, ch), np.full(n, np.nan))
                    times = [e[0] for e in evs]
                    vals = [e[1] for e in evs]
                    arr[i] = float(np.interp(tc, times, vals))

        bake.bake_object(rig_ob, nums, [f.body for f in frames], "POV Arms Body")
        bag = bake.channelbag(rig_ob, "POV Arms Body")
        for name, arr in bone_q.items():
            bake.write_vector(bag, f'pose.bones["{name}"].rotation_quaternion', nums, arr, group=name)
        self._bake_props(nums, frames, prop_m, prop_vis, channels)

    def _bake_props(self, nums, frames, prop_m, prop_vis, channels):
        cam = self.cam
        used = set(prop_m)
        smoke_starts = channels.pop(("SMOKE", "starts"), [])
        if smoke_starts:
            used.add("SMOKE")
        for ob in items.owned(cam):
            if ob.get("stride_item") not in used:
                data = ob.data
                for child in list(ob.children):
                    cd = child.data
                    _remove(child)
                    _remove_data(cd)
                _remove(ob)
                _remove_data(data)
        for item_id in used:
            ob = items.ensure(cam, item_id)
            bag = bake.channelbag(ob, f"POV {item_id.title()}")
            if item_id == "SMOKE":
                self._bake_smoke(ob, bag, nums, frames, smoke_starts)
                continue
            mats = prop_m[item_id]
            last = next((m for m in mats if m is not None), Matrix.Identity(4))
            filled = []
            for m in mats:
                last = m if m is not None else last
                filled.append(last)
            locs, rots = bake.euler_rows(filled)
            ob.rotation_mode = "XYZ"
            bake.write_vector(bag, "location", nums, locs, "Object Transforms")
            bake.write_vector(bag, "rotation_euler", nums, rots, "Object Transforms")
            hidden = ~prop_vis[item_id]
            _key_visibility(bag, nums, hidden)
            for (it, ch), arr in channels.items():
                if it != item_id:
                    continue
                vals = _fill(arr, ob.get(ch, 0.0))
                ob[ch] = float(vals[0])
                bake.write(bag, f'["{ch}"]', 0, nums, vals, group="Channels")
                if item_id == "FLASHLIGHT" and ob.children:
                    lamp = ob.children[0]
                    lbag = bake.channelbag(lamp.data, "POV Flashlight Beam", slot_type="LIGHT")
                    bake.write(lbag, "energy", 0, nums, vals * 25.0)
                    _key_visibility(bake.channelbag(lamp, "POV Flashlight Beam Vis"), nums, hidden)

    def _bake_smoke(self, ob, bag, nums, frames, starts):
        n = len(frames)
        dens = np.zeros(n)
        mats = []
        for i, fr in enumerate(frames):
            cur = None
            for t0, kind, head in starts:
                if t0 <= fr.t < t0 + SMOKE_LIFE:
                    cur = (t0, kind, head)
            if cur is None:
                mats.append(mats[-1] if mats else Matrix.Translation((0, 0, -1000)) @ Matrix.Scale(0.01, 4))
                continue
            t0, kind, head = cur
            age = fr.t - t0
            fwd = Vector(head.col[1][:3]).normalized()
            mouth = head @ Vector(clips.MOUTH)
            pos = mouth + fwd * (0.06 + 0.32 * age ** 0.7) + Vector((0, 0, 0.07 * age))
            size = 0.035 + 0.30 * (1.0 - math.exp(-age * 1.1))
            peak = 1.6 if kind == "puff" else 0.6
            fade = min(age / 0.25, 1.0) * math.exp(-age * 1.0)
            dens[i] = peak * fade / max(size / 0.1, 1.0) ** 1.4
            rot = Matrix.Rotation(age * 0.4, 4, "Z")
            mats.append(Matrix.Translation(pos) @ rot @ Matrix.Diagonal((size, size * 0.8, size * 0.7, 1.0)))
        ob.rotation_mode = "XYZ"
        locs, rots = bake.euler_rows(mats)
        scales = np.array([m.to_scale() for m in mats])
        bake.write_vector(bag, "location", nums, locs, "Object Transforms")
        bake.write_vector(bag, "rotation_euler", nums, rots, "Object Transforms")
        bake.write_vector(bag, "scale", nums, scales, "Object Transforms")
        ob["density"] = 0.0
        bake.write(bag, '["density"]', 0, nums, dens, group="Channels")
        _key_visibility(bag, nums, dens <= 1e-4)


def _fill(arr, default):
    """Forward-fill NaNs (frames without an action keep the last value)."""
    out = np.array(arr, float)
    last = default
    for i in range(len(out)):
        if np.isnan(out[i]):
            out[i] = last
        else:
            last = out[i]
    return out


def _key_visibility(bag, nums, hidden):
    """Constant keys only where visibility changes."""
    hidden = np.asarray(hidden, bool)
    idx = [0] + [i for i in range(1, len(hidden)) if hidden[i] != hidden[i - 1]]
    fr = np.array([nums[i] for i in idx], float)
    vals = np.array([float(hidden[i]) for i in idx])
    for path in ("hide_viewport", "hide_render"):
        bake.write(bag, path, 0, fr, vals, constant=True)


def _remove(ob):
    import bpy
    bpy.data.objects.remove(ob, do_unlink=True)


def _remove_data(data):
    import bpy
    if data is None or data.users:
        return
    if isinstance(data, bpy.types.Mesh):
        bpy.data.meshes.remove(data)
    elif isinstance(data, bpy.types.Light):
        bpy.data.lights.remove(data)
