# SPDX-License-Identifier: GPL-3.0-or-later
"""Small maths for the motion solver (numpy, no bpy): easing, noise, splines, smoothing."""

import math

import numpy as np

TAU = 2.0 * math.pi


def clamp(x, lo, hi):
    return lo if x < lo else hi if x > hi else x


def lerp(a, b, t):
    return a + (b - a) * t


def smoothstep(e0, e1, x):
    if e1 == e0:
        return 1.0 if x >= e1 else 0.0
    t = clamp((x - e0) / (e1 - e0), 0.0, 1.0)
    return t * t * (3.0 - 2.0 * t)


def min_jerk(t):
    """0..1 ease with zero velocity and acceleration at both ends (how people move a limb)."""
    t = clamp(t, 0.0, 1.0)
    return t * t * t * (10.0 + t * (-15.0 + 6.0 * t))


def wrap_angle(a):
    """Angle into -pi..pi."""
    return (a + math.pi) % TAU - math.pi


def unwrap(angles):
    """Remove 2*pi jumps from a sequence of angles."""
    return np.unwrap(np.asarray(angles, dtype=np.float64))


# -- noise -----------------------------------------------------------------------------

def _hash(i, seed):
    """Deterministic pseudo random value in -1..1 for integer lattice points (array or int)."""
    x = (np.asarray(i, dtype=np.int64) * 374761393 + seed * 668265263) & 0xFFFFFFFF
    x = ((x ^ (x >> 13)) * 1274126177) & 0xFFFFFFFF
    x = x ^ (x >> 16)
    return (x & 0xFFFF) / 32767.5 - 1.0


def noise1(x, seed=0):
    """Smooth 1D gradient noise, roughly -1..1, zero at integers."""
    x = np.asarray(x, dtype=np.float64)
    i = np.floor(x)
    f = x - i
    g0 = _hash(i.astype(np.int64), seed)
    g1 = _hash(i.astype(np.int64) + 1, seed)
    u = f * f * f * (f * (f * 6.0 - 15.0) + 10.0)
    return 2.0 * (g0 * f * (1.0 - u) + g1 * (f - 1.0) * u)


def fbm1(x, seed=0, octaves=3, gain=0.5):
    """Layered noise for organic, slightly irregular motion."""
    x = np.asarray(x, dtype=np.float64)
    out = np.zeros_like(x)
    amp, freq, norm = 1.0, 1.0, 0.0
    for o in range(octaves):
        out += amp * noise1(x * freq + o * 17.31, seed + o * 101)
        norm += amp
        amp *= gain
        freq *= 2.03
    return out / norm


# -- splines ---------------------------------------------------------------------------

def catmull_rom(points, per_segment=48, alpha=0.5):
    """Centripetal Catmull-Rom curve through 2D or 3D points. Returns an (n, d) array.

    Centripetal parameterisation never overshoots or loops, so a path between
    close waypoints stays where it was put.
    """
    p = np.asarray(points, dtype=np.float64)
    if len(p) < 2:
        return p.copy()
    if len(p) == 2:
        t = np.linspace(0.0, 1.0, per_segment + 1)[:, None]
        return p[0] + (p[1] - p[0]) * t
    ext = np.vstack([2 * p[0] - p[1], p, 2 * p[-1] - p[-2]])
    out = []
    for k in range(len(p) - 1):
        p0, p1, p2, p3 = ext[k], ext[k + 1], ext[k + 2], ext[k + 3]
        t0 = 0.0
        t1 = t0 + max(np.linalg.norm(p1 - p0), 1e-6) ** alpha
        t2 = t1 + max(np.linalg.norm(p2 - p1), 1e-6) ** alpha
        t3 = t2 + max(np.linalg.norm(p3 - p2), 1e-6) ** alpha
        last = k == len(p) - 2
        t = np.linspace(t1, t2, per_segment + 1 if last else per_segment, endpoint=last)[:, None]
        a1 = (t1 - t) / (t1 - t0) * p0 + (t - t0) / (t1 - t0) * p1
        a2 = (t2 - t) / (t2 - t1) * p1 + (t - t1) / (t2 - t1) * p2
        a3 = (t3 - t) / (t3 - t2) * p2 + (t - t2) / (t3 - t2) * p3
        b1 = (t2 - t) / (t2 - t0) * a1 + (t - t0) / (t2 - t0) * a2
        b2 = (t3 - t) / (t3 - t1) * a2 + (t - t1) / (t3 - t1) * a3
        out.append((t2 - t) / (t2 - t1) * b1 + (t - t1) / (t2 - t1) * b2)
    return np.vstack(out)


def resample(poly, step):
    """Resample a polyline at even arc-length steps. Returns (points, arc lengths)."""
    poly = np.asarray(poly, dtype=np.float64)
    seg = np.linalg.norm(np.diff(poly, axis=0), axis=1)
    cum = np.concatenate([[0.0], np.cumsum(seg)])
    total = cum[-1]
    if total < 1e-9:
        return poly[:1].copy(), np.zeros(1)
    n = max(2, int(math.ceil(total / step)) + 1)
    s = np.linspace(0.0, total, n)
    out = np.column_stack([np.interp(s, cum, poly[:, d]) for d in range(poly.shape[1])])
    return out, s


def box_smooth(values, radius):
    """Moving average with the window shrinking at the ends (keeps endpoints in place)."""
    v = np.asarray(values, dtype=np.float64)
    if radius < 1 or len(v) < 3:
        return v.copy()
    c = np.concatenate([[0.0], np.cumsum(v)])
    idx = np.arange(len(v))
    r = np.minimum(np.minimum(idx, len(v) - 1 - idx), radius)
    return (c[idx + r + 1] - c[idx - r]) / (2 * r + 1)


def damp(values, dt, tau):
    """Critically damped follow of a sampled signal (state carried forward in time).

    Smooths jerky targets into the lag a neck or a hand really has; tau is
    the time constant in seconds.
    """
    v = np.asarray(values, dtype=np.float64)
    if tau <= 1e-6 or len(v) < 2:
        return v.copy()
    out = np.empty_like(v)
    x, vel = v[0], 0.0
    omega = 2.0 / tau
    for i, target in enumerate(v):
        # exact step of a critically damped spring (Game Programming Gems 4)
        k = omega * dt
        e = 1.0 / (1.0 + k + 0.48 * k * k + 0.235 * k * k * k)
        change = x - target
        temp = (vel + omega * change) * dt
        vel = (vel - omega * temp) * e
        x = target + (change + temp) * e
        out[i] = x
    return out
