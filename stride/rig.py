# SPDX-License-Identifier: GPL-3.0-or-later
"""The rig's scene objects: POV camera, start/end/waypoint boxes and floors.

A rig is identified by its camera; ``camera.stride`` holds every setting and
points at the rig's other objects, so renaming anything is safe.
"""

import math

import bmesh
import bpy
from mathutils import Matrix, Vector

from . import floor

BOX_W, BOX_H = 0.5, 1.8


def _box_mesh(name):
    """Person-sized box outline standing on its base, with an arrow showing which way it faces."""
    me = bpy.data.meshes.get(name)
    if me is not None:
        return me
    me = bpy.data.meshes.new(name)
    bm = bmesh.new()
    h = BOX_W / 2
    corners = [(-h, -h), (h, -h), (h, h), (-h, h)]
    lo = [bm.verts.new((x, y, 0.0)) for x, y in corners]
    hi = [bm.verts.new((x, y, BOX_H)) for x, y in corners]
    for i in range(4):
        bm.edges.new((lo[i], lo[(i + 1) % 4]))
        bm.edges.new((hi[i], hi[(i + 1) % 4]))
        bm.edges.new((lo[i], hi[i]))
    # facing arrow on the floor and at eye height
    for z in (0.002, 1.62):
        a = [bm.verts.new(c) for c in ((-0.12, -0.05, z), (0.12, -0.05, z), (0.0, 0.42, z))]
        for i in range(3):
            bm.edges.new((a[i], a[(i + 1) % 3]))
    bm.to_mesh(me)
    bm.free()
    return me


def _post_mesh(name):
    """Waypoint marker: a post with a ring at its base and a diamond on top."""
    me = bpy.data.meshes.get(name)
    if me is not None:
        return me
    me = bpy.data.meshes.new(name)
    bm = bmesh.new()
    ring = [bm.verts.new((0.22 * math.cos(a), 0.22 * math.sin(a), 0.0))
            for a in (math.tau * i / 16 for i in range(16))]
    for i in range(16):
        bm.edges.new((ring[i], ring[(i + 1) % 16]))
    base, top = bm.verts.new((0, 0, 0)), bm.verts.new((0, 0, 1.45))
    bm.edges.new((base, top))
    d = [bm.verts.new(c) for c in ((0.1, 0, 1.6), (0, 0.1, 1.6), (-0.1, 0, 1.6), (0, -0.1, 1.6))]
    up = bm.verts.new((0, 0, 1.75))
    for i in range(4):
        bm.edges.new((d[i], d[(i + 1) % 4]))
        bm.edges.new((d[i], top))
        bm.edges.new((d[i], up))
    bm.to_mesh(me)
    bm.free()
    return me


def _link(ob, coll):
    coll.objects.link(ob)
    return ob


def _helper(name, mesh, coll, location, yaw=0.0):
    ob = _link(bpy.data.objects.new(name, mesh), coll)
    ob.location = location
    ob.rotation_euler = (0.0, 0.0, yaw)
    floor.setup_object(ob)
    ob.lock_rotation = (True, True, False)
    ob.lock_scale = (True, True, True)
    return ob


def is_rig(ob):
    return ob is not None and ob.type == "CAMERA" and ob.stride.is_rig


def all_rigs(scene=None):
    obs = scene.objects if scene is not None else bpy.data.objects
    return [ob for ob in obs if is_rig(ob)]


def rig_objects(cam):
    """Every object belonging to the rig (helpers, arms, props), the camera included."""
    r = cam.stride
    out = {cam}
    for it in r.points:
        if it.obj is not None:
            out.add(it.obj)
    for it in r.floors:
        if it.obj is not None and it.owned:
            out.add(it.obj)
    for ob in (r.arms, r.body):
        if ob is not None:
            out.add(ob)
            out.update(ob.children_recursive)
    if r.arms is not None:
        from . import items
        out.update(items.owned(cam))      # breath smoke drifts in world space, unparented
    return out


