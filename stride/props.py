# SPDX-License-Identifier: GPL-3.0-or-later
"""Settings: per rig (on its camera, ``camera.stride``) and per scene (``scene.stride``)."""

import bpy
from bpy.props import (BoolProperty, CollectionProperty, EnumProperty, FloatProperty, IntProperty,
                       PointerProperty)

from . import clips, materials, motion

# walking styles: values written into the rig's settings when picked
STYLES = [
    ("STROLL", "Stroll", "Slow and relaxed", dict(speed=1.0, step=0.62, bob=0.012, sway=0.012, roll=0.5,
                                                   shake=0.35, accel=0.7, crouch=0.0, look_ahead=2.0)),
    ("WALK", "Walk", "A normal walking pace", dict(speed=1.35, step=0.72, bob=0.016, sway=0.010, roll=0.6,
                                                  shake=0.35, accel=0.9, crouch=0.0, look_ahead=2.5)),
    ("BRISK", "Brisk", "In a hurry", dict(speed=1.75, step=0.80, bob=0.020, sway=0.008, roll=0.7,
                                         shake=0.4, accel=1.1, crouch=0.0, look_ahead=3.0)),
    ("JOG", "Jog", "An easy run", dict(speed=2.8, step=1.05, bob=0.032, sway=0.012, roll=1.0,
                                      shake=0.6, accel=1.6, crouch=0.0, look_ahead=4.0)),
    ("RUN", "Run", "Running fast", dict(speed=4.2, step=1.45, bob=0.042, sway=0.014, roll=1.4,
                                       shake=0.9, accel=2.4, crouch=0.0, look_ahead=6.0)),
    ("SNEAK", "Sneak", "Slow and crouched, careful steps", dict(speed=0.55, step=0.50, bob=0.010, sway=0.018,
                                                               roll=0.8, shake=0.3, accel=0.5, crouch=0.35,
                                                               look_ahead=2.0)),
    ("GIMBAL", "Gimbal", "Stabilised: a smooth glide with the walk barely felt",
     dict(speed=1.3, step=0.72, bob=0.003, sway=0.002, roll=0.0, shake=0.06, accel=0.6, crouch=0.0,
          look_ahead=3.0)),
    ("BODYCAM", "Bodycam", "Chest-mounted camera: shakier, and it turns with the body",
     dict(speed=1.4, step=0.72, bob=0.024, sway=0.016, roll=1.2, shake=1.0, accel=1.0, crouch=0.28,
          look_ahead=1.0)),
    ("WOBBLY", "Wobbly", "Tired or dizzy: big sway and roll", dict(speed=0.9, step=0.60, bob=0.020, sway=0.045,
                                                                  roll=2.5, shake=1.2, accel=0.6, crouch=0.0,
                                                                  look_ahead=2.0)),
]
STYLE_BY_ID = {s[0]: s[3] for s in STYLES}

_suspend = {"on": False}


def _dirty(self, context):
    if _suspend["on"]:
        return
    from . import handlers
    cam = self.id_data
    if isinstance(cam, bpy.types.Object):
        handlers.request(cam)


def _style_update(self, context):
    vals = STYLE_BY_ID.get(self.style)
    if not vals:
        return
    _suspend["on"] = True
    try:
        for k, v in vals.items():
            setattr(self, k, v)
    finally:
        _suspend["on"] = False
    _dirty(self, context)


def _look_kind_update(self, context):
    amount, duration = motion.LOOK_DEFAULTS.get(self.kind, (45.0, 2.5))
    _suspend["on"] = True
    try:
        self.amount = amount
        self.duration = duration
    finally:
        _suspend["on"] = False
    _dirty(self, context)


def _clip_update(self, context):
    c = clips.CLIP_BY_ID.get(self.clip)
    if c is not None:
        _suspend["on"] = True
        try:
            self.duration = c.default_duration
        finally:
            _suspend["on"] = False
    _dirty(self, context)


def _tone_update(self, context):
    from . import arms
    if self.arms is not None:
        arms.set_tone(self.id_data, self.skin_tone)


def _sleeve_update(self, context):
    from . import arms
    if self.arms is not None:
        arms.set_sleeve(self.id_data, self.sleeve)


def _build_update(self, context):
    from . import arms
    if self.arms is not None:
        arms.add(self.id_data, self.build, self.skin_tone, self.sleeve, self.watch)
        _dirty(self, context)


def _watch_update(self, context):
    from . import items
    if self.arms is not None:
        if self.watch:
            items.add_watch(self.id_data)
        else:
            items.remove_watch(self.id_data)


def _mesh_poll(self, ob):
    return ob.type == "MESH"


def _clip_items(self, context):
    return clips.enum_items()


class STRIDE_Point(bpy.types.PropertyGroup):
    obj: PointerProperty(type=bpy.types.Object, update=_dirty)
    role: EnumProperty(items=[("START", "Start", ""), ("WAY", "Waypoint", ""), ("END", "End", "")])
    wait: FloatProperty(name="Wait", default=0.0, min=0.0, soft_max=10.0, update=_dirty,
                        description="Seconds to stand still at this point before walking on")
    speed: FloatProperty(name="Speed", default=1.0, min=0.1, max=3.0, update=_dirty,
                         description="Speed from this point to the next, as a factor of the walking speed")


