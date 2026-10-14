# SPDX-License-Identifier: GPL-3.0-or-later
"""The invisible floor: meshes the walk stands on, and finding the floor height under a point.

Floors are ordinary meshes that don't render. Edit them like any mesh (pull
up steps, tilt a ramp) and the walk follows. Any scene mesh can be a floor too.
"""

import math

import bmesh
import bpy
from mathutils import Matrix, Vector
from mathutils.bvhtree import BVHTree


def grid_mesh(name, length=8.0, width=2.0, cell=0.25):
    """A flat floor strip along +Y, starting at the origin."""
    me = bpy.data.meshes.new(name)
    bm = bmesh.new()
    nx = max(1, int(round(width / cell)))
    ny = max(1, int(round(length / cell)))
    verts = [[bm.verts.new((-width / 2 + width * i / nx, -0.5 + (length + 1.0) * j / ny, 0.0))
              for j in range(ny + 1)] for i in range(nx + 1)]
    for i in range(nx):
        for j in range(ny):
            bm.faces.new((verts[i][j], verts[i + 1][j], verts[i + 1][j + 1], verts[i][j + 1]))
    bm.to_mesh(me)
    bm.free()
    return me


def stairs_mesh(name, steps=10, rise=0.17, run=0.28, width=1.4, before=2.0, after=2.0):
    """Floor, a straight flight of stairs along +Y, and a landing at the top.

    Negative ``rise`` makes the flight go down.
    """
    me = bpy.data.meshes.new(name)
    bm = bmesh.new()
    hw = width / 2
    profile = [(-0.5, 0.0), (before, 0.0)]
    y, z = before, 0.0
    for _ in range(steps):
        z += rise
        profile.append((y, z))
        y += run
        profile.append((y, z))
    profile.append((y + after, z))
    rows = []
    for py, pz in profile:
        rows.append((bm.verts.new((-hw, py, pz)), bm.verts.new((hw, py, pz))))
    for (a0, a1), (b0, b1) in zip(rows, rows[1:]):
        if (a0.co - b0.co).length > 1e-6:
            bm.faces.new((a0, a1, b1, b0))
    bm.normal_update()
    bm.to_mesh(me)
    bm.free()
    return me


def setup_object(ob):
    """Make an object read as helper geometry: visible while working, never rendered."""
    ob.hide_render = True
    ob.display_type = "WIRE"
    ob.show_in_front = False
    for attr in ("visible_camera", "visible_diffuse", "visible_glossy", "visible_transmission",
                 "visible_volume_scatter", "visible_shadow"):
        if hasattr(ob, attr):
            setattr(ob, attr, False)


class Ground:
    """Floor height lookups against a set of floor objects (world space)."""

    def __init__(self, objects, depsgraph):
        self.trees = []
        for ob in objects:
            if ob is None or ob.type != "MESH":
                continue
            if ob.mode == "EDIT":
                bm = bmesh.from_edit_mesh(ob.data)
                tree = BVHTree.FromBMesh(bm)
            else:
                try:
                    tree = BVHTree.FromObject(ob, depsgraph)
                except (ValueError, RuntimeError):
                    continue
            mw = ob.matrix_world.copy()
            self.trees.append((tree, mw, mw.inverted_safe()))

    def __bool__(self):
        return bool(self.trees)

    def height(self, x, y, z_hint, up=0.6, down=2.5):
        """Highest floor point under (x, y) between z_hint + up and z_hint - down."""
        origin = Vector((x, y, z_hint + up))
        best = None
        for tree, mw, inv in self.trees:
            o = inv @ origin
            d = (inv.to_3x3() @ Vector((0.0, 0.0, -1.0)))
            scale = d.length
            if scale < 1e-12:
                continue
            hit, _n, _i, dist = tree.ray_cast(o, d / scale, (up + down) * scale)
            if hit is None:
                continue
            z = (mw @ hit).z
            if best is None or z > best:
                best = z
        return best

    def __call__(self, x, y, z_hint):
        return self.height(x, y, z_hint)


def conform(floor, exclude, depsgraph, lift=0.0):
    """Drop every vertex of a floor mesh onto the scene geometry below it.

    Turns a flat grid into a floor that follows the real stairs, slopes and
    paving underneath. Objects in ``exclude`` (the rig) are ignored.
    """
    scene = bpy.context.scene
    me = floor.data
    mw = floor.matrix_world
    inv = mw.inverted_safe()
    hidden = []
    for ob in exclude:
        if ob is not None and not ob.hide_viewport:
            hidden.append(ob)
            ob.hide_viewport = True
    depsgraph.update()
    moved = 0
    try:
        for v in me.vertices:
            w = mw @ v.co
            origin = Vector((w.x, w.y, w.z + 1.0))
            hit, loc, *_ = scene.ray_cast(depsgraph, origin, Vector((0, 0, -1)), distance=4.0)
            if hit:
                v.co = inv @ Vector((w.x, w.y, loc.z + lift))
                moved += 1
    finally:
        for ob in hidden:
            ob.hide_viewport = False
    me.update()
    return moved


def footprint_tris(co, yaw, side, length=0.27, width=0.10):
    """Triangles of a simple shoe sole outline lying on the floor, for the overlay."""
    pts = []
    n = 14
    for i in range(n):
        a = math.tau * i / n
        # a rounded sole: wider at the ball of the foot, narrow at the heel
        r_y = length / 2
        r_x = width / 2 * (0.78 + 0.22 * math.sin(a))
        pts.append((r_x * math.cos(a) + side * 0.008 * math.sin(a), r_y * math.sin(a)))
    rot = Matrix.Rotation(yaw - math.pi / 2, 3, "Z")
    c = Vector(co) + Vector((0, 0, 0.012))
    world = [c + rot @ Vector((x, y, 0.0)) for x, y in pts]
    tris = []
    for i in range(n):
        tris += [c, world[i], world[(i + 1) % n]]
    return tris
