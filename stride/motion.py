# SPDX-License-Identifier: GPL-3.0-or-later
"""Body and head motion over time: step bob and sway, looking ahead, look moves, breathing.

Frames of reference (all right handed, Z up):

- body: origin at the eyes' resting place, +Y the way the body faces. The
  arms hang from it.
- head: turns about the neck pivot, which sits behind and below the eyes, so
  looking down also moves the eyes forward and down like a real head.
- camera: the head frame turned so the lens looks along the head's +Y.
"""

import math
from dataclasses import dataclass, field

import numpy as np
from mathutils import Matrix, Vector

from . import mathkit as mk

NECK = Vector((0.0, -0.075, -0.115))     # neck pivot, from the eyes
CAMERA_BASE = Matrix.Rotation(math.pi / 2, 4, "X")
D2R = math.pi / 180.0


@dataclass
class Head:
    look_ahead: float = 2.5      # how far along the path the eyes lead (m)
    lag: float = 0.3             # how slowly the head follows (s)
    pitch: float = -3.0          # resting pitch (degrees, negative looks down)
    follow_slope: float = 0.35   # look up or down slopes and stairs
    watch_step: float = 10.0     # extra look down on stairs (degrees)
    shake: float = 0.35          # handheld wander (degrees)
    breathing: float = 1.0
    seed: int = 0


@dataclass
class Look:
    """A look move: the head turns somewhere and back. Times in seconds."""
    start: float
    duration: float
    kind: str = "LEFT"
    amount: float = 60.0         # degrees
    target: tuple = None         # world point for kind "AT"


LOOK_KINDS = [
    # id, label, description, icon, default amount (degrees), default duration (s)
    ("LEFT", "Look Left", "Turn the head left and back", "BACK", 65.0, 2.5),
    ("RIGHT", "Look Right", "Turn the head right and back", "FORWARD", 65.0, 2.5),
    ("UP", "Look Up", "Look up and back down", "SORT_DESC", 35.0, 2.5),
    ("DOWN", "Look Down", "Look down at the floor and back up", "SORT_ASC", 40.0, 2.0),
    ("AROUND", "Look Around", "Look left, then right, then ahead again", "ORIENTATION_GIMBAL", 60.0, 4.5),
    ("BACK_LEFT", "Over Left Shoulder", "Glance back over the left shoulder", "LOOP_BACK", 125.0, 2.5),
    ("BACK_RIGHT", "Over Right Shoulder", "Glance back over the right shoulder", "LOOP_FORWARDS", 125.0, 2.5),
    ("NOD", "Nod", "Nod yes", "TRIA_DOWN", 12.0, 1.4),
    ("SHAKE", "Shake Head", "Shake the head no", "ARROW_LEFTRIGHT", 14.0, 1.4),
    ("AT", "Look At Object", "Turn to look at an object, then back", "RESTRICT_SELECT_OFF", 1.0, 3.0),
]
LOOK_DEFAULTS = {k[0]: (k[4], k[5]) for k in LOOK_KINDS}


def _turn_time(amount, duration):
    return min(mk.clamp(0.22 + abs(amount) / 220.0, 0.25, 0.75), duration * 0.45)


def look_keys(lk):
    """(time, yaw, pitch) keys of a look move, in degrees; eased with min-jerk between."""
    d, a = max(lk.duration, 0.2), lk.amount
    tt = _turn_time(a, d)
    if lk.kind in ("LEFT", "BACK_LEFT"):
        return [(0, 0, 0), (tt, a, 0), (d - tt, a, 0), (d, 0, 0)]
    if lk.kind in ("RIGHT", "BACK_RIGHT"):
        return [(0, 0, 0), (tt, -a, 0), (d - tt, -a, 0), (d, 0, 0)]
    if lk.kind == "UP":
        return [(0, 0, 0), (tt, 0, a), (d - tt, 0, a), (d, 0, 0)]
    if lk.kind == "DOWN":
        return [(0, 0, 0), (tt, 0, -a), (d - tt, 0, -a), (d, 0, 0)]
    if lk.kind == "AROUND":
        return [(0, 0, 0), (0.22 * d, a, 2), (0.38 * d, a * 0.9, 1), (0.62 * d, -a * 0.9, 1),
                (0.78 * d, -a, 2), (d, 0, 0)]
    if lk.kind == "NOD":
        return [(0, 0, 0), (0.2 * d, 0, -a), (0.4 * d, 0, a * 0.25), (0.62 * d, 0, -a * 0.8),
                (0.82 * d, 0, a * 0.1), (d, 0, 0)]
    if lk.kind == "SHAKE":
        return [(0, 0, 0), (0.17 * d, a, 0), (0.39 * d, -a, 0), (0.61 * d, a * 0.8, 0),
                (0.82 * d, -a * 0.5, 0), (d, 0, 0)]
    if lk.kind == "AT":
        return [(0, 0, 0), (min(0.6, 0.3 * d), 1, 0), (d - min(0.7, 0.3 * d), 1, 0), (d, 0, 0)]
    return [(0, 0, 0), (d, 0, 0)]


