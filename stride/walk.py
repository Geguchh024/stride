# SPDX-License-Identifier: GPL-3.0-or-later
"""The walk: a path through the points, the ground under it, footsteps, speed and timing.

No bpy here. The caller passes a ``ground(x, y, z_hint)`` function (the
invisible floor), and gets back a :class:`Plan` it can sample at any time.
"""

import math
from dataclasses import dataclass, field

import numpy as np

from . import mathkit as mk

DS = 0.02            # path sample spacing (m)
FOOT_HALF = 0.12     # half a foot length: a footstep stands on the highest ground under the foot
FOOT_SIDE = 0.10     # feet sit this far either side of the path
STEP_UP = 0.6        # the floor is searched from this far above the last footstep...
STEP_DOWN = 2.5      # ...down to this far below it


@dataclass
class Point:
    """A start, end or waypoint box: where its base stands, and what happens there."""
    co: tuple
    wait: float = 0.0        # seconds standing still here
    speed: float = 1.0       # speed factor for the walk from here to the next point
    yaw: float = None        # facing (radians from +X), used at the start and end


@dataclass
class Gait:
    speed: float = 1.35          # m/s on flat ground
    step: float = 0.72           # step length (m)
    eye: float = 1.62            # eye height above the floor (m)
    bob: float = 0.016           # vertical bob, half of peak to peak (m)
    sway: float = 0.010          # side to side sway (m)
    roll: float = 0.6            # roll with the sway (degrees)
    accel: float = 0.9           # starting and stopping (m/s^2)
    turn_accel: float = 1.2      # sideways acceleration people allow in turns (m/s^2)
    stairs: float = 1.8          # how much slopes and stairs slow the walk
    stair_rhythm: float = 0.5    # 0 glides up stairs, 1 lifts the body step by step
    start_delay: float = 0.0     # seconds standing before the first step


@dataclass
class Plant:
    s: float
    side: int        # -1 left, +1 right, 0 both feet
    co: tuple        # world position of the footprint
    yaw: float


@dataclass
class Plan:
    s: np.ndarray = None          # arc length of each path sample
    xy: np.ndarray = None
    ground: np.ndarray = None     # floor height under each sample
    hit: np.ndarray = None        # whether the floor was found there
    base: np.ndarray = None       # body base height (follows the footsteps)
    yaw: np.ndarray = None        # body heading
    v: np.ndarray = None          # speed profile along the path
    knot_t: np.ndarray = None     # time -> arc length mapping (with waits)
    knot_s: np.ndarray = None
    point_s: list = field(default_factory=list)
    plants: list = field(default_factory=list)
    step: float = 0.72
    length: float = 0.0
    duration: float = 0.0         # arrival time (s), including the start delay and waits
    gait: Gait = None
    points: list = None

    # -- sampling ------------------------------------------------------------------

    def s_at(self, t):
        return float(np.interp(t, self.knot_t, self.knot_s))

    def _at(self, arr, s):
        return float(np.interp(s, self.s, arr))

    def xy_at(self, s):
        return (self._at(self.xy[:, 0], s), self._at(self.xy[:, 1], s))

    def yaw_at(self, s):
        return self._at(self.yaw, s)

    def base_at(self, s):
        return self._at(self.base, s)

    def ground_at(self, s):
        return self._at(self.ground, s)

    def speed_at(self, t):
        """Instantaneous walking speed (0 while waiting)."""
        i = int(np.searchsorted(self.knot_t, t))
        if i <= 0 or i >= len(self.knot_t):
            return 0.0
        dt = self.knot_t[i] - self.knot_t[i - 1]
        return float((self.knot_s[i] - self.knot_s[i - 1]) / dt) if dt > 1e-9 else 0.0

    def ahead(self, s, dist):
        """Point (x, y, ground) a distance along the path, extrapolated past the end."""
        target = s + dist
        if target <= self.length:
            x, y = self.xy_at(target)
            return x, y, self.ground_at(target)
        x, y = self.xy[-1]
        a = self.yaw[-1]
        extra = target - self.length
        return x + math.cos(a) * extra, y + math.sin(a) * extra, self.ground[-1]

    def phase(self, s):
        """Steps taken so far as a float: the integer part counts footsteps."""
        return s / self.step


