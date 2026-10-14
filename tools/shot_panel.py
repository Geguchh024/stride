# SPDX-License-Identifier: GPL-3.0-or-later
"""Screenshot the POV sidebar and the walk overlay (needs Blender's UI).

    blender --factory-startup --enable-event-simulate --window-geometry 0 0 1920 1080 \
        --python tools/shot_panel.py -- OUT.png

Builds a small walk with stairs, a waypoint, hands and an action, frames
it from above in solid shading, opens Sidebar > POV, writes OUT.png and quits.
"""

import math
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import bpy  # noqa: E402
from mathutils import Vector  # noqa: E402

import stride  # noqa: E402

OUT = os.path.abspath(sys.argv[sys.argv.index("--") + 1])
stride.register()
from stride import arms, props, rig, solve  # noqa: E402

bpy.context.preferences.view.ui_scale = 1.2
bpy.context.preferences.view.show_splash = False
for o in list(bpy.data.objects):
    bpy.data.objects.remove(o)
sc = bpy.context.scene
cam = rig.create(bpy.context, Vector((0, 0, 0)), math.pi / 2, length=9.0)
rig.add_stairs(cam, Vector((0.0, 3.0, 0.0)), 0.0, steps=6, rise=0.16, run=0.3, width=1.6, before=0.6, after=2.5)
end = cam.stride.points[-1].obj
end.location = (1.2, 9.0, 0.96)
rig.add_waypoint(cam, Vector((-0.6, 2.2, 0.0)))
cam.stride.points[1].wait = 1.0
arms.add(cam)
props._suspend["on"] = True
it = cam.stride.clips.add()
it.clip = "SMOKE"
it.frame = 30
it.duration = 9.0
lk = cam.stride.looks.add()
lk.kind = "LEFT"
lk.frame = 120
props._suspend["on"] = False
bpy.context.view_layer.update()
solve.update(cam)
sc.frame_set(70)
bpy.ops.object.select_all(action="DESELECT")
end.select_set(True)
bpy.context.view_layer.objects.active = end


def view3d():
    win = bpy.context.window_manager.windows[0]
    area = max((a for a in win.screen.areas if a.type == "VIEW_3D"), key=lambda a: a.width * a.height)
    return win, area


def setup():
    win, area = view3d()
    space = area.spaces.active
    space.show_region_ui = True
    space.shading.type = "SOLID"
    r3d = space.region_3d
    r3d.view_perspective = "PERSP"
    r3d.view_location = Vector((0.3, 4.5, 0.6))
    r3d.view_distance = 11.0
    from mathutils import Euler
    r3d.view_rotation = Euler((math.radians(55), 0, math.radians(-35))).to_quaternion()
    return None


tries = [0]


def pick_tab():
    win, area = view3d()
    space = area.spaces.active
    ui = next(r for r in area.regions if r.type == "UI")
    if ui.active_panel_category == "POV" or tries[0] > 40:
        return None
    tries[0] += 1
    x = ui.x + ui.width - int(14 * bpy.context.preferences.view.ui_scale)
    y = ui.y + ui.height - 40 - tries[0] * 12
    win.event_simulate(type="MOUSEMOVE", value="NOTHING", x=x, y=y)
    win.event_simulate(type="LEFTMOUSE", value="PRESS", x=x, y=y)
    win.event_simulate(type="LEFTMOUSE", value="RELEASE", x=x, y=y)
    space.show_region_ui = True
    return 0.2


def shoot():
    win, area = view3d()
    print("tab:", next(r for r in area.regions if r.type == "UI").active_panel_category)
    with bpy.context.temp_override(window=win):
        bpy.ops.screen.screenshot(filepath=OUT)
    print("wrote", OUT)
    bpy.ops.wm.quit_blender()


bpy.app.timers.register(setup, first_interval=2.0)
bpy.app.timers.register(pick_tab, first_interval=4.0)
bpy.app.timers.register(shoot, first_interval=16.0)