def eval_keys(keys, t):
    """Value of (time, *values) keys at t, eased with min-jerk between keys."""
    if t <= keys[0][0]:
        return keys[0][1:]
    for k0, k1 in zip(keys, keys[1:]):
        if t <= k1[0]:
            span = k1[0] - k0[0]
            u = mk.min_jerk((t - k0[0]) / span) if span > 1e-9 else 1.0
            return tuple(a + (b - a) * u for a, b in zip(k0[1:], k1[1:]))
    return keys[-1][1:]


@dataclass
class Frame:
    t: float
    s: float
    speed: float
    gait: float          # 0 standing .. 1 full walk (drives bob and hand sway)
    phase: float         # step phase (integers are footsteps)
    body: Matrix = None
    head: Matrix = None
    camera: Matrix = None
    head_rot: tuple = (0.0, 0.0, 0.0)
    extra: dict = field(default_factory=dict)


def head_matrix(body, yaw, pitch, roll):
    """Eye frame for a head turned (yaw, pitch, roll radians) about the neck pivot."""
    rot = (Matrix.Rotation(yaw, 4, "Z") @ Matrix.Rotation(pitch, 4, "X")
           @ Matrix.Rotation(roll, 4, "Y"))
    return body @ Matrix.Translation(NECK) @ rot @ Matrix.Translation(-NECK)


