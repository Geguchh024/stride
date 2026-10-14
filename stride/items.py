# SPDX-License-Identifier: GPL-3.0-or-later
"""Props for the hands: cigarette, phone, cup, bottle, flashlight, watch and breath smoke.

Each prop is built from code (no image files), lives in the rig's collection
and is keyed per frame from the posed hand, so it never slips in the grip.
Grips are written for the right hand in a bone's own frame (origin at the
bone's head, +Y along the bone, +Z the back of the hand, +X the little-finger
side); the left hand mirrors them.
"""

import math
from dataclasses import dataclass

import bmesh
import bpy
import numpy as np
from mathutils import Matrix, Vector

from . import materials


@dataclass
class Grip:
    points: tuple            # ((bone, t along bone), ...) averaged into the grip point
    frame: str               # bone whose axes orient the prop
    offset: tuple            # prop origin from the grip point, in that bone's axes
    y: tuple                 # prop +Y in that bone's axes
    z: tuple                 # prop +Z in that bone's axes


GRIPS = {
    # cigarette between index and middle finger: filter on the palm side, lit end out the back
    "CIG_V": Grip((("index.01", 0.86), ("middle.01", 0.86)), "index.01", (0.0, 0.0, -0.016),
                  (0.0, 0.08, 1.0), (0.0, 1.0, 0.0)),
    # phone upright across the palm (top towards the thumb), screen facing the same way as the palm;
    # its far edge just short of the middle finger joints, which the fingers curl round. These offsets
    # and the grip poses were fitted so the skin touches the props without going into them.
    "PHONE": Grip((("hand", 0.80),), "hand", (-0.020, 0.011, -0.0335), (-1.0, 0.0, 0.0), (0.0, 0.0, -1.0)),
    # cylinders across the palm: the top points out of the thumb side
    "CUP": Grip((("hand", 0.80),), "hand", (0.008, -0.004, -0.062), (0.0, 1.0, 0.0), (-1.0, 0.0, 0.0)),
    "BOTTLE": Grip((("hand", 0.80),), "hand", (0.012, 0.0, -0.060), (0.0, 1.0, 0.0), (-1.0, 0.0, 0.0)),
    # power grip: the tube runs diagonally across the palm, out between thumb and index finger
    "TUBE": Grip((("hand", 0.80),), "hand", (-0.004, 0.002, -0.034), (-0.74, 0.67, 0.0), (0.0, 0.0, 1.0)),
}

# where on a prop (its own coordinates) a 'prop_to' key puts the target, e.g. the mouth
TIPS = {
    "CIGARETTE": (0.0, 0.0, 0.0),            # the filter end
    "CUP": (0.0, -0.034, 0.112),             # the lid's sip hole
    "BOTTLE": (0.0, 0.0, 0.205),             # the bottle's mouth
}


def _new_object(name, me, coll):
    ob = bpy.data.objects.new(name, me)
    coll.objects.link(ob)
    return ob


def _lathe(name, profile, segments=32, caps=True):
    """Mesh of revolution about +Z from (radius, z) points."""
    me = bpy.data.meshes.new(name)
    bm = bmesh.new()
    rings = []
    for r, z in profile:
        ring = []
        for i in range(segments):
            a = math.tau * i / segments
            ring.append(bm.verts.new((r * math.cos(a), r * math.sin(a), z)))
        rings.append(ring)
    for r0, r1 in zip(rings, rings[1:]):
        for i in range(segments):
            j = (i + 1) % segments
            bm.faces.new((r0[i], r0[j], r1[j], r1[i]))
    if caps:
        bm.faces.new(list(reversed(rings[0])))
        bm.faces.new(rings[-1])
    bm.normal_update()
    bm.to_mesh(me)
    bm.free()
    for p in me.polygons:
        p.use_smooth = True
    return me


def _rounded_box(name, size, radius, segments=4):
    me = bpy.data.meshes.new(name)
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0)
    bmesh.ops.scale(bm, vec=Vector(size), verts=bm.verts)
    bmesh.ops.bevel(bm, geom=list(bm.edges), offset=radius, segments=segments, profile=0.5,
                    affect="EDGES", clamp_overlap=True)
    bm.to_mesh(me)
    bm.free()
    for p in me.polygons:
        p.use_smooth = True
    return me


