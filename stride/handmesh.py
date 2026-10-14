# SPDX-License-Identifier: GPL-3.0-or-later
"""The arm and sleeve meshes, with skin weights and shading masks (numpy, no bpy).

The arm is a sculpted, skinned and textured mesh (data/arm_source.npz, made by
tools/import_hands.py) fitted to each build's skeleton. Sleeves are meshed from
the arm's skin shapes (signed distances). The results are plain arrays (cached
as .npz) so adding hands in Blender is instant after the first build.
"""

import os

import numpy as np

from . import anatomy, sdf

CACHE_VERSION = 13
K_ARM = 0.022
CHUNK = 400_000


def arm_distance(prims, p, k=K_ARM):
    """Signed distance to the arm's skin shapes (smoothly blended); the sleeves are cut round it."""
    out = np.full(len(p), 1.0)
    for pr in prims:
        lo, hi = pr.aabb()
        lo, hi = lo - k - 0.002, hi + k + 0.002
        m = np.all((p >= lo) & (p <= hi), axis=1)
        if m.any():
            out[m] = sdf.smin(out[m], pr.distance(p[m]), k)
    return out


def _smooth01(e0, e1, x):
    t = np.clip((x - e0) / (e1 - e0), 0.0, 1.0)
    return t * t * (3 - 2 * t)


def masks(arm, verts, normals, weights):
    """Shading masks: nail, fingertip and knuckle flush, palm side."""
    # nails: the top of each fingertip, from the knuckle-side third of the last segment to the tip
    nail = np.zeros(len(verts))
    for name in ("thumb",) + anatomy.FINGERS:
        joints, radii, _d, zref = arm.chains[name]
        a, b = np.asarray(joints[2]), np.asarray(joints[3])
        y = (b - a) / np.linalg.norm(b - a)
        z = np.asarray(zref, float) - y * (y @ zref)
        z /= np.linalg.norm(z)
        x = np.cross(y, z)
        rel = verts - a
        t = rel @ y / np.linalg.norm(b - a)
        r = radii[3]
        patch = (_smooth01(0.30, 0.45, t) * _smooth01(1.55, 1.30, t)
                 * _smooth01(0.85 * r, 0.62 * r, np.abs(rel @ x)) * _smooth01(0.25, 0.55, normals @ z))
        own = weights.get(f"{name}.03", 0.0)
        nail = np.maximum(nail, patch * _smooth01(0.3, 0.7, own))
    knuckle = np.zeros(len(verts))
    flush = np.zeros(len(verts))
    palm = np.zeros(len(verts))
    hz = arm.hand_z
    # how much each vertex belongs to the hand (smooth across the wrist, no seam)
    on_hand = sum(w for b, w in weights.items() if b == "hand" or "." in b)
    on_hand = np.clip(on_hand, 0.0, 1.0)
    for name in ("thumb",) + anatomy.FINGERS:
        joints, radii, _d, _z = arm.chains[name]
        tip = np.linalg.norm(verts - joints[3], axis=1)
        flush = np.maximum(flush, _smooth01(0.02, 0.004, tip))
        for k in range(3):
            dj = np.linalg.norm(verts - joints[k], axis=1)
            near = _smooth01(radii[k] * 1.8, radii[k] * 0.9, dj)
            flush = np.maximum(flush, 0.6 * near)
            if name != "thumb" or k > 0:
                knuckle = np.maximum(knuckle, _smooth01(radii[k] * 1.5, radii[k] * 0.7, dj))
    side = normals @ -hz
    palm = _smooth01(-0.15, 0.45, side) * on_hand
    flush = np.clip(flush + 0.35 * palm, 0, 1) * on_hand
    knuckle = knuckle * _smooth01(-0.1, 0.4, normals @ hz) * on_hand
    return {"nail": nail, "flush": flush, "palm": palm, "knuckle": knuckle}


SOURCE = os.path.join(os.path.dirname(__file__), "data", "arm_source.npz")
ARM_BONES = ("clavicle", "upper_arm", "forearm")


def _rotation_between(a, b):
    """The smallest rotation taking unit vector a onto unit vector b."""
    v = np.cross(a, b)
    c = float(a @ b)
    if np.linalg.norm(v) < 1e-9:
        return np.eye(3) if c > 0 else -np.eye(3)
    k = np.array([[0, -v[2], v[1]], [v[2], 0, -v[0]], [-v[1], v[0], 0]])
    return np.eye(3) + k + k @ k / (1.0 + c)


