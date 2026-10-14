# SPDX-License-Identifier: GPL-3.0-or-later
"""Posing the arm skeleton in Python: forward kinematics, two-bone arm IK, finger poses.

Bone maths mirror Blender's exactly (pose = parent pose @ rest offset @
basis), so the rotations solved here can be keyed straight onto the pose
bones and render the same with or without the add-on.
"""

import math

from mathutils import Matrix, Quaternion, Vector

from . import handposes

IDENTITY = Quaternion()


def mirror_quat(q):
    """A right-side local rotation as the left side's (bones are mirrored across X)."""
    return Quaternion((q.w, q.x, -q.y, -q.z))


def mirror_vec(v):
    return Vector((-v[0], v[1], v[2]))


def frame_from(fingers, palm):
    """Hand rotation (3x3, armature space) from where the fingers point and the palm faces."""
    y = Vector(fingers).normalized()
    z = -Vector(palm)
    z = (z - y * z.dot(y))
    if z.length < 1e-6:
        z = y.orthogonal()
    z.normalize()
    x = y.cross(z)
    m = Matrix((x, y, z)).transposed()
    return m


class Skeleton:
    def __init__(self, rig_ob):
        bones = rig_ob.data.bones
        self.names = [b.name for b in bones]
        self.rest = {b.name: b.matrix_local.copy() for b in bones}
        self.parent = {b.name: (b.parent.name if b.parent else None) for b in bones}
        self.length = {b.name: b.length for b in bones}
        self.rel = {}
        for b in bones:
            if b.parent:
                self.rel[b.name] = b.parent.matrix_local.inverted() @ b.matrix_local
            else:
                self.rel[b.name] = b.matrix_local.copy()
        # parents before children
        order, seen = [], set()

        def visit(n):
            if n in seen:
                return
            p = self.parent[n]
            if p:
                visit(p)
            seen.add(n)
            order.append(n)
        for n in self.names:
            visit(n)
        self.order = order

    def base(self, name, poses):
        """A bone's matrix with an identity basis, under its parent's current pose."""
        p = self.parent[name]
        return (poses[p] if p else Matrix.Identity(4)) @ self.rel[name]

    def fk(self, basis):
        poses = {}
        for n in self.order:
            q = basis.get(n, IDENTITY)
            poses[n] = self.base(n, poses) @ q.to_matrix().to_4x4()
        return poses

    def aim(self, name, poses, direction, twist=0.0):
        """Basis that swings a bone (minimal rotation) to point along ``direction``."""
        base = self.base(name, poses)
        b3 = base.to_3x3()
        y0 = Vector(b3.col[1]).normalized()
        q = y0.rotation_difference(Vector(direction).normalized())
        world = q.to_matrix() @ b3
        if twist:
            world = world @ Matrix.Rotation(twist, 3, "Y")
        basis = (b3.transposed() @ world).to_quaternion()
        poses[name] = base @ basis.to_matrix().to_4x4()
        return basis

    def orient(self, name, poses, rot3):
        """Basis that gives a bone exactly the armature-space rotation ``rot3``."""
        base = self.base(name, poses)
        basis = (base.to_3x3().transposed() @ rot3).to_quaternion()
        poses[name] = base @ basis.to_matrix().to_4x4()
        return basis

    # -- arms ----------------------------------------------------------------------

    def solve_arm(self, side, wrist, hand_rot, elbow_hint, fingers, basis, poses, reach_shoulder=True):
        """Pose one arm (side 'R' or 'L') so the wrist lands on ``wrist`` with the hand turned to
        ``hand_rot``. Writes into ``basis`` and ``poses`` (armature space)."""
        s = "." + side
        clav, upper, fore, twist, hand = (f"clavicle{s}", f"upper_arm{s}", f"forearm{s}",
                                         f"forearm_twist{s}", f"hand{s}")
        a, b = self.length[upper], self.length[fore]
        wrist = Vector(wrist)

        # the shoulder comes forward and up a little for far or high reaches
        poses_c = dict(poses)
        shoulder_rest = self.rest[upper].translation
        reach = (wrist - shoulder_rest).length / (a + b)
        clav_head = self.base(clav, poses_c).translation
        goal = shoulder_rest.copy()
        if reach_shoulder:
            d = (wrist - shoulder_rest).normalized()
            goal += d * 0.035 * min(max((reach - 0.82) / 0.18, 0.0), 1.0)
            goal.z += 0.025 * min(max((wrist.z - shoulder_rest.z) / 0.25, 0.0), 1.0)
        basis[clav] = self.aim(clav, poses, goal - clav_head)

        S = self.base(upper, poses).translation
        d = wrist - S
        dist = min(max(d.length, abs(a - b) + 1e-3), (a + b) * 0.9995)
        dirn = d.normalized() if d.length > 1e-9 else Vector((0, 1, 0))
        cos_a = (a * a + dist * dist - b * b) / (2 * a * dist)
        sin_a = math.sqrt(max(0.0, 1.0 - cos_a * cos_a))
        h = Vector(elbow_hint)
        pn = h - dirn * h.dot(dirn)
        if pn.length < 1e-6:
            pn = dirn.orthogonal()
        pn.normalize()
        E = S + dirn * (a * cos_a) + pn * (a * sin_a)
        W = S + dirn * dist
        basis[upper] = self.aim(upper, poses, E - S)
        basis[fore] = self.aim(fore, poses, W - E)

        # forearm twist: roll the wrist end so the hand needs as little wrist roll as possible
        base_t = self.base(twist, poses).to_3x3()
        y = Vector(base_t.col[1]).normalized()
        z0 = Vector(base_t.col[2])
        hz = Vector(hand_rot.col[2])
        hz_p = hz - y * hz.dot(y)
        tw = 0.0
        if hz_p.length > 1e-6:
            hz_p.normalize()
            tw = math.atan2(z0.cross(hz_p).dot(y), z0.dot(hz_p))
            tw = max(-2.0, min(2.0, tw))
        basis[twist] = Quaternion((0.0, 1.0, 0.0), tw)
        poses[twist] = self.base(twist, poses) @ basis[twist].to_matrix().to_4x4()
        basis[hand] = self.orient(hand, poses, hand_rot)

        # fingers: local rotations from the pose library
        for name, q in fingers.items():
            if name.startswith("_"):
                continue
            bn = name + s
            if bn in self.rest:
                basis[bn] = q if side == "R" else mirror_quat(q)
                poses[bn] = self.base(bn, poses) @ basis[bn].to_matrix().to_4x4()
        return basis


    def fingers(self, pose):
        """Local rotations for every finger bone of a hand pose (right side)."""
        out = handposes.quats(pose)
        rel = self.rel.get("thumb.01.R")
        if rel is not None:
            out["thumb.01"] = handposes.thumb_base(pose, rel.to_3x3())
        # parents before children
        return {k: out[k] for k in sorted(out)}
