# SPDX-License-Identifier: GPL-3.0-or-later
"""Render the README images from the meadow walk (tools/showcase_scene.py).

    blender -b --factory-startup --python tools/render_previews.py -- [hero] [actions] [ACTION_ID...] [--samples N]

hero: a sheet of frames along one walk with a cigarette. actions: one POV
frame per action. Writes docs/images/. Needs ../verdant and ../open-sky.
"""

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)

import bpy  # noqa: E402
import numpy as np  # noqa: E402

import showcase_scene  # noqa: E402

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
SAMPLES = int(argv[argv.index("--samples") + 1]) if "--samples" in argv else 96
SCALE = float(argv[argv.index("--scale") + 1]) if "--scale" in argv else 1.0
jobs = [a for a in argv if a in ("hero", "actions")] or ["hero", "actions"]
only = [a.upper() for a in argv if a not in ("hero", "actions") and not a.startswith("--")
        and not a.replace(".", "").isdigit()]
OUT = os.path.join(ROOT, "docs", "images")


def render(sc, path, w=1280, h=720):
    sc.render.resolution_x, sc.render.resolution_y = int(w * SCALE), int(h * SCALE)
    sc.render.resolution_percentage = 100
    os.makedirs(os.path.dirname(path), exist_ok=True)
    sc.render.filepath = path
    bpy.ops.render.render(write_still=True)
    print("wrote", path)
    return path


def sheet(paths, out, cols):
    imgs = []
    for p in paths:
        im = bpy.data.images.load(p, check_existing=False)
        w, h = im.size
        imgs.append(np.array(im.pixels[:], np.float32).reshape(h, w, 4))
        bpy.data.images.remove(im)
    h, w = imgs[0].shape[:2]
    gap = max(2, w // 160)
    rows = (len(imgs) + cols - 1) // cols
    canvas = np.ones((rows * h + (rows - 1) * gap, cols * w + (cols - 1) * gap, 4), np.float32)
    for i, im in enumerate(imgs):
        r, c = divmod(i, cols)
        y0 = (rows - 1 - r) * (h + gap)
        x0 = c * (w + gap)
        canvas[y0:y0 + h, x0:x0 + w] = im
    img = bpy.data.images.new("sheet", canvas.shape[1], canvas.shape[0], alpha=True)
    img.pixels.foreach_set(canvas.ravel())
    img.filepath_raw = out
    img.file_format = "PNG"
    img.save()
    print("wrote", out)


def hero():
    sc, cam = showcase_scene.build(samples=SAMPLES, actions=(("SMOKE", 30, 9.0),))
    frames = [24, 62, 96, 150]
    paths = []
    for f in frames:
        sc.frame_set(f)
        paths.append(render(sc, os.path.join(OUT, "frames", f"walk_{f:04d}.png"), 960, 540))
    sheet(paths, os.path.join(OUT, "walk.png"), 2)


def actions():
    picks = [("PHONE", 0.45, "HOODIE", "MEDIUM"), ("COFFEE", 0.75, "DENIM", "FAIR"),
             ("FLASHLIGHT", 0.5, "LEATHER", "BROWN"), ("WAVE", 0.35, "FLANNEL", "LIGHT"),
             ("LOOK_HANDS", 0.4, "SWEATER", "TAN"), ("SMOKE", 0.2, "JACKET", "LIGHT")]
    paths = []
    for clip_id, frac, sleeve, tone in picks:
        if only and clip_id not in only:
            continue
        from stride import clips
        c = clips.CLIP_BY_ID[clip_id]
        sc, cam = showcase_scene.build(samples=SAMPLES, actions=((clip_id, 20, c.default_duration),),
                                       sleeve=sleeve, tone=tone)
        sc.frame_set(20 + int(c.default_duration * frac * 24))
        paths.append(render(sc, os.path.join(OUT, "frames", f"action_{clip_id.lower()}.png"), 960, 540))
    if not only:
        sheet(paths, os.path.join(OUT, "actions.png"), 3)


if "hero" in jobs:
    hero()
if "actions" in jobs:
    actions()
