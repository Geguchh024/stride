# SPDX-License-Identifier: GPL-3.0-or-later
"""Finger poses: how far each joint bends, by name (right hand, degrees).

Fingers: (knuckle, middle joint, end joint, spread towards the thumb).
Thumb: (swing across the palm, swing out in front of the palm, roll, middle joint, end joint).
Poses blend by mixing these numbers, so any two poses make a smooth transition.
"""

import math

from mathutils import Quaternion

FINGERS = ("index", "middle", "ring", "pinky")


def _p(index, middle, ring, pinky, thumb):
    return {"index": index, "middle": middle, "ring": ring, "pinky": pinky, "thumb": thumb}


POSES = {
    "RELAXED": _p((14, 20, 10, 1), (18, 24, 12, 0), (22, 28, 14, -1), (26, 32, 16, -3), (10, 18, 15, 10, 12)),
    "LIMP": _p((8, 12, 6, 2), (10, 14, 8, 0), (13, 17, 9, -2), (16, 20, 10, -5), (5, 12, 8, 6, 8)),
    "OPEN": _p((2, 3, 2, 6), (2, 3, 2, 0), (2, 3, 2, -5), (2, 3, 2, -11), (-5, 5, 0, 0, 4)),
    "SPREAD": _p((0, 2, 2, 12), (0, 2, 2, 0), (0, 2, 2, -10), (0, 2, 2, -22), (-15, -5, -5, -5, 0)),
    "FIST": _p((85, 100, 60, 0), (88, 100, 62, 0), (90, 100, 62, -2), (92, 100, 60, -4), (35, 35, 35, 30, 25)),
    "LOOSE_FIST": _p((55, 70, 40, 0), (60, 72, 42, 0), (64, 74, 42, -2), (68, 76, 42, -4), (22, 30, 25, 20, 20)),
    # cylinder grips: a to-go cup (8 cm), a bottle (6.5 cm), a flashlight (3 cm)
    "CUP": _p((43, 57, 33, 2), (47, 59, 36, 0), (55, 65, 37, -3), (60, 67, 37, -7), (2, 85, 40, 4, 3)),
    "BOTTLE": _p((41, 53, 30, 1), (45, 54, 32, 0), (55, 64, 36, -3), (70, 77, 42, -7), (6, 75, 40, 21, 15)),
    "TUBE": _p((36, 43, 23, 0), (59, 71, 39, 0), (60, 72, 39, -2), (92, 107, 57, -5), (28, 15, 40, 36, 23)),
    # phone held in the palm, thumb free over the screen
    # phone resting on the palm and the first finger segments, fingertips curled round its far edge
    "PHONE": _p((12, 76, 29, 2), (15, 84, 32, 0), (14, 68, 26, -2), (10, 36, 14, -5), (30, 54, 28, 4, 3)),
    "PHONE_TAP": _p((12, 76, 29, 2), (15, 84, 32, 0), (14, 68, 26, -2), (10, 36, 14, -5), (36, 62, 32, 13, 15)),
    # cigarette between index and middle finger, the other two curled away
    "CIG_V": _p((20, 24, 10, 4), (24, 22, 10, -3), (48, 66, 34, -2), (54, 70, 34, -5), (12, 24, 18, 14, 18)),
    "PINCH": _p((42, 52, 22, 2), (48, 64, 32, 0), (58, 72, 36, -2), (64, 76, 38, -4), (30, 45, 45, 15, 15)),
    "POINT": _p((2, 4, 2, 2), (82, 98, 58, 0), (86, 98, 58, -2), (88, 98, 56, -4), (35, 30, 35, 30, 20)),
    "LIGHTER": _p((70, 84, 46, 0), (74, 86, 48, 0), (76, 88, 48, -2), (78, 88, 46, -5), (10, 10, 10, 15, 25)),
    "FLAT": _p((-4, 0, 0, 3), (-4, 0, 0, 0), (-4, 0, 0, -3), (-4, 0, 0, -6), (12, 2, 0, 0, 0)),
    "THUMBS_UP": _p((86, 100, 60, 0), (88, 100, 62, 0), (90, 100, 62, -2), (92, 100, 60, -4), (10, -20, 0, -5, -5)),
    "PEACE": _p((-2, 2, 2, 10), (-2, 2, 2, -6), (86, 98, 58, -2), (88, 98, 56, -4), (35, 30, 35, 30, 20)),
    "CUPPED": _p((22, 26, 14, 1), (24, 28, 14, 0), (26, 30, 14, -2), (30, 32, 14, -5), (5, 20, 15, 5, 8)),
}


def mix(a, b, t):
    """Blend two poses (names or dicts) by t."""
    pa = POSES[a] if isinstance(a, str) else a
    pb = POSES[b] if isinstance(b, str) else b
    if t <= 0.0:
        return pa
    if t >= 1.0:
        return pb
    return {k: tuple(x + (y - x) * t for x, y in zip(pa[k], pb[k])) for k in pa}


def _rx(deg):
    return Quaternion((1.0, 0.0, 0.0), math.radians(deg))


def _ry(deg):
    return Quaternion((0.0, 1.0, 0.0), math.radians(deg))


def _rz(deg):
    return Quaternion((0.0, 0.0, 1.0), math.radians(deg))


def quats(pose):
    """Local rotations of the finger bones (right hand), parents first."""
    p = POSES[pose] if isinstance(pose, str) else pose
    out = {}
    for f in FINGERS:
        mcp, pip, dip, spread = p[f]
        out[f"{f}.01"] = _rz(spread) @ _rx(-mcp)
        out[f"{f}.02"] = _rx(-pip)
        out[f"{f}.03"] = _rx(-dip)
    _flex, _abduct, _roll, mcp, ip = p["thumb"]
    # thumb.01 turns about the hand's own axes; the skeleton works that out (see thumb_base)
    out["thumb.02"] = _rx(-mcp)
    out["thumb.03"] = _rx(-ip)
    return out


# The thumb's rest pose comes from the hand mesh (anatomy.THUMB_DIRS): further out in front of the
# palm and further from the fingers than the flatter thumb these numbers were written for. Every
# pose adds this back, so (0, 0, 0) still means that flatter thumb.
REST_FLEX, REST_ABDUCT, REST_ROLL = 17.0, -26.0, 9.0


def thumb_base(pose, rel3):
    """Local rotation of the thumb's base bone (right hand).

    ``rel3`` is the bone's rest rotation relative to the hand. The thumb
    swings across the palm (flex, about the back-of-hand axis), out in front
    of the palm (abduct) and rolls about itself (opposition).
    """
    from mathutils import Vector
    p = POSES[pose] if isinstance(pose, str) else pose
    flex, abduct, roll, _mcp, _ip = p["thumb"]
    flex, abduct, roll = flex + REST_FLEX, abduct + REST_ABDUCT, roll + REST_ROLL
    t = Vector(rel3.col[1])
    t.z = 0.0
    t.normalize()
    perp = Vector((0.0, 0.0, 1.0)).cross(t)
    q_hand = Quaternion((0.0, 0.0, 1.0), math.radians(-flex)) @ Quaternion(perp, math.radians(abduct))
    q_rel = rel3.to_quaternion()
    return q_rel.inverted() @ q_hand @ q_rel @ _ry(roll)
