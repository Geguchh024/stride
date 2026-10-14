# SPDX-License-Identifier: GPL-3.0-or-later
"""The POV arms in Blender: armature, skinned arm and sleeve meshes, materials, the watch."""

import os

import bmesh
import bpy
import numpy as np
from mathutils import Vector

from . import anatomy, handmesh, items, materials

SIDES = (("R", 1), ("L", -1))
PACKAGE_DATA = os.path.join(os.path.dirname(__file__), "data")


def cache_dir():
    """Prebuilt meshes ship in data/; anything else is built once into the user's cache."""
    try:
        return bpy.utils.extension_path_user(__package__, path="cache", create=True)
    except (ValueError, AttributeError, RuntimeError):
        return bpy.utils.user_resource("CONFIG", path="stride_cache", create=True)


def _arm_data(build_id):
    data = handmesh.load(os.path.join(PACKAGE_DATA, f"arm_{build_id.lower()}.npz"))
    return data or handmesh.cached(build_id, cache_dir())


def _sleeve_data(build_id, kind):
    data = handmesh.load(os.path.join(PACKAGE_DATA, f"sleeve_{build_id.lower()}_{kind}.npz"))
    return data or handmesh.cached_sleeve(build_id, kind, cache_dir())


def _mirror_point(p, sign):
    return Vector((p[0] * sign, p[1], p[2]))


def build_armature(name, arm, coll):
    data = bpy.data.armatures.new(name)
    data.display_type = "OCTAHEDRAL"
    ob = bpy.data.objects.new(name, data)
    coll.objects.link(ob)
    ob.show_in_front = False
    view_layer = bpy.context.view_layer
    prev_active = view_layer.objects.active
    if bpy.context.mode != "OBJECT" and bpy.context.object is not None:
        bpy.ops.object.mode_set(mode="OBJECT")
    view_layer.objects.active = ob
    bpy.ops.object.mode_set(mode="EDIT")
    try:
        for suffix, sign in SIDES:
            for bname, head, tail, zref, parent, connect in arm.bones():
                eb = data.edit_bones.new(f"{bname}.{suffix}")
                eb.head = _mirror_point(head, sign)
                eb.tail = _mirror_point(tail, sign)
                eb.align_roll(_mirror_point(zref, sign))
                if parent:
                    eb.parent = data.edit_bones[f"{parent}.{suffix}"]
                    eb.use_connect = connect
                eb.use_deform = True
    finally:
        bpy.ops.object.mode_set(mode="OBJECT")
        view_layer.objects.active = prev_active
    for pb in ob.pose.bones:
        pb.rotation_mode = "QUATERNION"
    return ob


def build_mesh(name, data, suffix, sign):
    v = data["verts"].astype(np.float64).copy()
    q = data["quads"]
    if sign < 0:
        v[:, 0] *= -1
        q = q[:, ::-1]
    me = bpy.data.meshes.new(name)
    me.vertices.add(len(v))
    me.vertices.foreach_set("co", v.ravel())
    me.loops.add(q.size)
    me.loops.foreach_set("vertex_index", q.ravel())
    me.polygons.add(len(q))
    me.polygons.foreach_set("loop_start", np.arange(0, q.size, 4))
    me.update(calc_edges=True)
    me.polygons.foreach_set("use_smooth", np.ones(len(q), bool))
    uv = data.get("uv")
    if uv is not None:
        if sign < 0:
            uv = uv.reshape(-1, 4, 2)[:, ::-1].reshape(-1, 2)
        me.uv_layers.new(name="UVMap").data.foreach_set("uv", np.ascontiguousarray(uv, np.float32).ravel())
    rest = me.attributes.new("rest", "FLOAT_VECTOR", "POINT")
    rest.data.foreach_set("vector", v.astype(np.float32).ravel())
    for key, arr in data["masks"].items():
        a = me.attributes.new(key, "FLOAT", "POINT")
        a.data.foreach_set("value", np.asarray(arr, np.float32))
    me.update()
    return me


def assign_weights(ob, weights, suffix):
    me = ob.data
    names = sorted(weights)
    for bname in names:
        ob.vertex_groups.new(name=f"{bname}.{suffix}")
    bm = bmesh.new()
    bm.from_mesh(me)
    dl = bm.verts.layers.deform.verify()
    bm.verts.ensure_lookup_table()
    for gi, bname in enumerate(names):
        w = weights[bname]
        for i in np.nonzero(w > 1e-4)[0]:
            bm.verts[int(i)][dl][gi] = float(w[i])
    bm.to_mesh(me)
    bm.free()