def _assign(me, mat_by_face):
    """mat_by_face(polygon) -> material index."""
    idx = np.array([mat_by_face(p) for p in me.polygons], np.int32)
    me.polygons.foreach_set("material_index", idx)


# -- builders ---------------------------------------------------------------------------

def _cigarette(coll):
    # along +Y from the filter end (origin) to the lit end
    length, r = 0.084, 0.0039
    prof = [(0.0001, 0.0), (r * 0.92, 0.0), (r, 0.0012), (r, 0.025), (r, 0.0251), (r, length - 0.006),
            (r * 0.98, length - 0.0015), (r * 0.8, length), (0.0001, length + 0.0006)]
    me = _lathe("POV Cigarette", prof, segments=20, caps=False)
    me.transform(Matrix.Rotation(-math.pi / 2, 4, "X"))
    filt = materials.simple("POV Cigarette Filter", (0.62, 0.36, 0.16), rough=0.6)
    paper = materials.simple("POV Cigarette Paper", (0.82, 0.81, 0.78), rough=0.55)
    ember = _ember_material()
    for m in (filt, paper, ember):
        me.materials.append(m)
    _assign(me, lambda p: 0 if p.center.y < 0.025 else (1 if p.center.y < length - 0.0058 else 2))
    ob = _new_object("POV Cigarette", me, coll)
    ob["ember"] = 0.15
    return ob


def _ember_material():
    mat = bpy.data.materials.get("POV Cigarette Ember") or bpy.data.materials.new("POV Cigarette Ember")
    n = materials.Nodes(mat)
    out = n.new("ShaderNodeOutputMaterial", 500, 0)
    bsdf = n.new("ShaderNodeBsdfPrincipled", 250, 0)
    n.link(bsdf.outputs[0], out.inputs["Surface"])
    bsdf.inputs["Base Color"].default_value = (0.06, 0.055, 0.05, 1.0)
    bsdf.inputs["Roughness"].default_value = 0.9
    bsdf.inputs["Emission Color"].default_value = (1.0, 0.22, 0.03, 1.0)
    # glow: ash flecks, brighter on a drag (object property 'ember')
    tex = n.new("ShaderNodeTexNoise", -500, -100, Scale=2500.0, Detail=3.0)
    ramp = n.new("ShaderNodeMapRange", -300, -100, From_Min=0.45, From_Max=0.65, To_Min=0.0, To_Max=1.0)
    n.link(tex.outputs["Fac"], ramp.inputs["Value"])
    attr = n.new("ShaderNodeAttribute", -500, 150)
    attr.attribute_type = "OBJECT"
    attr.attribute_name = "ember"
    mul = n.new("ShaderNodeMath", -100, 0, _operation="MULTIPLY")
    n.link(ramp.outputs[0], mul.inputs[0])
    n.link(attr.outputs["Fac"], mul.inputs[1])
    strength = n.new("ShaderNodeMath", 50, 0, _operation="MULTIPLY")
    strength.inputs[1].default_value = 60.0
    n.link(mul.outputs[0], strength.inputs[0])
    n.link(strength.outputs[0], bsdf.inputs["Emission Strength"])
    return mat


def _phone(coll):
    w, h, d = 0.0715, 0.147, 0.0079
    me = _rounded_box("POV Phone", (w, h, d), 0.0035, segments=3)
    frame = materials.simple("POV Phone Frame", (0.05, 0.05, 0.055), rough=0.3, metal=1.0)
    back = materials.simple("POV Phone Back", (0.02, 0.022, 0.026), rough=0.25)
    screen = _screen_material()
    for m in (frame, back, screen):
        me.materials.append(m)
    _assign(me, lambda p: 2 if (p.normal.z > 0.9 and abs(p.center.x) < w / 2 - 0.003
                                 and abs(p.center.y) < h / 2 - 0.003)
            else (1 if p.normal.z < -0.9 else 0))
    # camera bump on the back
    ob = _new_object("POV Phone", me, coll)
    ob["screen"] = 0.0
    return ob


