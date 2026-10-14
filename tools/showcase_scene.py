# SPDX-License-Identifier: GPL-3.0-or-later
"""A meadow walk for README images and previews.

Built with the sibling add-ons Verdant (meadow, path, trees) and Open Sky
(sky and sun) from ../verdant and ../open-sky. Import and call build();
it returns (scene, rig camera).
"""

import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
PROJECTS = os.path.dirname(ROOT)
for repo in ("verdant", "open-sky"):
    sys.path.insert(0, os.path.join(PROJECTS, repo))
sys.path.insert(0, ROOT)
sys.path.insert(0, HERE)

import bpy  # noqa: E402
from mathutils import Vector  # noqa: E402

import open_sky  # noqa: E402
import stride  # noqa: E402
import verdant  # noqa: E402

verdant.register()
open_sky.register()
stride.register()
from open_sky import rig as sky_rig  # noqa: E402
from verdant import catalog, patches, scatter  # noqa: E402

import render_gpu  # noqa: E402
from stride import arms, props, rig, solve  # noqa: E402


def _plant(sp_id, variant, loc, rot=0.0, scale=1.0):
    coll = catalog.variant_collection(sp_id, variant)
    catalog.species_collection(sp_id)
    o = bpy.data.objects.new(coll.name, None)
    o.instance_type = "COLLECTION"
    o.instance_collection = coll
    o.location = loc
    o.rotation_euler.z = rot
    o.scale = (scale,) * 3
    bpy.context.scene.collection.objects.link(o)


def build(samples=96, sun_elevation=11.0, sun_azimuth=105.0, actions=(("SMOKE", 20, 9.0),), sleeve="JACKET",
          tone="LIGHT", style="WALK", length=14.0):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    sc = bpy.context.scene
    sc.render.engine = "CYCLES"
    render_gpu.enable(sc)
    sc.cycles.samples = samples
    sc.cycles.use_denoising = True
    sc.cycles.max_bounces = 6
    sc.cycles.transparent_max_bounces = 8
    sc.view_settings.view_transform = "AgX"
    sc.view_settings.look = "AgX - Medium High Contrast"
    sc.view_settings.exposure = 0.2
    sc.render.fps = 24
    world = sky_rig.create(sc)
    node = sky_rig.sky_node(world)
    for k, v in {"Haze Density": 0.45, "Cloud Coverage": 0.15, "Ground": 0.0}.items():
        if k in node.inputs:
            node.inputs[k].default_value = v
    sky_rig.set_sun_angles(sky_rig.sun_object(world), math.radians(sun_elevation), math.radians(sun_azimuth))

    ctx = bpy.context
    near = patches.add_patch(ctx, "MEADOW", size=36.0, seed=4, location=(0, 14, 0))
    far = patches.add_patch(ctx, "MEADOW", size=140.0, seed=5, location=(0, 100, -0.3))
    for mod in scatter.layers(far):
        name = scatter.get(mod, "Collection").name
        if name == "VD Lawn Grass":
            scatter.set_value(mod, "Density", 25.0)
        elif name == "VD Meadow Grass":
            scatter.set_value(mod, "Density", 18.0)
    for x, y, v, s in ((-6.5, 22, 0, 1.0), (7.5, 30, 2, 0.95), (-12, 38, 1, 1.05)):
        _plant("OAK", v, (x, y, -0.05), x * 0.3, s)
    for x, y, v in ((3.2, 11, 0), (4.6, 15.5, 1), (-3.4, 18, 2), (5.5, 24, 0), (-4.8, 9.5, 1)):
        _plant("BIRCH", v, (x, y, -0.05), x * 0.7, 0.95)
    for i in range(26):
        x = -70 + i * 5.5 + (i * 7919 % 11) * 0.4
        y = 120 + (i * 104729 % 17)
        _plant("SPRUCE" if i % 3 else "PINE", i % 3, (x, y, -0.3), i * 1.3, 0.85 + (i % 5) * 0.08)

    bpy.context.view_layer.update()
    for o in list(ctx.selected_objects):
        o.select_set(False)
    cam = rig.create(ctx, Vector((0.0, 0.0, 0.0)), math.pi / 2, length=length, floor_from=near)
    dg = ctx.evaluated_depsgraph_get()
    from stride import floor as floor_mod
    ground = floor_mod.Ground([near], dg)
    for it in cam.stride.points:
        p = it.obj.location
        z = ground.height(p.x, p.y, 5.0, up=0.0, down=10.0)
        if z is not None:
            it.obj.location.z = z
    rig.add_waypoint(cam, Vector((0.5, length * 0.5, 0.0)))
    wp = cam.stride.points[1].obj
    wp.location.z = ground.height(wp.location.x, wp.location.y, 5.0, up=0.0, down=10.0) or 0.0
    cam.stride.style = style
    cam.data.clip_end = 3000.0
    arms.add(cam, "AVERAGE", tone, sleeve, True)
    props._suspend["on"] = True
    try:
        cam.stride.skin_tone = tone
        cam.stride.sleeve = sleeve
        for clip_id, frame, duration in actions:
            it = cam.stride.clips.add()
            it.clip = clip_id
            it.frame = frame
            it.duration = duration
    finally:
        props._suspend["on"] = False
    bpy.context.view_layer.update()
    solve.update(cam)
    sc.camera = cam
    sc.render.use_motion_blur = True
    sc.render.motion_blur_shutter = 0.35
    return sc, cam