def _skinned(name, data, suffix, sign, rig_ob, coll, mats):
    me = build_mesh(name, data, suffix, sign)
    for m in mats:
        me.materials.append(m)
    ob = bpy.data.objects.new(name, me)
    coll.objects.link(ob)
    ob.parent = rig_ob
    assign_weights(ob, data["weights"], suffix)
    # the meshes are dense already: render subdivision would cost ~25 s a frame for no visible gain
    mod = ob.modifiers.new("Armature", "ARMATURE")
    mod.object = rig_ob
    return ob


def add(cam, build_id="AVERAGE", tone="LIGHT", sleeve="JACKET", watch=True):
    """Give a rig its arms. Returns the armature object."""
    r = cam.stride
    if r.arms is not None:
        remove(cam)
    coll = r.collection or cam.users_collection[0]
    arm = anatomy.Arm(anatomy.BUILDS[build_id])
    rig_ob = build_armature("POV Arms", arm, coll)
    rig_ob["stride_build"] = build_id
    r.arms = rig_ob
    data = _arm_data(build_id)
    skin = materials.skin(f"POV Skin {tone.title()}", materials.TONE_BY_ID[tone])
    for suffix, sign in SIDES:
        _skinned(f"POV Arm.{suffix}", data, suffix, sign, rig_ob, coll, [skin])
    set_sleeve(cam, sleeve)
    if watch:
        items.add_watch(cam)
    rig_ob.hide_select = False
    return rig_ob


def arm_meshes(cam):
    rig_ob = cam.stride.arms
    if rig_ob is None:
        return []
    return [c for c in rig_ob.children if c.type == "MESH" and c.name.startswith("POV Arm")]


def sleeve_meshes(cam):
    rig_ob = cam.stride.arms
    if rig_ob is None:
        return []
    return [c for c in rig_ob.children if c.type == "MESH" and c.get("stride_sleeve")]


def set_sleeve(cam, sleeve):
    rig_ob = cam.stride.arms
    if rig_ob is None:
        return
    for ob in sleeve_meshes(cam):
        me = ob.data
        bpy.data.objects.remove(ob, do_unlink=True)
        if me.users == 0:
            bpy.data.meshes.remove(me)
    rig_ob["stride_sleeve"] = sleeve
    kind = materials.SLEEVE_BY_ID[sleeve][6]
    if kind == "none":
        return
    if sleeve == "TSHIRT":
        kind = "tee"
    build_id = rig_ob.get("stride_build", "AVERAGE")
    data = _sleeve_data(build_id, kind)
    coll = rig_ob.users_collection[0]
    mat = materials.fabric(f"POV Sleeve {materials.SLEEVE_BY_ID[sleeve][1]}", sleeve)
    th = handmesh.SLEEVE_CUT[kind][2]
    for suffix, sign in SIDES:
        ob = _skinned(f"POV Sleeve.{suffix}", data, suffix, sign, rig_ob, coll, [mat])
        ob["stride_sleeve"] = sleeve
        # cloth thickness, after the deform so the rim follows the arm
        sol = ob.modifiers.new("Thickness", "SOLIDIFY")
        sol.thickness = th
        sol.offset = -1.0
        sol.use_rim = True
        # plain offset: 'even thickness' explodes on the odd near-degenerate face of a meshed surface
        sol.use_even_offset = False


def set_tone(cam, tone):
    skin = materials.skin(f"POV Skin {tone.title()}", materials.TONE_BY_ID[tone])
    for ob in arm_meshes(cam):
        ob.data.materials[0] = skin
    if cam.stride.arms is not None:
        cam.stride.arms["stride_tone"] = tone


def remove(cam):
    rig_ob = cam.stride.arms
    if rig_ob is None:
        return
    for ob in list(rig_ob.children_recursive):
        data = ob.data
        bpy.data.objects.remove(ob, do_unlink=True)
        if data is not None and data.users == 0 and isinstance(data, bpy.types.Mesh):
            bpy.data.meshes.remove(data)
    data = rig_ob.data
    bpy.data.objects.remove(rig_ob, do_unlink=True)
    if data.users == 0:
        bpy.data.armatures.remove(data)
    cam.stride.arms = None


def rest_matrices(rig_ob):
    return {b.name: b.matrix_local.copy() for b in rig_ob.data.bones}