def _screen_material():
    """A phone screen: a map-like app, drawn into a small packed image."""
    mat = bpy.data.materials.get("POV Phone Screen") or bpy.data.materials.new("POV Phone Screen")
    img = bpy.data.images.get("POV Phone UI")
    if img is None:
        img = _phone_ui()
    n = materials.Nodes(mat)
    out = n.new("ShaderNodeOutputMaterial", 600, 0)
    bsdf = n.new("ShaderNodeBsdfPrincipled", 300, 0)
    n.link(bsdf.outputs[0], out.inputs["Surface"])
    bsdf.inputs["Base Color"].default_value = (0.004, 0.004, 0.005, 1.0)
    bsdf.inputs["Roughness"].default_value = 0.05
    bsdf.inputs["Coat Weight"].default_value = 1.0
    coord = n.new("ShaderNodeTexCoord", -700, 0)
    mapping = n.new("ShaderNodeMapping", -500, 0)
    mapping.inputs["Location"].default_value = (0.5, 0.5, 0.0)
    mapping.inputs["Scale"].default_value = (1 / 0.066, 1 / 0.142, 1.0)
    n.link(coord.outputs["Object"], mapping.inputs["Vector"])
    tex = n.new("ShaderNodeTexImage", -300, 0)
    tex.image = img
    tex.extension = "CLIP"
    n.link(mapping.outputs[0], tex.inputs["Vector"])
    n.link(tex.outputs["Color"], bsdf.inputs["Emission Color"])
    attr = n.new("ShaderNodeAttribute", -300, -250)
    attr.attribute_type = "OBJECT"
    attr.attribute_name = "screen"
    st = n.new("ShaderNodeMath", 0, -250, _operation="MULTIPLY")
    st.inputs[1].default_value = 1.6
    n.link(attr.outputs["Fac"], st.inputs[0])
    n.link(st.outputs[0], bsdf.inputs["Emission Strength"])
    return mat


def _phone_ui(w=256, h=552):
    """Draw a simple map app: streets, a route, a pin and a bottom card."""
    rng = np.random.default_rng(7)
    px = np.zeros((h, w, 4), np.float32)
    px[..., :3] = (0.93, 0.92, 0.88)
    px[..., 3] = 1.0
    yy, xx = np.mgrid[0:h, 0:w]
    # parks and water
    for _ in range(5):
        cx, cy, r = rng.integers(0, w), rng.integers(80, h - 120), rng.integers(20, 55)
        m = (xx - cx) ** 2 + (yy - cy) ** 2 < r * r
        px[m, :3] = (0.70, 0.86, 0.62)
    m = (xx + yy * 0.4) % 400 < 40
    px[m & (yy > 300), :3] = (0.62, 0.78, 0.95)
    # streets
    for k in range(9):
        a = rng.uniform(-0.5, 0.5)
        off = rng.uniform(0, h)
        d = np.abs(yy - (off + a * xx))
        px[d < 3.5, :3] = (1.0, 1.0, 1.0)
        px[(d >= 3.5) & (d < 4.5), :3] = (0.8, 0.8, 0.78)
    for k in range(6):
        x0 = rng.uniform(0, w)
        d = np.abs(xx - x0 - 0.15 * yy)
        px[d < 3.0, :3] = (1.0, 1.0, 1.0)
    # route and pin
    route = np.abs(xx - (w * 0.5 + 40 * np.sin(yy / 70.0))) < 4
    px[route & (yy > 180) & (yy < 430), :3] = (0.15, 0.45, 0.95)
    pin = (xx - w * 0.5 - 40 * np.sin(180 / 70.0)) ** 2 + (yy - 180) ** 2 < 100
    px[pin, :3] = (0.92, 0.2, 0.18)
    # status bar (top) and a card (bottom); rows are bottom-up in Blender images
    px[h - 22:, :, :3] = (0.98, 0.98, 0.98)
    px[:120, :, :3] = (0.99, 0.99, 0.99)
    px[95:105, 20:170, :3] = (0.2, 0.2, 0.22)
    px[70:80, 20:120, :3] = (0.55, 0.55, 0.58)
    px[22:52, 20:w - 20, :3] = (0.15, 0.45, 0.95)
    img = bpy.data.images.new("POV Phone UI", w, h, alpha=False)
    img.pixels.foreach_set(px.ravel())
    img.pack()
    return img


