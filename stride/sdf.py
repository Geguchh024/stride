# SPDX-License-Identifier: GPL-3.0-or-later
"""Signed distance shapes and a surface-nets mesher (numpy, no bpy).

Arms and hands are modelled as smooth unions of rounded cones and
ellipsoids, then meshed in one piece: no seams between fingers and palm,
and a clean quad mesh that subdivides well.
"""

import numpy as np


def _frame(y_axis, z_ref):
    """Orthonormal frame (3x3, columns X Y Z) with Y along y_axis and Z towards z_ref."""
    y = np.asarray(y_axis, float)
    y = y / max(np.linalg.norm(y), 1e-12)
    z = np.asarray(z_ref, float) - y * np.dot(z_ref, y)
    if np.linalg.norm(z) < 1e-6:
        z = np.cross(y, [1.0, 0.0, 0.0])
    z = z / np.linalg.norm(z)
    x = np.cross(y, z)
    return np.column_stack([x, y, z])


def smin(a, b, k):
    """Polynomial smooth minimum: blends two shapes within distance k."""
    if k <= 0:
        return np.minimum(a, b)
    h = np.maximum(k - np.abs(a - b), 0.0) / k
    return np.minimum(a, b) - h * h * k * 0.25


class Prim:
    """One shape. ``bone`` and ``joint`` data drive skin weights later."""

    def __init__(self, kind, bone, **kw):
        self.kind = kind
        self.bone = bone
        self.__dict__.update(kw)
        self.label = kw.get("label", "skin")

    def aabb(self):
        if self.kind == "cone":
            r = max(self.ra, self.rb) / min(self.sx, self.sz) + 1e-3
            lo = np.minimum(self.a, self.b) - r
            hi = np.maximum(self.a, self.b) + r
            return lo, hi
        r = np.max(self.radii) + 1e-3
        return self.c - r, self.c + r

    def distance(self, p):
        """Approximate signed distance for points p (..., 3)."""
        if self.kind == "cone":
            return self._cone(p)
        if self.kind == "ellipsoid":
            q = (p - self.c) @ self.rot
            r = np.asarray(self.radii, float)
            k0 = np.linalg.norm(q / r, axis=-1)
            k1 = np.linalg.norm(q / (r * r), axis=-1)
            return k0 * (k0 - 1.0) / np.maximum(k1, 1e-12)
        if self.kind == "nail":
            # a patch of the base shape's skin, raised a little
            return np.maximum(self.base.distance(p) - self.lift, self.region.distance(p))
        if self.kind == "box":
            q = np.abs((p - self.c) @ self.rot) - (np.asarray(self.radii) - self.round)
            out = np.linalg.norm(np.maximum(q, 0.0), axis=-1)
            inside = np.minimum(np.max(q, axis=-1), 0.0)
            return out + inside - self.round
        raise ValueError(self.kind)

    def _cone(self, p):
        # local frame: squash the cross-section into an ellipse (sx wide, sz thick)
        rot = self.rot
        q = (p - self.a) @ rot
        q = q * np.array([1.0 / self.sx, 1.0, 1.0 / self.sz])
        length = np.linalg.norm(self.b - self.a)
        ba = np.array([0.0, length, 0.0])
        r1, r2 = self.ra, self.rb
        l2 = length * length
        rr = r1 - r2
        a2 = l2 - rr * rr
        il2 = 1.0 / l2
        y = q[..., 1] * length
        z = y - l2
        w = q * l2 - ba * y[..., None]
        x2 = (w * w).sum(-1)
        y2 = y * y * l2
        z2 = z * z * l2
        k = np.sign(rr) * rr * rr * x2
        d_tail = np.sqrt(x2 + z2) * il2 - r2
        d_head = np.sqrt(x2 + y2) * il2 - r1
        d_side = (np.sqrt(np.maximum(x2 * a2 * il2, 0.0)) + y * rr) * il2 - r1
        d = np.where(np.sign(z) * a2 * z2 > k, d_tail, np.where(np.sign(y) * a2 * y2 < k, d_head, d_side))
        return d * min(self.sx, self.sz)

    def param(self, p):
        """Distance along a cone's axis from its start (m), for blending weights."""
        axis = (self.b - self.a) / np.linalg.norm(self.b - self.a)
        return (p - self.a) @ axis


