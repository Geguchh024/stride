# SPDX-License-Identifier: GPL-3.0-or-later
"""Procedural materials for the arms: skin (nails included), sleeves and the props.

The skin is a painted texture (UVs) tinted to the chosen tone. Procedural
textures read the ``rest`` attribute (the undeformed position in metres), so
pores and weave stay put on the skin while the arm moves.
"""

import os

import bpy

SKIN_TONES = [
    # id, label, linear albedo
    ("PALE", "Pale", (0.80, 0.57, 0.46)),
    ("FAIR", "Fair", (0.71, 0.47, 0.36)),
    ("LIGHT", "Light", (0.60, 0.38, 0.27)),
    ("MEDIUM", "Medium", (0.46, 0.27, 0.17)),
    ("TAN", "Tan", (0.33, 0.18, 0.105)),
    ("BROWN", "Brown", (0.19, 0.098, 0.056)),
    ("DARK", "Dark", (0.090, 0.047, 0.029)),
]
TONE_BY_ID = {t[0]: t[2] for t in SKIN_TONES}
# average linear colour of the skin texture, which the tones are measured against
TEXTURE_ALBEDO = (0.56, 0.32, 0.22)
SKIN_TEXTURE = os.path.join(os.path.dirname(__file__), "data", "arm_skin.jpg")

SLEEVES = [
    # id, label, description, colour (linear), sheen, roughness, kind
    ("JACKET", "Field Jacket", "Olive cotton canvas jacket", (0.050, 0.055, 0.032), 0.5, 0.85, "canvas"),
    ("HOODIE", "Hoodie", "Grey cotton hoodie with ribbed cuffs", (0.13, 0.13, 0.14), 1.0, 0.95, "jersey"),
    ("DENIM", "Denim Jacket", "Blue denim", (0.035, 0.065, 0.13), 0.4, 0.8, "twill"),
    ("LEATHER", "Leather Jacket", "Black leather", (0.018, 0.016, 0.015), 0.0, 0.38, "leather"),
    ("FLANNEL", "Flannel Shirt", "Red and black plaid flannel", (0.20, 0.025, 0.02), 0.8, 0.9, "plaid"),
    ("SWEATER", "Knit Sweater", "Chunky cream knit", (0.55, 0.48, 0.36), 1.0, 0.95, "knit"),
    ("SUIT", "Suit", "Charcoal wool suit with a white shirt cuff", (0.022, 0.023, 0.026), 0.6, 0.75, "wool"),
    ("TSHIRT", "T-Shirt", "Short sleeves, bare forearms", (0.02, 0.02, 0.022), 0.6, 0.9, "jersey"),
    ("NONE", "Bare Arms", "No sleeves", (0, 0, 0), 0, 0, "none"),
]
SLEEVE_BY_ID = {s[0]: s for s in SLEEVES}


class Nodes:
    """Tiny node-tree builder: n.new(type, x, y, **inputs), n.link(a, b)."""

    def __init__(self, mat):
        mat.use_nodes = True
        self.nt = mat.node_tree
        self.nt.nodes.clear()

    def new(self, kind, x=0, y=0, **inputs):
        node = self.nt.nodes.new(kind)
        node.location = (x, y)
        for k, v in inputs.items():
            if k.startswith("_"):
                setattr(node, k[1:], v)
            else:
                node.inputs[k.replace("_", " ")].default_value = v
        return node

    def link(self, out, inp):
        self.nt.links.new(out, inp)


def _rest(n, x=-1400, y=0):
    a = n.new("ShaderNodeAttribute", x, y)
    a.attribute_name = "rest"
    return a.outputs["Vector"]


def _attr(n, name, x, y):
    a = n.new("ShaderNodeAttribute", x, y)
    a.attribute_name = name
    return a.outputs["Fac"]


def _bump_chain(n, layers, x=-300, y=-500):
    """Stack bump nodes: layers of (height socket, strength, distance)."""
    normal = None
    for i, (height, strength, dist) in enumerate(layers):
        b = n.new("ShaderNodeBump", x + 160 * i, y, Strength=strength, Distance=dist)
        n.link(height, b.inputs["Height"])
        if normal is not None:
            n.link(normal, b.inputs["Normal"])
        normal = b.outputs["Normal"]
    return normal


def skin_image():
    """The arm's painted skin, packed into the file so a saved scene doesn't need the add-on."""
    img = bpy.data.images.get("Stride Skin")
    if img is None:
        img = bpy.data.images.load(SKIN_TEXTURE)
        img.name = "Stride Skin"
        img.pack()
    return img