def _cup(coll):
    # paper to-go cup with lid and sleeve, up is +Z, origin at the base
    prof = [(0.0001, 0.0), (0.028, 0.0), (0.029, 0.002), (0.039, 0.098), (0.0405, 0.100), (0.0405, 0.103),
            (0.0398, 0.105), (0.036, 0.106), (0.034, 0.112), (0.006, 0.113), (0.0001, 0.113)]
    me = _lathe("POV Cup", prof, segments=40, caps=False)
    paper = materials.simple("POV Cup Paper", (0.85, 0.84, 0.80), rough=0.6)
    lid = materials.simple("POV Cup Lid", (0.03, 0.03, 0.03), rough=0.35)
    sleeve = materials.simple("POV Cup Sleeve", (0.42, 0.26, 0.13), rough=0.85)
    for m in (paper, lid, sleeve):
        me.materials.append(m)
    _assign(me, lambda p: 1 if p.center.z > 0.1005 else (2 if 0.035 < p.center.z < 0.080 else 0))
    return _new_object("POV Cup", me, coll)


def _bottle(coll):
    prof = [(0.0001, 0.0), (0.030, 0.0), (0.0325, 0.004), (0.0325, 0.120), (0.031, 0.140), (0.020, 0.170),
            (0.0135, 0.185), (0.0135, 0.188), (0.0145, 0.189), (0.0145, 0.205), (0.0001, 0.2055)]
    me = _lathe("POV Bottle", prof, segments=36, caps=False)
    plastic = materials.simple("POV Bottle Plastic", (0.85, 0.92, 0.95), rough=0.05, transmission=1.0)
    label = materials.simple("POV Bottle Label", (0.05, 0.35, 0.75), rough=0.4)
    cap = materials.simple("POV Bottle Cap", (0.9, 0.9, 0.92), rough=0.4)
    for m in (plastic, label, cap):
        me.materials.append(m)
    _assign(me, lambda p: 2 if p.center.z > 0.1885 else (1 if 0.05 < p.center.z < 0.11 else 0))
    return _new_object("POV Bottle", me, coll)


def _flashlight(coll):
    # beam along +Y from the tail (origin)
    prof = [(0.0001, 0.0), (0.0125, 0.0), (0.0135, 0.004), (0.0135, 0.105), (0.0185, 0.125), (0.0195, 0.150),
            (0.0185, 0.152), (0.0155, 0.150)]
    me = _lathe("POV Flashlight", prof, segments=32, caps=False)
    me.transform(Matrix.Translation((0, -0.055, 0)) @ Matrix.Rotation(-math.pi / 2, 4, "X"))
    body = materials.simple("POV Flashlight Body", (0.02, 0.02, 0.022), rough=0.35, metal=1.0)
    lens = materials.simple("POV Flashlight Lens", (1.0, 1.0, 1.0), rough=0.1, emit=(1.0, 0.92, 0.8), strength=0.0)
    for m in (body, lens):
        me.materials.append(m)
    _assign(me, lambda p: 1 if p.center.y > 0.0945 else 0)
    ob = _new_object("POV Flashlight", me, coll)
    lamp = bpy.data.lights.new("POV Flashlight Beam", "SPOT")
    lamp.energy = 25.0
    lamp.spot_size = math.radians(40)
    lamp.spot_blend = 0.55
    lamp.shadow_soft_size = 0.01
    lamp.color = (1.0, 0.93, 0.82)
    beam = _new_object("POV Flashlight Beam", lamp, coll)
    beam.parent = ob
    beam.matrix_parent_inverse = Matrix.Identity(4)
    beam.matrix_basis = Matrix.Translation((0, 0.10, 0)) @ Matrix.Rotation(-math.pi / 2, 4, "X")
    ob["light"] = 0.0
    return ob


