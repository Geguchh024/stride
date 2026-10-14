# SPDX-License-Identifier: GPL-3.0-or-later
"""Turn a rigged-arms glTF into Stride's arm source mesh (run once, in Blender).

    blender -b --factory-startup --python tools/import_hands.py -- rigged_arms.glb

Source: "Rigged Arms" by mrgyarmati, CC-BY-4.0,
https://sketchfab.com/3d-models/rigged-arms-76f4c7ae0b3e4cf9a57613ab991fad06
(MakeHuman-based mesh and skin texture).

Keeps the right arm, joins its triangles into quads and subdivides once,
then poses it into Stride's rest pose (straight fingers) with volume-preserving
skinning and bakes that in. The result is in the body frame in metres for the
average build, with the joints it was posed to, its skin weights renamed to
Stride's bones, and UVs into a cropped copy of the skin texture:

    stride/data/arm_source.npz, stride/data/arm_skin.jpg

handmesh.build fits it to each build's skeleton from there.
"""

import math
import os
import re
import sys

import bmesh
import bpy
import numpy as np
from mathutils import Matrix, Vector

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from stride import anatomy  # noqa: E402

DATA = os.path.join(ROOT, "stride", "data")
PALM = 0.100                    # wrist to middle knuckle, metres
FLIP = np.diag([-1.0, -1.0, 1.0])  # the glTF character faces -Y; Stride's body faces +Y
SUBDIV = 1


def stride_name(glb):
    """'index_02_r_024' -> 'index.02', 'lowerarm_r_021' -> 'forearm'; None for the left side."""
    m = re.match(r"^(thumb|index|middle|ring|pinky)_(\d\d)_r(_end)?_\d+$", glb)
    if m:
        return f"{m.group(1)}.{m.group(2)}"
    m = re.match(r"^(clavicle|upperarm|lowerarm|hand)_r_\d+$", glb)
    if m:
        return {"clavicle": "clavicle", "upperarm": "upper_arm", "lowerarm": "forearm", "hand": "hand"}[m.group(1)]
    if glb == "_rootJoint":
        return "clavicle"
    return None


def load(path):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.import_scene.gltf(filepath=path)
    rig = next(o for o in bpy.data.objects if o.type == "ARMATURE")
    ob = next(o for o in bpy.data.objects if o.type == "MESH" and o.vertex_groups)
    for pb in rig.pose.bones:
        pb.rotation_mode = "QUATERNION"
        pb.rotation_quaternion = (1, 0, 0, 0)
        pb.location = (0, 0, 0)
        pb.scale = (1, 1, 1)
    rig.data.pose_position = "POSE"
    bpy.context.view_layer.update()
    return rig, ob


def keep_right_arm(ob):
    """Drop the left arm, weld the seams, cap the shoulder, join the triangles into quads, subdivide once (weights and UVs follow)."""
    mw = ob.matrix_world
    bm = bmesh.new()
    bm.from_mesh(ob.data)
    bmesh.ops.delete(bm, geom=[v for v in bm.verts if (mw @ v.co).x > 0.0], context="VERTS")
    # glTF splits vertices along UV seams; weld them or subdividing opens cracks there
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-4)
    # close the shoulder end (hidden by the sleeve) so the surface is watertight
    bmesh.ops.holes_fill(bm, edges=bm.edges, sides=0)
    bmesh.ops.join_triangles(bm, faces=bm.faces, angle_face_threshold=math.radians(40),
                             angle_shape_threshold=math.radians(40), cmp_uvs=True)
    bm.to_mesh(ob.data)
    bm.free()
    sub = ob.modifiers.new("Subdivide", "SUBSURF")
    sub.levels = SUBDIV
    sub.uv_smooth = "PRESERVE_BOUNDARIES"
    with bpy.context.temp_override(object=ob, active_object=ob):
        bpy.ops.object.modifier_move_to_index(modifier=sub.name, index=0)
        bpy.ops.object.modifier_apply(modifier=sub.name)


def group_weights(ob):
    me = ob.data
    names = [g.name for g in ob.vertex_groups]
    w = np.zeros((len(me.vertices), len(names)))
    for v in me.vertices:
        for g in v.groups:
            w[v.index, g.group] = g.weight
    out = {}
    for i, n in enumerate(names):
        s = stride_name(n)
        if s is not None and w[:, i].max() > 0:
            out[s] = out.get(s, 0) + w[:, i]
    total = np.maximum(sum(out.values()), 1e-9)
    return {k: v / total for k, v in out.items()}


def tail_points(rig, ob, weights):
    """Armature-space point each bone aims with: its tail, or the fingertip for end bones
    (the glTF's last finger bones have meaningless tails)."""
    inv = rig.matrix_world.inverted()
    mw = ob.matrix_world
    co = [inv @ (mw @ v.co) for v in ob.data.vertices]
    pts = {}
    for b in rig.data.bones:
        s = stride_name(b.name)
        if s is None or b.name.endswith(tuple(f"_end_{i:03d}" for i in range(100))) or b.name == "_rootJoint":
            continue
        tail = b.tail_local.copy()
        if s.endswith(".03"):
            d = (b.head_local - b.parent.head_local).normalized()
            idx = np.nonzero(weights[s] > 0.3)[0]
            far = max(idx, key=lambda i: (co[i] - b.head_local).dot(d))
            tail = co[far]
        pts[b.name] = (s, b.matrix_local.inverted() @ tail)
    return pts