def skin(name, tone, gloss=0.5):
    mat = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    n = Nodes(mat)
    out = n.new("ShaderNodeOutputMaterial", 600, 0)
    bsdf = n.new("ShaderNodeBsdfPrincipled", 250, 0)
    bsdf.subsurface_method = "RANDOM_WALK_SKIN"
    n.link(bsdf.outputs[0], out.inputs["Surface"])
    rest = _rest(n)

    # the painted skin (veins, creases, nails), tinted from its own colour to the chosen tone
    tex = n.new("ShaderNodeTexImage", -1150, 520)
    tex.image = skin_image()
    tex.interpolation = "Cubic"
    tint = n.new("ShaderNodeRGB", -1150, 250)
    tint.outputs[0].default_value = (*(t / a for t, a in zip(tone, TEXTURE_ALBEDO)), 1.0)
    var = n.new("ShaderNodeMix", -900, 400, Factor=1.0)
    var.data_type = "RGBA"
    var.blend_type = "MULTIPLY"
    n.link(tex.outputs["Color"], var.inputs[6])
    n.link(tint.outputs[0], var.inputs[7])
    # broad noise still varies roughness
    blot = n.new("ShaderNodeTexNoise", -1150, 0, Scale=55.0, Detail=4.0, Roughness=0.55)
    n.link(rest, blot.inputs["Vector"])
    flush_col = n.new("ShaderNodeMix", -650, 400)
    flush_col.data_type = "RGBA"
    flush_col.blend_type = "MULTIPLY"
    flush_col.inputs[7].default_value = (1.0, 0.84, 0.82, 1.0)
    n.link(_attr(n, "flush", -900, 150), flush_col.inputs["Factor"])
    n.link(var.outputs[2], flush_col.inputs[6])
    # palms and soles are lighter, most visibly on dark skin
    palm_col = n.new("ShaderNodeMix", -400, 400)
    palm_col.data_type = "RGBA"
    lum = 0.2126 * tone[0] + 0.7152 * tone[1] + 0.0722 * tone[2]
    palm_strength = max(0.0, min(0.8, (0.35 - lum) * 2.4))
    palm_fac = n.new("ShaderNodeMath", -650, 150, _operation="MULTIPLY")
    palm_fac.inputs[1].default_value = palm_strength
    n.link(_attr(n, "palm", -900, 0), palm_fac.inputs[0])
    n.link(palm_fac.outputs[0], palm_col.inputs["Factor"])
    n.link(flush_col.outputs[2], palm_col.inputs[6])
    palm_col.inputs[7].default_value = (0.42, 0.24, 0.17, 1.0)
    # nails: the nail bed shows pink through the plate; glossier, a touch of clear coat
    nail_mask = _attr(n, "nail", -650, 650)
    nail_fac = n.new("ShaderNodeMath", -400, 650, _operation="MULTIPLY")
    nail_fac.inputs[1].default_value = 0.35
    n.link(nail_mask, nail_fac.inputs[0])
    nail_col = n.new("ShaderNodeMix", -200, 500)
    nail_col.data_type = "RGBA"
    n.link(nail_fac.outputs[0], nail_col.inputs["Factor"])
    n.link(palm_col.outputs[2], nail_col.inputs[6])
    bed = tuple(min(1.0, c * 0.92 + 0.10) for c in tone)
    nail_col.inputs[7].default_value = (bed[0], bed[1] * 0.80, bed[2] * 0.82, 1.0)
    n.link(nail_col.outputs[2], bsdf.inputs["Base Color"])
    n.link(nail_mask, bsdf.inputs["Coat Weight"])
    bsdf.inputs["Coat Roughness"].default_value = 0.2

    bsdf.inputs["Subsurface Weight"].default_value = 1.0
    bsdf.inputs["Subsurface Radius"].default_value = (1.0, 0.36, 0.20)
    bsdf.inputs["Subsurface Scale"].default_value = 0.0022
    bsdf.inputs["Subsurface IOR"].default_value = 1.4
    bsdf.inputs["Specular IOR Level"].default_value = 0.38
    bsdf.inputs["IOR"].default_value = 1.4

    # roughness: oilier on the knuckles and fingertips, drier elsewhere
    rough = n.new("ShaderNodeMapRange", -400, 0, From_Min=0.0, From_Max=1.0, To_Min=0.66 - 0.1 * gloss,
                  To_Max=0.50 - 0.1 * gloss)
    n.link(blot.outputs["Fac"], rough.inputs["Value"])
    rough_nail = n.new("ShaderNodeMix", -200, 0)
    rough_nail.data_type = "FLOAT"
    n.link(nail_mask, rough_nail.inputs["Factor"])
    n.link(rough.outputs[0], rough_nail.inputs[2])
    rough_nail.inputs[3].default_value = 0.3
    n.link(rough_nail.outputs[0], bsdf.inputs["Roughness"])

    # pores, fine skin cells and wrinkles across the joints
    pores = n.new("ShaderNodeTexNoise", -900, -300, Scale=2200.0, Detail=1.0, Roughness=0.5)
    n.link(rest, pores.inputs["Vector"])
    cells = n.new("ShaderNodeTexVoronoi", -900, -550, Scale=650.0)
    cells.feature = "DISTANCE_TO_EDGE"
    n.link(rest, cells.inputs["Vector"])
    # fine lines across the knuckles (fingers point along +Y in the rest pose)
    lines = n.new("ShaderNodeTexWave", -900, -800, Scale=420.0, Distortion=6.0, Detail=3.0,
                  Detail_Scale=1.5)
    lines.wave_type = "BANDS"
    lines.bands_direction = "Y"
    n.link(rest, lines.inputs["Vector"])
    kn = n.new("ShaderNodeMath", -700, -800, _operation="MULTIPLY")
    n.link(lines.outputs["Fac"], kn.inputs[0])
    n.link(_attr(n, "knuckle", -900, -1000), kn.inputs[1])
    normal = _bump_chain(n, [(pores.outputs["Fac"], 0.05, 0.00015),
                             (cells.outputs["Distance"], 0.06, 0.0002),
                             (kn.outputs[0], 0.35, 0.0004)], x=-500, y=-450)
    n.link(normal, bsdf.inputs["Normal"])
    return mat