def _smoke(coll):
    """A breath of smoke: a volume blob that drifts and spreads after it is breathed out."""
    me = bpy.data.meshes.new("POV Smoke")
    bm = bmesh.new()
    bmesh.ops.create_icosphere(bm, subdivisions=3, radius=1.0)
    bm.to_mesh(me)
    bm.free()
    mat = bpy.data.materials.get("POV Smoke") or bpy.data.materials.new("POV Smoke")
    n = materials.Nodes(mat)
    out = n.new("ShaderNodeOutputMaterial", 600, 0)
    vol = n.new("ShaderNodeVolumePrincipled", 300, 0)
    vol.inputs["Color"].default_value = (0.75, 0.78, 0.82, 1.0)
    vol.inputs["Anisotropy"].default_value = 0.3
    n.link(vol.outputs[0], out.inputs["Volume"])
    coord = n.new("ShaderNodeTexCoord", -900, 0)
    noise = n.new("ShaderNodeTexNoise", -650, 100, Scale=2.2, Detail=6.0, Roughness=0.6, Distortion=0.8)
    n.link(coord.outputs["Object"], noise.inputs["Vector"])
    length = n.new("ShaderNodeVectorMath", -650, -150, _operation="LENGTH")
    n.link(coord.outputs["Object"], length.inputs[0])
    fall = n.new("ShaderNodeMapRange", -450, -150, From_Min=0.2, From_Max=1.0, To_Min=1.0, To_Max=0.0)
    n.link(length.outputs["Value"], fall.inputs["Value"])
    wisps = n.new("ShaderNodeMapRange", -450, 100, From_Min=0.45, From_Max=0.75, To_Min=0.0, To_Max=1.0)
    n.link(noise.outputs["Fac"], wisps.inputs["Value"])
    mul = n.new("ShaderNodeMath", -250, 0, _operation="MULTIPLY")
    n.link(wisps.outputs[0], mul.inputs[0])
    n.link(fall.outputs[0], mul.inputs[1])
    attr = n.new("ShaderNodeAttribute", -250, -250)
    attr.attribute_type = "OBJECT"
    attr.attribute_name = "density"
    dens = n.new("ShaderNodeMath", 0, 0, _operation="MULTIPLY")
    n.link(mul.outputs[0], dens.inputs[0])
    n.link(attr.outputs["Fac"], dens.inputs[1])
    n.link(dens.outputs[0], vol.inputs["Density"])
    me.materials.append(mat)
    ob = _new_object("POV Smoke", me, coll)
    ob["density"] = 0.0
    ob.display_type = "WIRE"
    return ob


def _watch(coll, rx=0.0335, rz=0.0225, cx=0.0, cz=0.0):
    """Wristwatch for the left wrist (+Y along the arm, +Z face up): an elliptical strap of half-sizes
    rx, rz round (cx, cz) in the forearm's axes, the case on top."""
    me = bpy.data.meshes.new("POV Watch")
    bm = bmesh.new()
    # strap: an elliptical band around the wrist
    seg, half_w = 48, 0.0095
    th = 0.0028
    rings = []
    for side in (-1, 1):
        for rr in (0.0, th):
            ring = [bm.verts.new((cx + (rx + rr) * math.cos(a), side * half_w, cz + (rz + rr) * math.sin(a)))
                    for a in (math.tau * i / seg for i in range(seg))]
            rings.append(ring)
    inner_a, outer_a, inner_b, outer_b = rings
    for i in range(seg):
        j = (i + 1) % seg
        bm.faces.new((outer_a[i], outer_a[j], outer_b[j], outer_b[i]))
        bm.faces.new((inner_a[j], inner_a[i], inner_b[i], inner_b[j]))
        bm.faces.new((inner_a[i], inner_a[j], outer_a[j], outer_a[i]))
        bm.faces.new((outer_b[i], outer_b[j], inner_b[j], inner_b[i]))
    strap_faces = len(bm.faces)
    # case and dial on top
    res = bmesh.ops.create_cone(bm, cap_ends=True, segments=40, radius1=0.0195, radius2=0.018, depth=0.009)
    bmesh.ops.translate(bm, vec=(cx, 0, cz + rz + th + 0.004), verts=res["verts"])
    bm.to_mesh(me)
    bm.free()
    steel = materials.simple("POV Watch Steel", (0.75, 0.75, 0.76), rough=0.22, metal=1.0)
    strap = materials.simple("POV Watch Strap", (0.12, 0.06, 0.03), rough=0.55)
    dial = materials.simple("POV Watch Dial", (0.02, 0.03, 0.06), rough=0.15)
    for m in (strap, steel, dial):
        me.materials.append(m)
    top = cz + rz + th + 0.0085
    _assign(me, lambda p: 0 if p.index < strap_faces else (2 if p.center.z > top - 0.0002 and p.normal.z > 0.9
                                                             else 1))
    for p in me.polygons:
        p.use_smooth = p.index < strap_faces
    return _new_object("POV Watch", me, coll)