def bone_map(src, dst, across):
    """Affine map (A, t) laying a source bone onto a target bone: turned onto it, stretched to
    its length and scaled by ``across`` at right angles to it. Joints shared by two bones land
    on the same point from either side, so the skin blends across them without tearing."""
    (sh, st), (dh, dt) = src, dst
    la, lb = np.linalg.norm(st - sh), np.linalg.norm(dt - dh)
    da, db = (st - sh) / la, (dt - dh) / lb
    a = _rotation_between(da, db) @ (across * np.eye(3) + (lb / la - across) * np.outer(da, da))
    return a, dh - a @ sh


def vertex_normals(verts, quads):
    fn = np.cross(verts[quads[:, 2]] - verts[quads[:, 0]], verts[quads[:, 3]] - verts[quads[:, 1]])
    vn = np.zeros_like(verts)
    for i in range(4):
        np.add.at(vn, quads[:, i], fn)
    return vn / np.maximum(np.linalg.norm(vn, axis=1), 1e-12)[:, None]


def _ease_wrist(arm, verts, quads, weights, iters=40):
    """Even out the hand/forearm split across the wrist (the source's is narrow and lumpy on the
    palm side, which creases when the wrist bends). Only skin that follows just those two bones
    is touched, within a few centimetres of the joint."""
    s = (verts - arm.wrist) @ arm.f_dir
    others = sum(w for k, w in weights.items() if k not in ("hand", "forearm"))
    zone = (np.abs(s) < 0.045) & (others < 1e-3)
    e = _edges(quads)
    deg = np.bincount(e[:, 0], minlength=len(verts)).astype(float)
    h = weights["hand"].copy()
    for _ in range(iters):
        avg = np.bincount(e[:, 0], weights=h[e[:, 1]], minlength=len(verts)) / np.maximum(deg, 1)
        h = np.where(zone, 0.5 * h + 0.5 * avg, h)
    total = weights["hand"] + weights["forearm"]
    weights["hand"] = np.where(zone, np.clip(h, 0.0, total), weights["hand"])
    weights["forearm"] = np.where(zone, total - weights["hand"], weights["forearm"])


def _edges(quads):
    e = np.vstack([quads[:, [0, 1]], quads[:, [1, 2]], quads[:, [2, 3]], quads[:, [3, 0]]])
    return np.vstack([e, e[:, ::-1]])


def _arm_axis(arm, p):
    """Nearest point on the shoulder-elbow-wrist line and the distance along it."""
    S, E, W = arm.shoulder, arm.elbow, arm.wrist
    best, along, dist = None, None, None
    for a, b, start in ((S, E, 0.0), (E, W, np.linalg.norm(E - S))):
        ab = b - a
        t = np.clip(((p - a) @ ab) / (ab @ ab), 0.0, 1.0)
        q = a + t[:, None] * ab
        d = np.linalg.norm(p - q, axis=1)
        if best is None:
            best, along, dist = q, start + t * np.linalg.norm(ab), d
        else:
            closer = d < dist
            best = np.where(closer[:, None], q, best)
            along = np.where(closer, start + t * np.linalg.norm(ab), along)
            dist = np.minimum(d, dist)
    return best, along


def _tuck_under_sleeves(arm, verts, quads, margin=0.002):
    """Pull the arm in towards its bones wherever it would show through the sleeves (which are
    shaped round the arm's skin shapes), smoothly, and not at all from the wrist down."""
    d = arm_distance(arm.skin()["arm"], verts)
    need = np.maximum(d + margin, 0.0)
    axis, along = _arm_axis(arm, verts)
    wrist_at = np.linalg.norm(arm.elbow - arm.shoulder) + np.linalg.norm(arm.wrist - arm.elbow)
    need *= _smooth01(wrist_at - 0.005, wrist_at - 0.045, along)
    e = _edges(quads)
    deg = np.maximum(np.bincount(e[:, 0], minlength=len(verts)), 1)
    # a smooth envelope over what each vertex needs: blur, but never below the need itself
    base = need
    for _ in range(12):
        need = np.maximum(base, 0.5 * need + 0.5 * np.bincount(e[:, 0], weights=need[e[:, 1]],
                                                               minlength=len(verts)) / deg)
    radial = verts - axis
    r = np.linalg.norm(radial, axis=1)
    scale = np.clip((r - need) / np.maximum(r, 1e-9), 0.3, 1.0)
    return axis + radial * scale[:, None]