class STRIDE_Floor(bpy.types.PropertyGroup):
    obj: PointerProperty(type=bpy.types.Object, poll=_mesh_poll, update=_dirty)
    owned: BoolProperty(default=False, description="Created by the rig (deleted with it)")


class STRIDE_Look(bpy.types.PropertyGroup):
    kind: EnumProperty(name="Move", items=[k[:4] + (i,) for i, k in enumerate(motion.LOOK_KINDS)],
                       update=_look_kind_update)
    frame: IntProperty(name="Frame", default=1, update=_dirty, description="Frame the move starts on")
    duration: FloatProperty(name="Duration", default=2.5, min=0.3, soft_max=10.0, update=_dirty,
                            description="Seconds from turning away to looking ahead again")
    amount: FloatProperty(name="Amount", default=65.0, min=0.0, soft_max=170.0, update=_dirty,
                          description="How far the head turns (degrees); for Look At, how fully")
    target: PointerProperty(name="Target", type=bpy.types.Object, update=_dirty,
                            description="What to look at")


class STRIDE_Clip(bpy.types.PropertyGroup):
    clip: EnumProperty(name="Action", items=_clip_items, update=_clip_update)
    frame: IntProperty(name="Frame", default=1, update=_dirty, description="Frame the action starts on")
    duration: FloatProperty(name="Duration", default=6.0, min=0.5, soft_max=30.0, update=_dirty,
                            description="Seconds from raising the hands to lowering them again")
    mirror: BoolProperty(name="Other Hand", default=False, update=_dirty,
                         description="Do it with the other hand")
    head: FloatProperty(name="Head Follows", default=1.0, min=0.0, max=1.0, subtype="FACTOR", update=_dirty,
                        description="How much the head looks at what the hands are doing")


