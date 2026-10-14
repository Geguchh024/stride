# SPDX-License-Identifier: GPL-3.0-or-later
"""Arm and hand proportions: the skeleton and the shapes that make the skin (numpy, no bpy).

Everything is for the right arm in the body frame (origin at the eyes, +X
right, +Y forward, +Z up, metres); the left arm is its mirror image. Hand
details are written in hand space: origin at the wrist, +Y towards the
fingers, +Z the back of the hand, +X the little-finger side.
"""

import math
from dataclasses import dataclass

import numpy as np

from . import sdf

FINGERS = ("index", "middle", "ring", "pinky")


def _n(v):
    v = np.asarray(v, float)
    return v / np.linalg.norm(v)


@dataclass
class Build:
    """Body variations: overall size and how thick the limbs are."""
    size: float = 1.0
    girth: float = 1.0
    finger_girth: float = 1.0


BUILDS = {
    "AVERAGE": Build(),
    "SLIM": Build(size=0.94, girth=0.88, finger_girth=0.9),
    "STRONG": Build(size=1.03, girth=1.15, finger_girth=1.08),
}

# finger: MCP joint (hand space), spread (degrees towards the thumb), phalanx lengths, radii at
# MCP / PIP / DIP / tip. Measured off the skinned hand mesh (see tools/import_hands.py) with a 10 cm palm.
FINGER_DATA = {
    "index": ((-0.0253, 0.1006, -0.0047), 5.0, (0.0251, 0.0225, 0.0198), (0.0095, 0.0090, 0.0080, 0.0070)),
    "middle": ((0.0, 0.1000, 0.0), 0.0, (0.0329, 0.0267, 0.0191), (0.0098, 0.0094, 0.0082, 0.0070)),
    "ring": ((0.0189, 0.0943, 0.0004), -5.0, (0.0289, 0.0241, 0.0205), (0.0092, 0.0087, 0.0078, 0.0066)),
    "pinky": ((0.0368, 0.0848, -0.0047), -11.0, (0.0206, 0.0152, 0.0148), (0.0078, 0.0070, 0.0063, 0.0056)),
}
THUMB_CMC = (-0.0237, 0.0368, -0.0030)
THUMB_DIRS = ((-0.63, 0.35, -0.69), (-0.53, 0.69, -0.50), (-0.29, 0.80, -0.52))
THUMB_LENGTHS = (0.0301, 0.0354, 0.0243)
THUMB_RADII = (0.0125, 0.0110, 0.0095, 0.0085)
THUMB_NAIL = (-0.84, -0.34, 0.43)      # which way the thumbnail faces