BUILDERS = {
    "CIGARETTE": _cigarette,
    "PHONE": _phone,
    "CUP": _cup,
    "BOTTLE": _bottle,
    "FLASHLIGHT": _flashlight,
    "SMOKE": _smoke,
}


def ensure(cam, item_id):
    """The rig's prop object for ``item_id``, built on first use."""
    rig_ob = cam.stride.arms
    for ob in owned(cam):
        if ob.get("stride_item") == item_id:
            return ob
    coll = rig_ob.users_collection[0]
    ob = BUILDERS[item_id](coll)
    ob["stride_item"] = item_id
    if item_id != "SMOKE":
        # hand props are keyed in the arms' space; smoke drifts off in world space
        ob.parent = rig_ob
        ob.matrix_parent_inverse = Matrix.Identity(4)
    return ob


def owned(cam):
    rig_ob = cam.stride.arms
    if rig_ob is None:
        return []
    coll = rig_ob.users_collection[0]
    return [ob for ob in coll.objects if ob.get("stride_item")]


def add_watch(cam):
    rig_ob = cam.stride.arms
    for ob in rig_ob.children:
        if ob.get("stride_watch"):
            return ob
    bone = rig_ob.data.bones["forearm_twist.L"]
    ob = _watch(rig_ob.users_collection[0], *_wrist_size(rig_ob, bone, bone.length - 0.034))
    ob["stride_watch"] = True
    ob.parent = rig_ob
    ob.parent_type = "BONE"
    ob.parent_bone = bone.name
    # 3 cm up the forearm from the wrist, face on the back of the wrist
    local = Matrix.Translation((0.0, bone.length - 0.034, 0.0))
    ob.matrix_parent_inverse = Matrix.Identity(4)
    ob.matrix_basis = Matrix.Translation((0.0, -bone.length, 0.0)) @ local
    return ob


def _wrist_size(rig_ob, bone, at, clearance=0.0008):
    """Half-sizes and centre (rx, rz, cx, cz) of the left arm's skin ``at`` metres along ``bone``,
    in the bone's axes, so the strap sits on the wrist instead of floating round it."""
    arm = next((c for c in rig_ob.children if c.type == "MESH" and c.name.startswith("POV Arm")
                and c.name.endswith(".L")), None)
    if arm is None or "rest" not in arm.data.attributes:
        return ()
    rest = np.empty(len(arm.data.vertices) * 3, np.float32)
    arm.data.attributes["rest"].data.foreach_get("vector", rest)
    m = np.array(bone.matrix_local.inverted())
    p = rest.reshape(-1, 3) @ m[:3, :3].T + m[:3, 3]
    ring = p[np.abs(p[:, 1] - at) < 0.004]
    if len(ring) < 8:
        return ()
    lo, hi = ring.min(axis=0), ring.max(axis=0)
    c = (lo + hi) / 2
    return ((hi[0] - lo[0]) / 2 + clearance, (hi[2] - lo[2]) / 2 + clearance, c[0], c[2])


def remove_watch(cam):
    rig_ob = cam.stride.arms
    for ob in list(rig_ob.children if rig_ob else ()):
        if ob.get("stride_watch"):
            me = ob.data
            bpy.data.objects.remove(ob, do_unlink=True)
            if me.users == 0:
                bpy.data.meshes.remove(me)


def grip_matrix(grip, poses, side, lengths):
    """Prop matrix (armature space) for a grip on the posed hand."""
    s = "." + side
    pts = []
    for bone, t in grip.points:
        m = poses[bone + s]
        head = m.translation
        y = Vector(m.col[1][:3])
        pts.append(head + y * t * lengths[bone + s])
    p = sum(pts, Vector()) / len(pts)
    m = poses[grip.frame + s].to_3x3()
    sx = 1.0 if side == "R" else -1.0

    def local(v):
        return m @ Vector((v[0] * sx, v[1], v[2]))
    y = local(grip.y).normalized()
    z = local(grip.z)
    z = (z - y * z.dot(y)).normalized()
    x = y.cross(z)
    rot = Matrix((x, y, z)).transposed().to_4x4()
    return Matrix.Translation(p + local(grip.offset)) @ rot