def cone(bone, a, b, ra, rb, z_ref=(0, 0, 1), sx=1.0, sz=1.0, **kw):
    a, b = np.asarray(a, float), np.asarray(b, float)
    return Prim("cone", bone, a=a, b=b, ra=ra, rb=rb, sx=sx, sz=sz, rot=_frame(b - a, z_ref), **kw)


def ellipsoid(bone, c, radii, y_axis=(0, 1, 0), z_ref=(0, 0, 1), **kw):
    return Prim("ellipsoid", bone, c=np.asarray(c, float), radii=np.asarray(radii, float),
                rot=_frame(y_axis, z_ref), **kw)


def box(bone, c, half, round_=0.002, y_axis=(0, 1, 0), z_ref=(0, 0, 1), **kw):
    return Prim("box", bone, c=np.asarray(c, float), radii=np.asarray(half, float), round=round_,
                rot=_frame(y_axis, z_ref), **kw)


# -- 3D value noise for cloth folds -----------------------------------------------

def _hash3(i, j, k, seed):
    x = (i * 73856093) ^ (j * 19349663) ^ (k * 83492791) ^ (seed * 2654435761)
    x = (x ^ (x >> 13)) * 1274126177
    x = x ^ (x >> 16)
    return (x & 0xFFFF).astype(np.float64) / 32767.5 - 1.0


def noise3(p, seed=0):
    p = np.asarray(p, float)
    i = np.floor(p).astype(np.int64)
    f = p - i
    u = f * f * (3.0 - 2.0 * f)
    out = 0.0
    for dx in (0, 1):
        for dy in (0, 1):
            for dz in (0, 1):
                w = ((u[..., 0] if dx else 1 - u[..., 0]) * (u[..., 1] if dy else 1 - u[..., 1])
                     * (u[..., 2] if dz else 1 - u[..., 2]))
                out = out + w * _hash3(i[..., 0] + dx, i[..., 1] + dy, i[..., 2] + dz, seed)
    return out


# -- meshing ------------------------------------------------------------------------

class Grid:
    """Sample points of a regular grid covering [lo, hi] with spacing h."""

    def __init__(self, lo, hi, h):
        self.h = h
        self.lo = np.asarray(lo, float)
        self.n = np.maximum(np.ceil((np.asarray(hi, float) - self.lo) / h).astype(int) + 1, 2)

    def block(self, lo, hi):
        """Index slices and sample points of the sub-grid covering [lo, hi]."""
        i0 = np.clip(np.floor((np.asarray(lo) - self.lo) / self.h).astype(int), 0, self.n - 1)
        i1 = np.clip(np.ceil((np.asarray(hi) - self.lo) / self.h).astype(int) + 1, 1, self.n)
        sl = tuple(slice(a, b) for a, b in zip(i0, i1))
        axes = [self.lo[d] + self.h * np.arange(i0[d], i1[d]) for d in range(3)]
        pts = np.stack(np.meshgrid(*axes, indexing="ij"), axis=-1)
        return sl, pts