def build(build_id="AVERAGE"):
    """The skinned arm for a build: the source mesh (tools/import_hands.py) fitted to its skeleton.

    The source is posed and proportioned like the average build's skeleton, so the hand and
    fingers map onto it bone for bone and the arm bones stretch to the build's lengths. Each
    vertex follows its bones by its skin weights (linear blend of the per-bone maps).
    """
    arm = anatomy.Arm(anatomy.BUILDS[build_id])
    avg = anatomy.Arm()
    b = arm.build
    z = np.load(SOURCE)
    src_v = z["verts"].astype(np.float64)
    target = {n: (np.asarray(h, float), np.asarray(t, float)) for n, h, t, *_ in arm.bones()}
    # the hand and fingers were measured off the mesh, so the average skeleton is their source;
    # the arm bones keep the joints the mesh was posed to
    source = {n: (np.asarray(h, float), np.asarray(t, float)) for n, h, t, *_ in avg.bones()}
    for n in ARM_BONES:
        source[n] = tuple(z["j_" + n].astype(np.float64))
    weights = {k[2:]: z[k].astype(np.float64) for k in z.files if k.startswith("w_")}
    verts = np.zeros_like(src_v)
    for name, w in weights.items():
        across = b.girth if name in ARM_BONES else b.size * (b.finger_girth if "." in name else 1.0)
        a, t = bone_map(source[name], target[name], across)
        verts += w[:, None] * (src_v @ a.T + t)
    quads = z["quads"].astype(np.int64)
    verts = _tuck_under_sleeves(arm, verts, quads)
    _ease_wrist(arm, verts, quads, weights)
    # the forearm shares its weight with the twist bone: none at the elbow, all of it at the wrist
    fore = weights.pop("forearm")
    e, wr = arm.elbow, arm.wrist
    t = np.clip(((verts - e) @ (wr - e)) / ((wr - e) @ (wr - e)), 0.0, 1.0)
    share = _smooth01(0.1, 0.95, t)
    weights["forearm_twist"] = fore * share
    weights["forearm"] = fore * (1.0 - share)
    m = masks(arm, verts, vertex_normals(verts, quads), weights)
    return {"verts": verts.astype(np.float32), "quads": quads.astype(np.int32), "uv": z["uv"],
            "bones": arm.bones(), "weights": {k: v.astype(np.float32) for k, v in weights.items()},
            "masks": {k: v.astype(np.float32) for k, v in m.items()}}


def save(data, path):
    arrays = {"verts": data["verts"], "quads": data["quads"], "version": np.array([CACHE_VERSION])}
    if data.get("uv") is not None:
        arrays["uv"] = np.asarray(data["uv"], np.float32)
    # half floats keep the shipped files small; weights are renormalised on load
    for k, v in data["weights"].items():
        arrays["w_" + k] = np.asarray(v, np.float16)
    for k, v in data["masks"].items():
        arrays["m_" + k] = np.asarray(v, np.float16)
    np.savez_compressed(path, **arrays)


def load(path):
    if not os.path.exists(path):
        return None
    z = np.load(path)
    if "version" not in z or int(z["version"][0]) != CACHE_VERSION:
        return None
    weights = {k[2:]: z[k].astype(np.float32) for k in z.files if k.startswith("w_")}
    total = np.maximum(sum(weights.values()), 1e-6)
    return {"verts": z["verts"], "quads": z["quads"], "uv": z["uv"] if "uv" in z.files else None,
            "weights": {k: v / total for k, v in weights.items()},
            "masks": {k[2:]: z[k].astype(np.float32) for k in z.files if k.startswith("m_")}}


def cached(build_id, folder):
    """The arm mesh for a build, from the cache folder or freshly built (and then cached)."""
    path = os.path.join(folder, f"arm_{build_id.lower()}.npz")
    data = load(path)
    if data is None:
        data = build(build_id)
        os.makedirs(folder, exist_ok=True)
        save(data, path)
        data = load(path)
    return data


def mirror(data):
    """The left arm: mirrored across X, faces flipped, '.R' bones renamed."""
    v = data["verts"].copy()
    v[:, 0] *= -1
    uv = data.get("uv")
    if uv is not None:
        uv = uv.reshape(-1, 4, 2)[:, ::-1].reshape(-1, 2).copy()
    return {"verts": v, "quads": data["quads"][:, ::-1].copy(), "uv": uv, "weights": data["weights"],
            "masks": data["masks"]}





# -- sleeves ---------------------------------------------------------------------------