def glb_hand_frame(rig):
    """The glTF hand's frame in Stride's hand-space convention, in the flipped world."""
    mw = rig.matrix_world

    def head(n):
        return FLIP @ np.array(mw @ rig.data.bones[n].head_local)
    names = {stride_name(b.name): b.name for b in rig.data.bones if stride_name(b.name)}
    w = head(names["hand"])
    m = head(names["middle.01"])
    i = head(names["index.01"])
    p = head(names["pinky.01"])
    y = (m - w) / np.linalg.norm(m - w)
    x = p - i
    x -= y * (x @ y)
    x /= np.linalg.norm(x)
    return np.column_stack([x, y, np.cross(x, y)]), PALM / np.linalg.norm(m - w)


def pose_to_stride(rig, pts, arm, frame):
    """Aim every bone along its Stride rest direction (the hand keeps its own orientation)."""
    targets = {name: (np.asarray(tail) - np.asarray(head)) for name, head, tail, *_ in arm.bones()}
    body_to_glb = frame @ arm.hand_rot.T          # body frame -> flipped glTF world
    arm_inv = rig.matrix_world.to_3x3().inverted()
    depth = {b.name: len(b.parent_recursive) for b in rig.data.bones}
    for b in sorted(rig.data.bones, key=lambda b: depth[b.name]):
        if b.name not in pts:
            continue
        s, local_tail = pts[b.name]
        pb = rig.pose.bones[b.name]
        bpy.context.view_layer.update()
        m = pb.matrix.copy()
        if s == "hand":
            new = Matrix.Translation(m.translation) @ b.matrix_local.to_3x3().to_4x4()
        else:
            cur = (m @ local_tail - m.translation).normalized()
            want = arm_inv @ Vector(FLIP @ (body_to_glb @ targets[s]))
            q = cur.rotation_difference(want.normalized())
            new = Matrix.Translation(m.translation) @ (q.to_matrix() @ m.to_3x3()).to_4x4()
        pb.matrix = new
    bpy.context.view_layer.update()


def main():
    src = sys.argv[sys.argv.index("--") + 1]
    rig, ob = load(src)
    keep_right_arm(ob)
    weights = group_weights(ob)
    pts = tail_points(rig, ob, weights)
    frame, k = glb_hand_frame(rig)
    arm = anatomy.Arm()
    pose_to_stride(rig, pts, arm, frame)

    mod = next(m for m in ob.modifiers if m.type == "ARMATURE")
    mod.use_deform_preserve_volume = True
    dg = bpy.context.evaluated_depsgraph_get()
    ev = ob.evaluated_get(dg)
    me = ev.to_mesh()
    mw = np.array(ob.matrix_world)
    co = np.array([v.co for v in me.vertices])
    co = co @ mw[:3, :3].T + mw[:3, 3]
    ev.to_mesh_clear()

    # posed glTF world -> body frame, metres: the hand lands on the average build's wrist
    rw = np.array(rig.matrix_world)
    names = {stride_name(b.name): b.name for b in rig.data.bones if b.name in pts}
    wrist = FLIP @ (rw @ np.append(np.array(rig.pose.bones[names["hand"]].head), 1.0))[:3]
    to_body = arm.hand_rot @ frame.T

    def body(p):
        return arm.wrist + ((np.asarray(p) @ FLIP.T) - wrist) @ to_body.T * k
    verts = body(co)
    joints = {}
    for gname, (s, local_tail) in pts.items():
        pb = rig.pose.bones[gname]
        h = (rw @ np.append(np.array(pb.head), 1.0))[:3]
        t = (rw @ np.append(np.array(pb.matrix @ local_tail), 1.0))[:3]
        joints[s] = np.array([body(h), body(t)])

    base = ob.data
    sizes = np.array([len(p.vertices) for p in base.polygons])
    assert np.all(sizes == 4), np.bincount(sizes)
    quads = np.array([p.vertices[:] for p in base.polygons], np.int32)
    uv = np.zeros((len(base.loops), 2))
    base.uv_layers.active.data.foreach_get("uv", uv.ravel())

    # crop the texture to what the arm uses
    img = base.materials[0].node_tree.nodes["Image Texture"].image
    w, h = img.size
    px = np.array(img.pixels[:], np.float32).reshape(h, w, img.channels)
    lo = np.floor(uv.min(axis=0) * (w, h)).astype(int) - 8
    hi = np.ceil(uv.max(axis=0) * (w, h)).astype(int) + 8
    lo = np.maximum(lo, 0)
    hi = np.minimum(hi, (w, h))
    crop = px[lo[1]:hi[1], lo[0]:hi[0]]
    uv = (uv * (w, h) - lo) / (hi - lo)
    out = bpy.data.images.new("arm_skin", crop.shape[1], crop.shape[0], alpha=False)
    out.pixels.foreach_set(np.ascontiguousarray(crop[..., :4] if crop.shape[2] == 4 else
                                                np.dstack([crop, np.ones(crop.shape[:2])])).ravel())
    out.filepath_raw = os.path.join(DATA, "arm_skin.jpg")
    out.file_format = "JPEG"
    bpy.context.scene.render.image_settings.quality = 92
    out.save()

    arrays = {"verts": verts.astype(np.float32), "quads": quads, "uv": uv.astype(np.float32)}
    for kname, v in weights.items():
        arrays["w_" + kname] = v.astype(np.float32)
    for kname, v in joints.items():
        arrays["j_" + kname] = v.astype(np.float32)
    np.savez_compressed(os.path.join(DATA, "arm_source.npz"), **arrays)
    print(f"arm source: {len(verts)} verts, {len(quads)} quads, texture {crop.shape[1]}x{crop.shape[0]}")


if __name__ == "__main__":
    main()