class Arm:
    """Joint positions, bones and skin shapes of one arm in its rest pose."""

    def __init__(self, build=None, side=1):
        b = build or Build()
        self.side = side
        self.build = b
        s = b.size
        self.shoulder = np.array([0.170 * s, -0.070, -0.210 * s])
        self.clav_root = np.array([0.030, -0.075, -0.200])
        self.upper_len = 0.290 * s
        self.fore_len = 0.260 * s
        u = _n((0.05, 0.35, -1.0))
        f = _n((-0.08, 1.0, 0.05))
        self.elbow = self.shoulder + u * self.upper_len
        self.wrist = self.elbow + f * self.fore_len
        hz = _n(np.array([0, 0, 1.0]) - f * f[2])
        hx = np.cross(f, hz)
        self.hand_rot = np.column_stack([hx, f, hz])     # hand space -> body frame
        self.u_dir, self.f_dir, self.hand_z = u, f, hz
        self._fingers()

    # -- hand space helpers -----------------------------------------------------

    def hp(self, p):
        """Hand-space point to the body frame (hand dimensions scale with the build)."""
        return self.wrist + self.hand_rot @ (np.asarray(p, float) * self.build.size)

    def hd(self, d):
        return self.hand_rot @ _n(d)

    def _fingers(self):
        self.chains = {}
        for name, (mcp, spread, lengths, radii) in FINGER_DATA.items():
            a = math.radians(spread)
            d = self.hd((-math.sin(a), math.cos(a), -0.02))
            p0 = self.hp(mcp)
            joints = [p0]
            for ln in lengths:
                joints.append(joints[-1] + d * ln * self.build.size)
            self.chains[name] = (joints, [r * self.build.finger_girth * self.build.size for r in radii],
                                 d, self.hand_z)
        joints = [self.hp(THUMB_CMC)]
        for d, ln in zip(THUMB_DIRS, THUMB_LENGTHS):
            joints.append(joints[-1] + self.hd(d) * ln * self.build.size)
        self.chains["thumb"] = (joints, [r * self.build.finger_girth * self.build.size for r in THUMB_RADII],
                                self.hd(THUMB_DIRS[1]), self.hd(THUMB_NAIL))

    # -- skeleton ------------------------------------------------------------------

    def bones(self):
        """(name, head, tail, z axis reference, parent, connected) for the right arm."""
        out = [
            ("clavicle", self.clav_root, self.shoulder, (0, 0, 1), None, False),
            ("upper_arm", self.shoulder, self.elbow, -self.f_dir, "clavicle", True),
            ("forearm", self.elbow, self.wrist, self.hand_z, "upper_arm", True),
            ("forearm_twist", self.elbow, self.wrist, self.hand_z, "forearm", False),
            ("hand", self.wrist, self.hp((0, 0.085, 0)), self.hand_z, "forearm_twist", True),
        ]
        for name in ("thumb",) + FINGERS:
            joints, _r, _d, zref = self.chains[name]
            for k in range(3):
                parent = "hand" if k == 0 else f"{name}.{k:02d}"
                out.append((f"{name}.{k + 1:02d}", joints[k], joints[k + 1], zref, parent, k > 0))
        return out

    # -- skin shapes ---------------------------------------------------------------

    def skin(self):
        """The arm's shapes (upper arm and forearm), which the sleeves are cut round. The
        skin itself is the sculpted mesh (handmesh.build)."""
        g = self.build.girth
        S, E, W = self.shoulder, self.elbow, self.wrist
        hz = self.hand_z
        f = self.f_dir
        M = E + (W - E) * 0.45
        arm = [
            sdf.cone("upper_arm", S, E, 0.050 * g, 0.041 * g, z_ref=-f, sx=1.0, sz=0.95,
                     parent="clavicle", r0=0.05, child="forearm", r1=0.035),
            sdf.ellipsoid("upper_arm", S + (E - S) * 0.55 + _n(np.cross(self.u_dir, (1, 0, 0))) * -0.012,
                          np.array([0.038, 0.085, 0.036]) * g, y_axis=E - S, z_ref=-f,
                          axis=(S, E), parent="clavicle", r0=0.05, child="forearm", r1=0.035),
            sdf.ellipsoid("clavicle", S + np.array([0.005, 0.0, 0.01]), np.array([0.055, 0.05, 0.05]) * g,
                          axis=(self.clav_root, S), child="upper_arm", r1=0.03),
            sdf.ellipsoid("upper_arm", E - self.u_dir * 0.004 - f * 0.012, (0.020, 0.024, 0.020),
                          axis=(S, E), parent="clavicle", r0=0.05, child="forearm", r1=0.035),
            sdf.cone("forearm", E, M, 0.041 * g, 0.034 * g, z_ref=hz, sx=1.08, sz=0.92,
                     axis=(E, W), parent="upper_arm", r0=0.035, child="hand", r1=0.032, twist=True),
            sdf.cone("forearm", M, W - f * 0.006, 0.034 * g, 0.0265 * g, z_ref=hz, sx=1.12, sz=0.72,
                     axis=(E, W), parent="upper_arm", r0=0.035, child="hand", r1=0.032, twist=True),
            # brachioradialis: the muscle bulge on top of the forearm near the elbow
            sdf.ellipsoid("forearm", E + (W - E) * 0.22 + hz * 0.012 + self.hd((-1, 0, 0)) * 0.01,
                          np.array([0.030, 0.075, 0.026]) * g, y_axis=W - E, z_ref=hz,
                          axis=(E, W), parent="upper_arm", r0=0.035, child="hand", r1=0.032, twist=True),
        ]
        return {"arm": arm}