# kind: cuff distance before the wrist (m, or ("upper", t) for short sleeves), ease, thickness,
# fold depth, cuff bunching
SLEEVE_CUT = {
    "canvas": (0.034, 0.010, 0.003, 0.0032, 0.004),
    "jersey": (0.022, 0.011, 0.003, 0.0040, 0.008),
    "twill": (0.030, 0.008, 0.003, 0.0028, 0.003),
    "leather": (0.036, 0.008, 0.002, 0.0022, 0.002),
    "plaid": (0.028, 0.006, 0.0025, 0.0030, 0.003),
    "knit": (0.026, 0.012, 0.005, 0.0035, 0.007),
    "wool": (0.048, 0.008, 0.003, 0.0016, 0.0),
    "tee": (("upper", 0.45), 0.012, 0.0025, 0.0030, 0.0),
}


def _solid(arm_field, p, ease, cut_point, cut_dir, back_point=None):
    """The arm grown by ``ease``, cut off at the cuff plane (and optionally behind)."""
    out = np.maximum(arm_field(p) - ease, (p - cut_point) @ cut_dir)
    if back_point is not None:
        out = np.maximum(out, -((p - back_point) @ cut_dir))
    return out


def _drop_caps(verts, quads, planes, h):
    """Open the sleeve: remove the flat faces closing it at the cuff planes."""
    c = verts[quads].mean(axis=1)
    n = np.cross(verts[quads[:, 2]] - verts[quads[:, 0]], verts[quads[:, 3]] - verts[quads[:, 1]])
    n /= np.maximum(np.linalg.norm(n, axis=1), 1e-12)[:, None]
    keep = np.ones(len(quads), bool)
    for point, direction in planes:
        on = np.abs((c - point) @ direction) < h * 0.9
        keep &= ~(on & (n @ direction > 0.5))
    quads = quads[keep]
    used = np.unique(quads)
    remap = -np.ones(len(verts), np.int64)
    remap[used] = np.arange(len(used))
    return verts[used], remap[quads], used


def build_sleeve(build_id, kind, h=0.0024):
    """A loose fabric sleeve over the arm, open at the cuff, with folds.

    Meshed as a single surface; the add-on gives it thickness with a
    Solidify modifier, so the cloth never has holes where it is thinner
    than the mesh.
    """
    arm = anatomy.Arm(anatomy.BUILDS[build_id])
    prims = arm.skin()["arm"]
    arm_field = lambda p: arm_distance(prims, p)  # noqa: E731
    cut_spec, ease0, _th, fold, bunch = SLEEVE_CUT[kind]
    f = arm.f_dir
    if isinstance(cut_spec, tuple):
        t = cut_spec[1]
        cut_dir = arm.u_dir
        cut_point = arm.shoulder + (arm.elbow - arm.shoulder) * t
    else:
        cut_dir = f
        cut_point = arm.wrist - f * cut_spec
    shirt_cut = arm.wrist - f * 0.024
    shirt_back = arm.wrist - f * 0.11

    def ease(p):
        # folds: broad soft wrinkles, and rings of fabric bunched up towards the cuff
        n = sdf.noise3(p * 26.0, 3) * 0.7 + sdf.noise3(p * 52.0, 5) * 0.3
        along = -((p - cut_point) @ cut_dir)
        near_cuff = np.clip(1.0 - along / 0.11, 0.0, 1.0)
        rings = np.sin(along * (np.pi * 2 / 0.038) + 2.5 * sdf.noise3(p * 18.0, 9))
        rings = np.maximum(rings, -0.3)
        e = ease0 + fold * (0.7 * n + 0.5 * rings * near_cuff) + bunch * near_cuff ** 2 * (0.6 + 0.4 * n)
        if kind in ("jersey", "knit"):
            # ribbed cuff hugs the wrist
            e = e - (ease0 * 0.75) * np.clip(1.0 - along / 0.035, 0, 1)
        return np.maximum(e, 0.0015)

    def shirt_field(p):
        return _solid(arm_field, p, 0.0035 + 0.0008 * sdf.noise3(p * 90, 7), shirt_cut, f, back_point=shirt_back)

    def field(p):
        p = np.asarray(p, float).reshape(-1, 3)
        d = _solid(arm_field, p, ease(p), cut_point, cut_dir)
        if kind == "wool":
            # the shirt cuff showing below the jacket sleeve
            d = np.minimum(d, shirt_field(p))
        return d

    lo = np.min([p.aabb()[0] for p in prims], axis=0) - 0.03
    hi = np.max([p.aabb()[1] for p in prims], axis=0) + 0.03
    grid = sdf.Grid(lo, hi, h)
    axes = [grid.lo[d] + grid.h * np.arange(grid.n[d]) for d in range(3)]
    pts = np.stack(np.meshgrid(*axes, indexing="ij"), axis=-1).reshape(-1, 3)
    values = np.empty(len(pts))
    for i in range(0, len(pts), CHUNK):
        values[i:i + CHUNK] = field(pts[i:i + CHUNK])
    verts, quads = sdf.surface_nets(values.reshape(tuple(grid.n)), grid)
    verts = sdf.relax(verts, quads, field, iters=2, smooth=0.4)
    planes = [(cut_point, cut_dir)] + ([(shirt_cut, f)] if kind == "wool" else [])
    verts, quads, _used = _drop_caps(verts, quads, planes, h)
    # the sleeve moves with the skin under it, so it bends exactly like the arm, and never dips into it
    arm_data = build(build_id)
    near = _nearest(np.asarray(arm_data["verts"], float), verts)
    verts = _clear_of_skin(arm_data, verts, quads, near, SLEEVE_CUT[kind][2] + 0.0012)
    weights = skin_like(arm_data, verts, quads, near=near)
    along = -((verts - cut_point) @ cut_dir)
    hem = np.clip(1.0 - along / 0.012, 0.0, 1.0)
    shirt = np.zeros(len(verts))
    if kind == "wool":
        d_jacket = _solid(arm_field, verts, ease(verts), cut_point, cut_dir)
        shirt = (np.abs(shirt_field(verts)) < np.abs(d_jacket)).astype(float)
        hem = hem * (1 - shirt)
    return {"verts": verts.astype(np.float32), "quads": quads.astype(np.int32),
            "weights": {k: v.astype(np.float32) for k, v in weights.items()},
            "masks": {"hem": hem.astype(np.float32), "shirt": shirt.astype(np.float32)}}