def surface_nets(field, grid):
    """Quad mesh of the zero level of ``field`` sampled on ``grid``. Returns (verts, quads)."""
    f = field
    inside = f < 0.0
    nx, ny, nz = f.shape
    lo, h = grid.lo, grid.h
    acc = np.zeros((nx - 1, ny - 1, nz - 1, 3))
    cnt = np.zeros((nx - 1, ny - 1, nz - 1))

    def edges(axis):
        sl0 = [slice(None)] * 3
        sl1 = [slice(None)] * 3
        sl0[axis] = slice(0, -1)
        sl1[axis] = slice(1, None)
        a, b = f[tuple(sl0)], f[tuple(sl1)]
        cross = (a < 0) != (b < 0)
        t = np.where(cross, a / np.where(cross, a - b, 1.0), 0.0)
        idx = np.indices(a.shape).astype(float)
        idx[axis] += t
        pos = np.moveaxis(idx, 0, -1) * h + lo
        return cross, pos

    crosses = []
    for axis in range(3):
        cross, pos = edges(axis)
        crosses.append(cross)
        others = [d for d in range(3) if d != axis]
        for o1 in (0, 1):
            for o2 in (0, 1):
                sl = [slice(None)] * 3
                sl[axis] = slice(None)
                sl[others[0]] = slice(o1, o1 + cross.shape[others[0]] - 1)
                sl[others[1]] = slice(o2, o2 + cross.shape[others[1]] - 1)
                c = cross[tuple(sl)]
                acc += np.where(c[..., None], pos[tuple(sl)], 0.0)
                cnt += c
    active = cnt > 0
    vid = -np.ones(cnt.shape, np.int64)
    vid[active] = np.arange(active.sum())
    verts = acc[active] / cnt[active][:, None]

    quads = []
    for axis in range(3):
        cross = crosses[axis]
        others = [d for d in range(3) if d != axis]
        idx = np.argwhere(cross)
        # the four cells around an edge need both neighbours inside the cell grid
        ok = np.ones(len(idx), bool)
        for d in others:
            ok &= (idx[:, d] >= 1) & (idx[:, d] <= f.shape[d] - 2)
        ok &= idx[:, axis] <= f.shape[axis] - 2
        idx = idx[ok]
        if not len(idx):
            continue
        corners = []
        for o1, o2 in ((0, 0), (1, 0), (1, 1), (0, 1)):
            c = idx.copy()
            c[:, others[0]] -= 1 - o1
            c[:, others[1]] -= 1 - o2
            corners.append(vid[c[:, 0], c[:, 1], c[:, 2]])
        q = np.column_stack(corners)
        # wind so normals point out of the shape
        flip = inside[idx[:, 0], idx[:, 1], idx[:, 2]]
        if axis != 1:
            flip = ~flip
        q[flip] = q[flip][:, ::-1]
        quads.append(q)
    quads = np.vstack(quads) if quads else np.zeros((0, 4), np.int64)
    quads = quads[(quads >= 0).all(axis=1)]
    return verts, quads


def relax(verts, quads, dist_fn, iters=3, smooth=0.5):
    """Even out the mesh and snap it back onto the surface."""
    n = len(verts)
    e = np.vstack([quads[:, [0, 1]], quads[:, [1, 2]], quads[:, [2, 3]], quads[:, [3, 0]]])
    e = np.vstack([e, e[:, ::-1]])
    deg = np.bincount(e[:, 0], minlength=n).astype(float)
    v = verts.copy()
    for _ in range(iters):
        nb = np.zeros_like(v)
        np.add.at(nb, e[:, 0], v[e[:, 1]])
        avg = nb / np.maximum(deg, 1)[:, None]
        v = v + (avg - v) * smooth
        v = project(v, dist_fn)
    return v


def gradient(p, dist_fn, eps=2e-4):
    g = np.zeros_like(p)
    for d in range(3):
        o = np.zeros(3)
        o[d] = eps
        g[:, d] = (dist_fn(p + o) - dist_fn(p - o)) / (2 * eps)
    return g


def project(p, dist_fn, steps=2, max_step=0.004):
    """Newton steps onto the zero level, never moving a point further than max_step at once
    (flat regions of a field have no useful gradient)."""
    for _ in range(steps):
        d = dist_fn(p)
        g = gradient(p, dist_fn)
        gl = np.linalg.norm(g, axis=1)
        ok = gl > 0.2
        step = np.clip(d / np.maximum(gl, 1e-9), -max_step, max_step) * ok
        p = p - step[:, None] * (g / np.maximum(gl, 1e-9)[:, None])
    return p