def rig_of(ob):
    """The rig an object belongs to (its camera), or None."""
    if ob is None:
        return None
    if is_rig(ob):
        return ob
    for cam in all_rigs():
        r = cam.stride
        if any(it.obj == ob for it in r.points) or any(it.obj == ob for it in r.floors):
            return cam
        if ob in rig_objects(cam):
            return cam
    return None


def active_rig(context):
    sc = context.scene
    ob = context.active_object
    cam = rig_of(ob) if ob is not None else None
    if cam is None:
        cam = sc.stride.rig if is_rig(sc.stride.rig) else None
    if cam is None:
        rigs = all_rigs(sc)
        cam = rigs[0] if rigs else None
    return cam


def create(context, location, yaw, length=6.0, floor_from=None):
    """A complete walk: camera, start and end boxes 'length' apart, and a floor under them."""
    sc = context.scene
    coll = bpy.data.collections.new("POV Walk")
    sc.collection.children.link(coll)

    cam_data = bpy.data.cameras.new("POV Camera")
    cam_data.lens = 18.0
    cam_data.sensor_width = 36.0
    cam_data.clip_start = 0.01
    cam = _link(bpy.data.objects.new("POV Camera", cam_data), coll)
    r = cam.stride
    r.is_rig = True
    r.collection = coll
    r.frame_start = sc.frame_start

    fwd = Vector((math.cos(yaw), math.sin(yaw), 0.0))
    loc = Vector(location)
    face = yaw - math.pi / 2
    start = _helper("POV Start", _box_mesh("POV Box"), coll, loc, face)
    end = _helper("POV End", _box_mesh("POV Box"), coll, loc + fwd * length, face)
    for ob, role in ((start, "START"), (end, "END")):
        it = r.points.add()
        it.obj = ob
        it.role = role

    if floor_from is not None:
        add_floor(cam, floor_from, owned=False)
    else:
        me = floor.grid_mesh("POV Floor", length=length + 2.0, width=2.0)
        fl = _link(bpy.data.objects.new("POV Floor", me), coll)
        fl.matrix_world = Matrix.Translation(loc) @ Matrix.Rotation(face, 4, "Z")
        floor.setup_object(fl)
        add_floor(cam, fl, owned=True)

    sc.stride.rig = cam
    if sc.camera is None:
        sc.camera = cam
    return cam


def add_floor(cam, ob, owned=False):
    r = cam.stride
    for it in r.floors:
        if it.obj == ob:
            return it
    it = r.floors.add()
    it.obj = ob
    it.owned = owned
    return it


def add_waypoint(cam, location=None):
    """A waypoint before the end box (halfway between its neighbours unless placed)."""
    r = cam.stride
    pts = r.points
    end_i = len(pts) - 1
    prev, nxt = pts[end_i - 1].obj, pts[end_i].obj
    if location is None:
        location = (prev.location + nxt.location) / 2 if prev and nxt else Vector()
        # nudge it sideways so the new bend is visible
        if prev and nxt:
            d = nxt.location - prev.location
            side = Vector((-d.y, d.x, 0.0))
            if side.length > 1e-6:
                location = location + side.normalized() * min(1.0, d.length * 0.2)
    coll = r.collection or cam.users_collection[0]
    n = len(pts) - 1
    ob = _helper(f"POV Point {n}", _post_mesh("POV Post"), coll, location)
    it = pts.add()
    it.obj = ob
    it.role = "WAY"
    pts.move(len(pts) - 1, end_i)
    return ob


def add_stairs(cam, location, yaw, **kw):
    me = floor.stairs_mesh("POV Stairs", **kw)
    coll = cam.stride.collection or cam.users_collection[0]
    ob = _link(bpy.data.objects.new("POV Stairs", me), coll)
    ob.matrix_world = Matrix.Translation(location) @ Matrix.Rotation(yaw, 4, "Z")
    floor.setup_object(ob)
    add_floor(cam, ob, owned=True)
    return ob


def delete(cam):
    """Remove the rig and everything it created (not floors it borrowed from the scene)."""
    obs = rig_objects(cam)
    coll = cam.stride.collection
    for ob in obs:
        bpy.data.objects.remove(ob, do_unlink=True)
    if coll is not None and not coll.objects and not coll.children:
        bpy.data.collections.remove(coll)