def simulate(plan, head, looks, times, extra_head=None):
    """Per-frame body, head and camera for the given times (seconds).

    ``extra_head(t)`` may add (yaw, pitch) degrees, e.g. a hand action
    looking down at a phone.
    """
    g = plan.gait
    times = np.asarray(times, float)
    n = len(times)
    dt = float(times[1] - times[0]) if n > 1 else 1.0 / 24.0
    s = np.array([plan.s_at(t) for t in times])
    speed = np.array([plan.speed_at(t) for t in times])
    gait = mk.damp(np.clip(speed / max(g.speed, 0.05), 0.0, 1.5), dt, 0.25)
    phase = s / max(plan.step, 1e-6)

    xy = np.column_stack([np.interp(s, plan.s, plan.xy[:, 0]), np.interp(s, plan.s, plan.xy[:, 1])])
    base = np.interp(s, plan.s, plan.base)
    yaw_b = np.interp(s, plan.s, plan.yaw)

    # start and end facing: turn on the spot before setting off and after arriving
    p0, p1 = plan.points[0], plan.points[-1]
    t_go = float(plan.knot_t[1]) if g.start_delay > 0 and len(plan.knot_t) > 1 else 0.0
    if p0.yaw is not None and t_go > 0:
        w = np.array([1.0 - mk.min_jerk((t - (t_go - 0.9)) / 0.9) for t in times])
        delta = mk.wrap_angle(p0.yaw - yaw_b[0])
        yaw_b = yaw_b + np.where(times < t_go, w * delta, 0.0)
    w_end = np.zeros(n)
    if p1.yaw is not None:
        w_end = np.array([mk.min_jerk((t - plan.duration + 0.25) / 1.1) for t in times])
        delta = mk.wrap_angle(p1.yaw - plan.yaw[-1])
        yaw_b = yaw_b + w_end * delta

    # step bob, sway over the support foot, breathing
    bob = -g.bob * gait * np.cos(mk.TAU * phase)
    lateral = -g.sway * gait * np.sin(math.pi * phase)
    rest = np.clip(1.0 - gait, 0.0, 1.0)
    breath = head.breathing * rest * (0.0025 * np.sin(mk.TAU * times / 4.2)
                                      + 0.0012 * mk.fbm1(times * 0.3, head.seed + 7))
    shift = head.breathing * rest * 0.006 * mk.fbm1(times * 0.12, head.seed + 9)

    # where the eyes lead: a point ahead on the path, followed with the neck's lag
    yaw_t = np.empty(n)
    pitch_t = np.empty(n)
    grade_win = 1.2
    for i in range(n):
        ax, ay, _ = plan.ahead(s[i], head.look_ahead)
        yaw_t[i] = mk.wrap_angle(math.atan2(ay - xy[i, 1], ax - xy[i, 0]) - yaw_b[i])
        g0 = plan.ground_at(s[i])
        g1 = plan.ahead(s[i], grade_win)[2]
        slope = math.atan2(g1 - g0, grade_win)
        stairs = mk.smoothstep(0.12, 0.35, abs(math.tan(slope)))
        pitch_t[i] = head.pitch * D2R + head.follow_slope * slope - head.watch_step * D2R * stairs * min(gait[i], 1)
    if np.hypot(*(xy[-1] - xy[0])) < 0.05:
        yaw_t[:] = 0.0
    yaw_t = np.clip(yaw_t, -80 * D2R, 80 * D2R) * (1.0 - w_end)   # after turning to the end arrow, look that way
    yaw_o = mk.damp(yaw_t, dt, head.lag)
    pitch_o = mk.damp(pitch_t, dt, head.lag * 1.3)

    # look moves and hand actions
    add_yaw = np.zeros(n)
    add_pitch = np.zeros(n)
    at_moves = []
    for lk in looks:
        keys = look_keys(lk)
        if lk.kind == "AT":
            at_moves.append((lk, keys))
            continue
        for i, t in enumerate(times):
            if lk.start <= t <= lk.start + lk.duration:
                y, p = eval_keys(keys, t - lk.start)
                add_yaw[i] += y * D2R
                add_pitch[i] += p * D2R
    if extra_head is not None:
        for i, t in enumerate(times):
            y, p = extra_head(t)
            add_yaw[i] += y * D2R
            add_pitch[i] += p * D2R

    # handheld wander, and the small head nod and twist of each step
    sh = head.shake * D2R
    nyaw = sh * (mk.fbm1(times * 0.35, head.seed + 1) + 0.15 * mk.fbm1(times * 2.1, head.seed + 2))
    npitch = sh * 0.8 * (mk.fbm1(times * 0.4, head.seed + 3) + 0.15 * mk.fbm1(times * 2.3, head.seed + 4))
    nroll = sh * 0.5 * mk.fbm1(times * 0.3, head.seed + 5)
    step_pitch = 0.25 * D2R * gait * np.sin(mk.TAU * phase + 0.6)
    step_yaw = 0.35 * D2R * gait * np.sin(math.pi * phase)
    roll_gait = g.roll * D2R * gait * -np.sin(math.pi * phase - 0.3)

    yaw_h = yaw_o + add_yaw + nyaw + step_yaw
    pitch_h = pitch_o + add_pitch + npitch + step_pitch
    # heads lean a little into quick turns
    lean = np.clip(-0.05 * np.gradient(yaw_h, dt) if n > 1 else np.zeros(n), -0.06, 0.06)
    frames = []
    for i in range(n):
        body_yaw = float(yaw_b[i])
        loc = Vector((xy[i, 0], xy[i, 1], base[i] + g.eye + bob[i] + breath[i]))
        right = Vector((math.sin(body_yaw), -math.cos(body_yaw), 0.0))
        loc += right * (lateral[i] + shift[i])
        body = Matrix.Translation(loc) @ Matrix.Rotation(body_yaw - math.pi / 2, 4, "Z")
        yh, ph = float(yaw_h[i]), float(pitch_h[i])
        if at_moves:
            eye = head_matrix(body, yh, ph, 0.0).translation
            for lk, keys in at_moves:
                t = times[i]
                if lk.target is not None and lk.start <= t <= lk.start + lk.duration:
                    w = eval_keys(keys, t - lk.start)[0] * min(max(lk.amount, 0.0), 1.0)
                    d = Vector(lk.target) - eye
                    ty = mk.wrap_angle(math.atan2(d.y, d.x) - body_yaw)
                    tp = math.atan2(d.z, max(d.xy.length, 1e-6))
                    yh += mk.wrap_angle(ty - yh) * w
                    ph += (tp - ph) * w
        yh = mk.clamp(yh, -165 * D2R, 165 * D2R)
        ph = mk.clamp(ph, -80 * D2R, 75 * D2R)
        rh = float(nroll[i] + roll_gait[i] + lean[i])
        hm = head_matrix(body, yh, ph, rh)
        frames.append(Frame(t=float(times[i]), s=float(s[i]), speed=float(speed[i]), gait=float(gait[i]),
                            phase=float(phase[i]), body=body, head=hm, camera=hm @ CAMERA_BASE,
                            head_rot=(yh, ph, rh)))
    return frames
