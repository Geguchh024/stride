# Contributing

Everything you need to work on the add-on.

## Project layout

```
stride/                    the add-on (this folder is what gets zipped)
  __init__.py              registration
  blender_manifest.toml    extension manifest
  mathkit.py               easing, noise, splines, damping (numpy, no bpy)
  walk.py                  the walk: path, floor heights, footsteps, speed, timing (no bpy)
  motion.py                body and head over time, look moves (mathutils)
  floor.py                 floor meshes (plane, stairs), floor height lookups, drop onto scene
  rig.py                   the rig's objects: camera, boxes, floors
  solve.py                 rig settings -> plan -> frames -> keys
  bake.py                  writing per-frame keys (slotted actions)
  anatomy.py               arm and hand proportions: skeleton and skin shapes (numpy)
  sdf.py                   signed distance shapes and the surface-nets mesher (numpy)
  handmesh.py              meshing arms and sleeves, skin weights, shading masks, .npz cache
  arms.py                  armature, skinned meshes, sleeves in Blender
  materials.py             skin, nail, fabric and prop materials
  handposes.py             finger poses
  pose.py                  forward kinematics and two-bone arm IK (matches Blender's bone maths)
  clips.py                 the hand action library
  items.py                 props and grips
  animate.py               hands over time: actions, rest swing, sway, props, smoke; baking
  overlay.py               viewport drawing
  handlers.py              live updates
  props.py / ops.py / ui.py   settings, operators, sidebar panels
  data/                    arm source mesh + skin texture (tools/import_hands.py),
                           prebuilt arm and sleeve meshes (tools/build_meshes.py)
tools/import_hands.py      turns the rigged-arms glTF into stride/data/arm_source.npz + arm_skin.jpg
tools/build_meshes.py      prebuilds the meshes into stride/data
tools/showcase_scene.py    the meadow walk for README images, built with ../verdant and ../open-sky
tools/render_previews.py   renders docs/images (walk.png, actions.png)
tools/shot_panel.py        screenshots the sidebar and overlay (needs Blender's UI)
tools/render_gpu.py        turns on the GPU for tool renders
tests/run_tests.py         headless test suite
```

## Running from source

Add the repo root to *Preferences → File Paths → Script Directories*, or
symlink `stride` into your user extensions folder, then enable the add-on.

## Tests

```
blender -b --factory-startup --python tests/run_tests.py
```

Covers the walk maths (timing, waits, waypoints, floors, footsteps), look
moves, baking and that keys reproduce the solve, stairs, live floor edits
and box moves, the operators, walking styles, the arm mesh and weights, IK
against Blender's own bone evaluation, every action baking, smoking (ember,
smoke, filter at the lips), action time warping, and a saved file playing
back without the add-on.

## Images

```
blender -b --factory-startup --python tools/render_previews.py -- hero actions
blender -b --factory-startup --python tools/render_previews.py -- actions PHONE COFFEE
blender --factory-startup --enable-event-simulate --window-geometry 0 0 1920 1080 \
    --python tools/shot_panel.py -- docs/images/panel.png
```

## Meshes

```
blender -b --factory-startup --python tools/import_hands.py -- rigged_arms.glb   # only when the source mesh changes
python tools/build_meshes.py         # average build and all sleeves into stride/data
python tools/build_meshes.py --all   # also slim and strong
```

Bump `CACHE_VERSION` in `handmesh.py` whenever the anatomy, the mesher or the
masks change, then rebuild. Old caches are ignored.

## Things to know

- **No drivers.** In Blender 5.2, drivers reading custom properties don't
  evaluate. Everything is solved in Python and keyed per frame; prop
  channels (`ember`, `screen`, `density`) are keyed custom properties read by
  Attribute nodes.
- **Frames.** Body frame: origin at the eyes, +X right, +Y forward, +Z up.
  The head turns about `motion.NECK`. Hand-space: +Y to the fingers, +Z the
  back of the hand, +X the little-finger side (right hand).
- **Actions** are written for the right hand in `clips.py`. Keys give the
  wrist position, finger direction, palm direction and a finger pose;
  `prop_to` puts a prop's tip (`items.TIPS`) somewhere instead, e.g. the
  mouth. Check new actions from the POV camera and from close up.
- **Left side**: bones are mirrored across X, so a right-side local rotation
  becomes the left one by negating its Y and Z (`pose.mirror_quat`).