def fabric(name, sleeve_id):
    sid, _label, _desc, color, sheen, rough, kind = SLEEVE_BY_ID[sleeve_id]
    mat = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    n = Nodes(mat)
    out = n.new("ShaderNodeOutputMaterial", 600, 0)
    bsdf = n.new("ShaderNodeBsdfPrincipled", 300, 0)
    n.link(bsdf.outputs[0], out.inputs["Surface"])
    rest = _rest(n)
    bsdf.inputs["Roughness"].default_value = rough
    bsdf.inputs["Sheen Weight"].default_value = sheen
    bsdf.inputs["Sheen Roughness"].default_value = 0.5
    bsdf.inputs["Sheen Tint"].default_value = (1.0, 1.0, 1.0, 1.0)
    bsdf.inputs["Specular IOR Level"].default_value = 0.35 if kind != "leather" else 0.6

    # colour: slight mottling everywhere; plaid for flannel; a white shirt cuff for the suit
    mottle = n.new("ShaderNodeTexNoise", -1150, 350, Scale=40.0, Detail=6.0)
    n.link(rest, mottle.inputs["Vector"])
    base = n.new("ShaderNodeRGB", -1150, 600)
    base.outputs[0].default_value = (*color, 1.0)
    mix = n.new("ShaderNodeMix", -850, 450, Factor=0.10)
    mix.data_type = "RGBA"
    mix.blend_type = "OVERLAY"
    n.link(base.outputs[0], mix.inputs[6])
    n.link(mottle.outputs["Color"], mix.inputs[7])
    col_out = mix.outputs[2]
    if kind == "plaid":
        stripes = []
        for i, axis in enumerate(("X", "Z")):
            w = n.new("ShaderNodeTexWave", -950, 200 - 200 * i, Scale=28.0, Distortion=0.0)
            w.wave_type = "BANDS"
            w.bands_direction = axis
            n.link(rest, w.inputs["Vector"])
            band = n.new("ShaderNodeMath", -850, 200 - 200 * i, _operation="GREATER_THAN")
            band.inputs[1].default_value = 0.62
            n.link(w.outputs["Fac"], band.inputs[0])
            stripes.append(band.outputs[0])
        both = n.new("ShaderNodeMath", -750, 150, _operation="MULTIPLY")
        n.link(stripes[0], both.inputs[0])
        n.link(stripes[1], both.inputs[1])
        either = n.new("ShaderNodeMath", -750, 0, _operation="MAXIMUM")
        n.link(stripes[0], either.inputs[0])
        n.link(stripes[1], either.inputs[1])
        dark = n.new("ShaderNodeMix", -550, 300)
        dark.data_type = "RGBA"
        n.link(either.outputs[0], dark.inputs["Factor"])
        n.link(col_out, dark.inputs[6])
        dark.inputs[7].default_value = (0.012, 0.010, 0.010, 1.0)
        darker = n.new("ShaderNodeMix", -400, 300)
        darker.data_type = "RGBA"
        n.link(both.outputs[0], darker.inputs["Factor"])
        n.link(dark.outputs[2], darker.inputs[6])
        darker.inputs[7].default_value = (0.004, 0.004, 0.004, 1.0)
        col_out = darker.outputs[2]
    if kind == "wool":
        shirt = n.new("ShaderNodeMix", -400, 300)
        shirt.data_type = "RGBA"
        n.link(_attr(n, "shirt", -650, 250), shirt.inputs["Factor"])
        n.link(col_out, shirt.inputs[6])
        shirt.inputs[7].default_value = (0.78, 0.79, 0.80, 1.0)
        col_out = shirt.outputs[2]
    # hem: a slightly darker stitched band at the cuff
    hem = n.new("ShaderNodeMix", -250, 300)
    hem.data_type = "RGBA"
    hem.blend_type = "MULTIPLY"
    hem_f = n.new("ShaderNodeMath", -400, 100, _operation="MULTIPLY")
    hem_f.inputs[1].default_value = 0.35 if kind != "wool" else 0.0
    n.link(_attr(n, "hem", -650, 100), hem_f.inputs[0])
    n.link(hem_f.outputs[0], hem.inputs["Factor"])
    n.link(col_out, hem.inputs[6])
    hem.inputs[7].default_value = (0.55, 0.55, 0.55, 1.0)
    n.link(hem.outputs[2], bsdf.inputs["Base Color"])

    # weave / knit / grain
    layers = []
    if kind in ("canvas", "twill", "jersey", "wool", "plaid"):
        scale = {"canvas": 1500.0, "twill": 1300.0, "jersey": 2400.0, "wool": 2000.0, "plaid": 1300.0}[kind]
        for i, axis in enumerate(("X", "Z")):
            w = n.new("ShaderNodeTexWave", -950, -300 - 180 * i, Scale=scale, Distortion=0.0, Detail=0.0)
            w.wave_type = "BANDS"
            w.bands_direction = axis if kind != "twill" else "DIAGONAL"
            n.link(rest, w.inputs["Vector"])
            layers.append((w.outputs["Fac"], 0.06, 0.0001))
    elif kind == "knit":
        v = n.new("ShaderNodeTexVoronoi", -950, -300, Scale=180.0)
        v.feature = "DISTANCE_TO_EDGE"
        n.link(rest, v.inputs["Vector"])
        w = n.new("ShaderNodeTexWave", -950, -500, Scale=140.0, Distortion=3.0)
        w.wave_type = "BANDS"
        w.bands_direction = "Y"
        n.link(rest, w.inputs["Vector"])
        layers += [(v.outputs["Distance"], 0.5, 0.0015), (w.outputs["Fac"], 0.3, 0.0015)]
    elif kind == "leather":
        g = n.new("ShaderNodeTexVoronoi", -950, -300, Scale=900.0)
        g.feature = "DISTANCE_TO_EDGE"
        n.link(rest, g.inputs["Vector"])
        cr = n.new("ShaderNodeTexNoise", -950, -500, Scale=120.0, Detail=8.0)
        n.link(rest, cr.inputs["Vector"])
        layers += [(g.outputs["Distance"], 0.15, 0.0003), (cr.outputs["Fac"], 0.25, 0.0008)]
    wrinkle = n.new("ShaderNodeTexNoise", -950, -750, Scale=35.0, Detail=2.0)
    n.link(rest, wrinkle.inputs["Vector"])
    layers.append((wrinkle.outputs["Fac"], 0.12, 0.002))
    normal = _bump_chain(n, layers, x=-600, y=-600)
    n.link(normal, bsdf.inputs["Normal"])
    return mat


def simple(name, color, rough=0.5, metal=0.0, emit=None, strength=0.0, alpha=1.0, transmission=0.0):
    mat = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    n = Nodes(mat)
    out = n.new("ShaderNodeOutputMaterial", 300, 0)
    bsdf = n.new("ShaderNodeBsdfPrincipled", 0, 0)
    n.link(bsdf.outputs[0], out.inputs["Surface"])
    bsdf.inputs["Base Color"].default_value = (*color, 1.0)
    bsdf.inputs["Roughness"].default_value = rough
    bsdf.inputs["Metallic"].default_value = metal
    bsdf.inputs["Transmission Weight"].default_value = transmission
    if emit is not None:
        bsdf.inputs["Emission Color"].default_value = (*emit, 1.0)
        bsdf.inputs["Emission Strength"].default_value = strength
    if alpha < 1.0:
        bsdf.inputs["Alpha"].default_value = alpha
    return mat