def _pchip(x, y, xs):
    """Monotone cubic interpolation: smooth on ramps, never overshoots a stair edge."""
    x = np.asarray(x, float)
    y = np.asarray(y, float)
    if len(x) < 3:
        return np.interp(xs, x, y)
    h = np.diff(x)
    d = np.diff(y) / h
    m = np.zeros_like(y)
    for k in range(1, len(y) - 1):
        if d[k - 1] * d[k] > 0:
            w1, w2 = 2 * h[k] + h[k - 1], h[k] + 2 * h[k - 1]
            m[k] = (w1 + w2) / (w1 / d[k - 1] + w2 / d[k])
    m[0], m[-1] = d[0], d[-1]
    k = np.clip(np.searchsorted(x, xs) - 1, 0, len(x) - 2)
    t = (xs - x[k]) / h[k]
    h00 = (1 + 2 * t) * (1 - t) ** 2
    h10 = t * (1 - t) ** 2
    h01 = t * t * (3 - 2 * t)
    h11 = t * t * (t - 1)
    return h00 * y[k] + h10 * h[k] * m[k] + h01 * y[k + 1] + h11 * h[k] * m[k + 1]


def solve(points, gait, ground=None):
    """Plan a walk through ``points`` (start, waypoints, end).

    ``ground(x, y, z_hint)`` returns the floor height near ``z_hint`` or None;
    without it (or where it finds nothing) the floor runs straight between
    the boxes' bases.
    """
    pl = Plan(gait=gait, points=points)
    pts = np.array([p.co for p in points], float)
    if len(pts) < 2:
        pts = np.vstack([pts, pts])

    # path in plan view; each control point's arc length marks its stop
    per = 64
    dense = mk.catmull_rom(pts[:, :2], per_segment=per)
    seg = np.linalg.norm(np.diff(dense, axis=0), axis=1)
    cum = np.concatenate([[0.0], np.cumsum(seg)])
    pl.point_s = [float(cum[min(k * per, len(cum) - 1)]) for k in range(len(pts))]
    length = float(cum[-1])
    if length < 0.05:
        dense = pts[:1, :2] + np.array([[0.0, 0.0], [0.0, 0.01]])
        cum = np.array([0.0, 0.01])
        pl.point_s = [0.0] * (len(pts) - 1) + [0.01]
    xy, s = mk.resample(dense, DS)
    n = len(s)
    pl.s, pl.xy, pl.length = s, xy, float(s[-1])

    # heading: tangent smoothed over a stride, so the body doesn't twitch
    d = np.gradient(xy, axis=0)
    raw_yaw = mk.unwrap(np.arctan2(d[:, 1], d[:, 0]))
    if pl.length < 0.05:
        raw_yaw[:] = points[0].yaw if points[0].yaw is not None else math.pi / 2
    pl.yaw = mk.box_smooth(raw_yaw, int(0.35 / DS))

    # floor under the path, tracked from the previous height so bridges and
    # upper floors don't steal the walk
    fallback = np.interp(s, pl.point_s, pts[:, 2])
    pl.ground = fallback.copy()
    pl.hit = np.zeros(n, bool)
    if ground is not None:
        hint = fallback[0]
        for i in range(n):
            z = ground(xy[i, 0], xy[i, 1], hint)
            if z is not None:
                pl.ground[i] = z
                pl.hit[i] = True
                hint = z
            else:
                # off the floor: carry on level from the last floor height
                pl.ground[i] = hint if pl.hit[:i].any() else fallback[i]

    # footsteps: a whole number of even steps from start to end
    n_steps = max(1, int(round(pl.length / max(gait.step, 0.1))))
    pl.step = pl.length / n_steps if pl.length > 0.05 else gait.step
    half = max(1, int(FOOT_HALF / DS))
    plant_s = np.linspace(0.0, pl.length, n_steps + 1)
    plant_z = []
    pl.plants = []
    for k, ps in enumerate(plant_s):
        i = int(round(ps / DS))
        lo, hi = max(0, i - half), min(n, i + half + 1)
        z = float(pl.ground[lo:hi].max())
        plant_z.append(z)
        side = 0 if k in (0, n_steps) else (1 if k % 2 else -1)
        yaw = float(np.interp(ps, s, pl.yaw))
        x, y = np.interp(ps, s, xy[:, 0]), np.interp(ps, s, xy[:, 1])
        if side == 0:
            for sd in (-1, 1):
                ox, oy = math.sin(yaw) * sd * FOOT_SIDE, -math.cos(yaw) * sd * FOOT_SIDE
                pl.plants.append(Plant(float(ps), sd, (x + ox, y + oy, z), yaw))
        else:
            ox, oy = math.sin(yaw) * side * FOOT_SIDE, -math.cos(yaw) * side * FOOT_SIDE
            pl.plants.append(Plant(float(ps), side, (x + ox, y + oy, z), yaw))
    plant_z = np.array(plant_z)

    # body height: smooth through the footsteps, with some step-by-step lift on stairs
    glide = _pchip(plant_s, plant_z, s)
    k = np.clip(np.searchsorted(plant_s, s, side="right") - 1, 0, len(plant_s) - 2)
    u = (s - plant_s[k]) / max(pl.step, 1e-6)
    stepped = plant_z[k] + (plant_z[k + 1] - plant_z[k]) * np.array([mk.min_jerk(x) for x in u])
    pl.base = glide + (stepped - glide) * gait.stair_rhythm

    # speed: slower on slopes, in tight turns, and easing in and out of stops
    v = np.full(n, max(gait.speed, 0.05))
    for k in range(len(points) - 1):
        a, b = pl.point_s[k], pl.point_s[k + 1]
        v[(s >= a) & (s <= b)] *= max(points[k].speed, 0.05)
    grade = np.gradient(mk.box_smooth(pl.base, int(0.4 / DS)), s) if n > 2 else np.zeros(n)
    v /= 1.0 + gait.stairs * np.abs(grade)
    kappa = mk.box_smooth(np.abs(np.gradient(pl.yaw, s)) if n > 2 else np.zeros(n), int(0.3 / DS))
    v = np.minimum(v, np.sqrt(gait.turn_accel / np.maximum(kappa, 1e-6)))
    stops = {0, n - 1}
    waits = {}
    for k, p in enumerate(points[1:-1], start=1):
        if p.wait > 0:
            i = int(round(pl.point_s[k] / DS))
            i = min(max(i, 0), n - 1)
            stops.add(i)
            waits[i] = waits.get(i, 0.0) + p.wait
    for i in stops:
        v[i] = 0.0
    a2 = 2.0 * max(gait.accel, 0.05) * DS
    for i in range(1, n):
        v[i] = min(v[i], math.sqrt(v[i - 1] ** 2 + a2))
    for i in range(n - 2, -1, -1):
        v[i] = min(v[i], math.sqrt(v[i + 1] ** 2 + a2))
    pl.v = v

    # time along the path, with waits and the start delay as flat spans
    ds = np.diff(s)
    dt = 2.0 * ds / np.maximum(v[:-1] + v[1:], 1e-4)
    t = np.concatenate([[0.0], np.cumsum(dt)])
    kt, ks = [0.0], [0.0]
    offset = max(gait.start_delay, 0.0)
    if offset > 0:
        kt.append(offset)
        ks.append(0.0)
    for i in range(1, n):
        kt.append(t[i] + offset)
        ks.append(s[i])
        if i in waits:
            offset += waits[i]
            kt.append(t[i] + offset)
            ks.append(s[i])
    pl.knot_t, pl.knot_s = np.array(kt), np.array(ks)
    pl.duration = float(pl.knot_t[-1])
    return pl