class STRIDE_Rig(bpy.types.PropertyGroup):
    is_rig: BoolProperty(default=False)
    collection: PointerProperty(type=bpy.types.Collection)
    arms: PointerProperty(type=bpy.types.Object)
    body: PointerProperty(type=bpy.types.Object)
    live: BoolProperty(name="Live Update", default=True,
                       description="Update the animation as soon as boxes, floors or settings change. "
                                   "Off freezes the keys so you can edit them by hand")

    points: CollectionProperty(type=STRIDE_Point)
    point_index: IntProperty()
    floors: CollectionProperty(type=STRIDE_Floor)
    floor_index: IntProperty()
    looks: CollectionProperty(type=STRIDE_Look)
    look_index: IntProperty()
    clips: CollectionProperty(type=STRIDE_Clip)
    clip_index: IntProperty()

    frame_start: IntProperty(name="Start Frame", default=1, update=_dirty,
                             description="Frame the walk starts on")
    end_hold: FloatProperty(name="Hold at End", default=2.0, min=0.0, soft_max=20.0, update=_dirty,
                            description="Seconds to keep animating (breathing, looking) after arriving")
    start_delay: FloatProperty(name="Wait at Start", default=0.6, min=0.0, soft_max=20.0, update=_dirty,
                               description="Seconds standing at the start before the first step")
    use_start_facing: BoolProperty(name="Start Facing Box Arrow", default=False, update=_dirty,
                                   description="Stand facing the start box's arrow, then turn to walk")
    use_end_facing: BoolProperty(name="Turn to End Box Arrow", default=False, update=_dirty,
                                 description="After arriving, turn to face the end box's arrow")

    style: EnumProperty(name="Style", items=[s[:3] + (i,) for i, s in enumerate(STYLES)], default="WALK",
                        update=_style_update)
    speed: FloatProperty(name="Speed", default=1.35, min=0.1, soft_max=8.0, unit="VELOCITY", update=_dirty,
                         description="Walking speed on flat ground")
    step: FloatProperty(name="Step Length", default=0.72, min=0.2, soft_max=2.0, unit="LENGTH", update=_dirty)
    eye: FloatProperty(name="Eye Height", default=1.62, min=0.3, soft_max=2.2, unit="LENGTH", update=_dirty,
                       description="Height of the eyes above the floor when standing")
    crouch: FloatProperty(name="Crouch", default=0.0, min=0.0, soft_max=0.8, unit="LENGTH", update=_dirty,
                          description="Lowers the eyes, for sneaking or a chest camera")
    bob: FloatProperty(name="Bob", default=0.016, min=0.0, soft_max=0.08, unit="LENGTH", update=_dirty,
                       description="Up and down with each step")
    sway: FloatProperty(name="Sway", default=0.010, min=0.0, soft_max=0.08, unit="LENGTH", update=_dirty,
                        description="Side to side over each foot")
    roll: FloatProperty(name="Roll", default=0.6, min=0.0, soft_max=5.0, update=_dirty,
                        description="Tilt with the sway (degrees)")
    accel: FloatProperty(name="Acceleration", default=0.9, min=0.1, soft_max=5.0, update=_dirty,
                         description="How quickly the walk starts and stops (m/s²)")
    stairs: FloatProperty(name="Stairs Slowdown", default=1.8, min=0.0, soft_max=5.0, update=_dirty,
                          description="How much stairs and slopes slow the walk")
    stair_rhythm: FloatProperty(name="Stair Steps", default=0.5, min=0.0, max=1.0, subtype="FACTOR",
                                update=_dirty, description="0 glides up stairs, 1 lifts the body step by step")

    look_ahead: FloatProperty(name="Look Ahead", default=2.5, min=0.3, soft_max=10.0, unit="LENGTH",
                              update=_dirty, description="How far along the path the eyes lead into turns")
    head_lag: FloatProperty(name="Head Smoothness", default=0.3, min=0.0, soft_max=1.5, update=_dirty,
                            description="How slowly the head follows the path (seconds)")
    pitch: FloatProperty(name="Look Down", default=-3.0, soft_min=-30.0, soft_max=20.0, update=_dirty,
                         description="Resting head pitch (degrees; negative looks down)")
    follow_slope: FloatProperty(name="Follow Slopes", default=0.35, min=0.0, max=1.0, subtype="FACTOR",
                                update=_dirty, description="Look up and down slopes and stairs")
    watch_step: FloatProperty(name="Watch Steps", default=10.0, min=0.0, soft_max=30.0, update=_dirty,
                              description="Extra look down on stairs (degrees)")
    shake: FloatProperty(name="Handheld", default=0.35, min=0.0, soft_max=3.0, update=_dirty,
                         description="Gentle wander of the head (degrees)")
    breathing: FloatProperty(name="Breathing", default=1.0, min=0.0, soft_max=3.0, update=_dirty,
                             description="Rise and fall of breathing while standing")
    seed: IntProperty(name="Seed", default=0, update=_dirty, description="Changes the random head wander")

    skin_tone: EnumProperty(name="Skin", items=[(t[0], t[1], "") for t in materials.SKIN_TONES], default="LIGHT",
                            update=_tone_update)
    sleeve: EnumProperty(name="Sleeves", items=[s[:3] for s in materials.SLEEVES], default="JACKET",
                         update=_sleeve_update)
    build: EnumProperty(name="Build", default="AVERAGE", update=_build_update, items=[
        ("AVERAGE", "Average", "Average adult arms and hands"),
        ("SLIM", "Slim", "Smaller, slimmer arms and hands"),
        ("STRONG", "Strong", "Bigger, more muscular arms and hands"),
    ])
    watch: BoolProperty(name="Wristwatch", default=True, update=_watch_update,
                        description="A watch on the left wrist")
    in_view: FloatProperty(name="Hands in View", default=0.7, min=0.0, max=1.0, subtype="FACTOR", update=_dirty,
                           description="Lift raised hands into the camera's view. 0 keeps them where a real "
                                       "body would hold them (often below the frame), 1 frames them like a game")
    hand_sway: FloatProperty(name="Hand Sway", default=1.0, min=0.0, soft_max=3.0, update=_dirty,
                             description="How much the hands lag and bob with the walk and head turns")


def _rig_poll(self, ob):
    return ob.type == "CAMERA" and ob.stride.is_rig


class STRIDE_Scene(bpy.types.PropertyGroup):
    rig: PointerProperty(type=bpy.types.Object, poll=_rig_poll, name="Walk",
                         description="The POV walk shown in this panel")
    show_path: BoolProperty(name="Show Path", default=True, description="Draw the walk's path in the viewport")
    show_steps: BoolProperty(name="Footsteps", default=True, description="Draw footsteps along the path")
    show_time: BoolProperty(name="Seconds", default=True, description="Mark every second along the path")
    new_look: EnumProperty(name="Look Move", items=[k[:4] + (i,) for i, k in enumerate(motion.LOOK_KINDS)])
    new_clip: EnumProperty(name="Hand Action", items=_clip_items)
    stairs_steps: IntProperty(name="Steps", default=10, min=1, max=200)
    stairs_rise: FloatProperty(name="Rise", default=0.17, soft_min=-0.4, soft_max=0.4, unit="LENGTH",
                               description="Height of each step (negative goes down)")
    stairs_run: FloatProperty(name="Depth", default=0.28, min=0.05, soft_max=1.0, unit="LENGTH")
    stairs_width: FloatProperty(name="Width", default=1.4, min=0.2, soft_max=10.0, unit="LENGTH")


CLASSES = (STRIDE_Point, STRIDE_Floor, STRIDE_Look, STRIDE_Clip, STRIDE_Rig, STRIDE_Scene)


def register():
    for c in CLASSES:
        bpy.utils.register_class(c)
    bpy.types.Object.stride = PointerProperty(type=STRIDE_Rig)
    bpy.types.Scene.stride = PointerProperty(type=STRIDE_Scene)


def unregister():
    del bpy.types.Scene.stride
    del bpy.types.Object.stride
    for c in reversed(CLASSES):
        bpy.utils.unregister_class(c)