def _nearest(src, dst, chunk=2000):
    """Index of the nearest ``src`` point for every ``dst`` point."""
    near = np.empty(len(dst), np.int64)
    sq = (src ** 2).sum(axis=1)
    for i in range(0, len(dst), chunk):
        near[i:i + chunk] = np.argmin(sq[None, :] - 2.0 * dst[i:i + chunk] @ src.T, axis=1)
    return near


def skin_like(arm_data, verts, quads, smooth=20, near=None):
    """Weights for a mesh over the arm: those of the nearest arm vertex, smoothed a little."""
    src_v = np.asarray(arm_data["verts"], float)
    names = sorted(arm_data["weights"])
    src_w = np.column_stack([arm_data["weights"][n] for n in names])
    if near is None:
        near = _nearest(src_v, verts)
    w = src_w[near]
    e = _edges(np.asarray(quads, np.int64))
    deg = np.maximum(np.bincount(e[:, 0], minlength=len(verts)), 1)[:, None]
    for _ in range(smooth):
        nb = np.zeros_like(w)
        np.add.at(nb, e[:, 0], w[e[:, 1]])
        w = 0.5 * w + 0.5 * nb / deg
    w /= np.maximum(w.sum(axis=1, keepdims=True), 1e-9)
    return {n: w[:, i] for i, n in enumerate(names) if w[:, i].max() > 1e-4}


def _clear_of_skin(arm_data, verts, quads, near, clearance):
    """Push cloth out along the skin's normal wherever it would sit closer to the skin than
    ``clearance`` (its own thickness grows inwards), smoothly so the folds stay soft."""
    av = np.asarray(arm_data["verts"], float)
    an = vertex_normals(av, np.asarray(arm_data["quads"], np.int64))
    gap = np.einsum("ij,ij->i", verts - av[near], an[near])
    base = np.maximum(clearance - gap, 0.0)
    e = _edges(np.asarray(quads, np.int64))
    deg = np.maximum(np.bincount(e[:, 0], minlength=len(verts)), 1)
    push = base
    for _ in range(10):
        push = np.maximum(base, 0.5 * push + 0.5 * np.bincount(e[:, 0], weights=push[e[:, 1]],
                                                               minlength=len(verts)) / deg)
    return verts + an[near] * push[:, None]


def cached_sleeve(build_id, kind, folder):
    path = os.path.join(folder, f"sleeve_{build_id.lower()}_{kind}.npz")
    data = load(path)
    if data is None:
        data = build_sleeve(build_id, kind)
        os.makedirs(folder, exist_ok=True)
        save(data, path)
        data = load(path)
    return data
