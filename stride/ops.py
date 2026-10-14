# SPDX-License-Identifier: GPL-3.0-or-later
"""Operators: create a walk, edit its points and floors, add look moves and hand actions."""

import math

import bpy
import numpy as np
from bpy.props import BoolProperty, EnumProperty, IntProperty
from mathutils import Vector

from . import arms, clips, floor, handlers, motion, rig, solve


def _rig(context):
    return rig.active_rig(context)


def _update_now(cam):
    try:
        solve.update(cam)
    finally:
        handlers._redraw()


def _view_yaw(context):
    rv3d = getattr(context.space_data, "region_3d", None) if context.space_data else None
    if rv3d is None:
        return math.pi / 2
    d = rv3d.view_rotation @ Vector((0.0, 0.0, -1.0))
    if d.xy.length < 1e-4:
        d = rv3d.view_rotation @ Vector((0.0, 1.0, 0.0))
    return math.atan2(d.y, d.x)


class _RigOp:
    @classmethod
    def poll(cls, context):
        return _rig(context) is not None


class STRIDE_OT_create(bpy.types.Operator):
    bl_idname = "stride.create"
    bl_label = "Create POV Walk"
    bl_description = ("Add a POV camera, start and end boxes and an invisible floor at the 3D cursor, "
                      "walking the way the view looks")
    bl_options = {"REGISTER", "UNDO"}

    use_selected: BoolProperty(name="Walk on Selected", default=False,
                               description="Use the selected mesh as the floor instead of a new floor plane")
    length: bpy.props.FloatProperty(name="Distance", default=6.0, min=0.5, soft_max=50.0, unit="LENGTH")

    def invoke(self, context, event):
        ob = context.active_object
        self.use_selected = ob is not None and ob.type == "MESH" and ob.select_get() and rig.rig_of(ob) is None
        return self.execute(context)

    def execute(self, context):
        if context.mode != "OBJECT":
            bpy.ops.object.mode_set(mode="OBJECT")
        ob = context.active_object
        floor_from = ob if self.use_selected and ob is not None and ob.type == "MESH" else None
        cam = rig.create(context, context.scene.cursor.location.copy(), _view_yaw(context), self.length,
                         floor_from=floor_from)
        if floor_from is not None:
            # stand the boxes on the selected surface
            dg = context.evaluated_depsgraph_get()
            ground = floor.Ground([floor_from], dg)
            for it in cam.stride.points:
                p = it.obj.location
                z = ground.height(p.x, p.y, p.z + 50.0, up=0.0, down=200.0)
                if z is not None:
                    it.obj.location.z = z
        for o in context.selected_objects:
            o.select_set(False)
        end = cam.stride.points[-1].obj
        end.select_set(True)
        context.view_layer.objects.active = end
        _update_now(cam)
        self.report({"INFO"}, "Move the End box and the camera walks to it")
        return {"FINISHED"}


class STRIDE_OT_delete(_RigOp, bpy.types.Operator):
    bl_idname = "stride.delete"
    bl_label = "Delete Walk"
    bl_description = "Delete this walk: camera, boxes, its own floors, arms and props"
    bl_options = {"REGISTER", "UNDO"}

    def invoke(self, context, event):
        return context.window_manager.invoke_confirm(self, event)

    def execute(self, context):
        rig.delete(_rig(context))
        handlers._redraw()
        return {"FINISHED"}


class STRIDE_OT_update(_RigOp, bpy.types.Operator):
    bl_idname = "stride.update"
    bl_label = "Update"
    bl_description = "Solve the walk again and rewrite its keys"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        _update_now(_rig(context))
        return {"FINISHED"}


class STRIDE_OT_fit_range(_RigOp, bpy.types.Operator):
    bl_idname = "stride.fit_range"
    bl_label = "Fit Timeline"
    bl_description = "Set the scene's frame range to the whole walk, actions and hold included"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        cam = _rig(context)
        pl = solve.plan(cam)
        if pl is None:
            self.report({"WARNING"}, "The walk needs its Start and End boxes")
            return {"CANCELLED"}
        sc = context.scene
        first, last = solve.frame_range(cam, sc, pl)
        sc.frame_start, sc.frame_end = first, last
        return {"FINISHED"}


class STRIDE_OT_footstep_markers(_RigOp, bpy.types.Operator):
    bl_idname = "stride.footstep_markers"
    bl_label = "Footstep Markers"
    bl_description = ("Put a timeline marker on every footstep (L and R), for lining up footstep sounds. "
                      "Run again to refresh them")
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        cam = _rig(context)
        sc = context.scene
        pl = solve.plan(cam)
        if pl is None:
            self.report({"WARNING"}, "The walk needs its Start and End boxes")
            return {"CANCELLED"}
        prefix = "step "
        for m in list(sc.timeline_markers):
            if m.name.startswith(prefix):
                sc.timeline_markers.remove(m)
        f = solve.fps(sc)
        seen = set()
        for p in pl.plants:
            if p.side == 0:
                continue
            # the first time the walk reaches this footstep
            i = int(np.searchsorted(pl.knot_s, p.s - 1e-6))
            t = float(pl.knot_t[min(i, len(pl.knot_t) - 1)])
            frame = cam.stride.frame_start + int(round(t * f))
            if frame in seen:
                continue
            seen.add(frame)
            sc.timeline_markers.new(prefix + ("R" if p.side > 0 else "L"), frame=frame)
        self.report({"INFO"}, f"{len(seen)} footsteps marked")
        return {"FINISHED"}


class STRIDE_OT_look_through(_RigOp, bpy.types.Operator):
    bl_idname = "stride.look_through"
    bl_label = "Look Through"
    bl_description = "Make the POV camera the scene camera and look through it"

    def execute(self, context):
        cam = _rig(context)
        context.scene.camera = cam
        if context.space_data and context.space_data.type == "VIEW_3D":
            context.space_data.region_3d.view_perspective = "CAMERA"
        return {"FINISHED"}


# -- points ----------------------------------------------------------------------------

class STRIDE_OT_add_waypoint(_RigOp, bpy.types.Operator):
    bl_idname = "stride.add_waypoint"
    bl_label = "Add Waypoint"
    bl_description = "Add a point the walk passes through, before the End box"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        cam = _rig(context)
        ob = rig.add_waypoint(cam)
        for o in context.selected_objects:
            o.select_set(False)
        ob.select_set(True)
        context.view_layer.objects.active = ob
        cam.stride.point_index = len(cam.stride.points) - 2
        handlers.request(cam)
        return {"FINISHED"}


class STRIDE_OT_remove_point(_RigOp, bpy.types.Operator):
    bl_idname = "stride.remove_point"
    bl_label = "Remove Waypoint"
    bl_description = "Remove the selected waypoint (the start and end stay)"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        cam = _rig(context)
        if cam is None:
            return False
        r = cam.stride
        return 0 <= r.point_index < len(r.points) and r.points[r.point_index].role == "WAY"

    def execute(self, context):
        cam = _rig(context)
        r = cam.stride
        it = r.points[r.point_index]
        ob = it.obj
        r.points.remove(r.point_index)
        if ob is not None:
            bpy.data.objects.remove(ob, do_unlink=True)
        r.point_index = min(r.point_index, len(r.points) - 1)
        handlers.request(cam)
        return {"FINISHED"}


class STRIDE_OT_move_point(_RigOp, bpy.types.Operator):
    bl_idname = "stride.move_point"
    bl_label = "Move Waypoint"
    bl_description = "Change the order the walk visits the waypoints"
    bl_options = {"REGISTER", "UNDO"}

    direction: EnumProperty(items=[("UP", "Up", ""), ("DOWN", "Down", "")])

    def execute(self, context):
        cam = _rig(context)
        r = cam.stride
        i = r.point_index
        j = i - 1 if self.direction == "UP" else i + 1
        if not (0 < i < len(r.points) - 1 and 0 < j < len(r.points) - 1):
            return {"CANCELLED"}
        r.points.move(i, j)
        r.point_index = j
        handlers.request(cam)
        return {"FINISHED"}


class STRIDE_OT_select(bpy.types.Operator):
    bl_idname = "stride.select"
    bl_label = "Select"
    bl_description = "Select this object in the viewport"
    bl_options = {"REGISTER", "UNDO"}

    name: bpy.props.StringProperty()

    def execute(self, context):
        ob = bpy.data.objects.get(self.name)
        if ob is None:
            return {"CANCELLED"}
        if context.mode != "OBJECT":
            bpy.ops.object.mode_set(mode="OBJECT")
        for o in context.selected_objects:
            o.select_set(False)
        ob.hide_set(False)
        ob.select_set(True)
        context.view_layer.objects.active = ob
        return {"FINISHED"}


# -- floors ------------------------------------------------------------------------------

class STRIDE_OT_add_floor(_RigOp, bpy.types.Operator):
    bl_idname = "stride.add_floor"
    bl_label = "Add Floor"
    bl_description = "Add something for the walk to stand on"
    bl_options = {"REGISTER", "UNDO"}

    kind: EnumProperty(items=[
        ("PLANE", "Floor Plane", "An invisible floor strip at the 3D cursor; edit it to shape slopes and steps"),
        ("STAIRS", "Stairs", "An invisible flight of stairs at the 3D cursor"),
        ("SELECTED", "Selected Objects", "Walk on the selected meshes (terrain, buildings...)"),
    ])

    def execute(self, context):
        cam = _rig(context)
        sc = context.scene
        yaw = _view_yaw(context) - math.pi / 2
        loc = sc.cursor.location.copy()
        if self.kind == "PLANE":
            me = floor.grid_mesh("POV Floor", 8.0, 2.0)
            ob = bpy.data.objects.new("POV Floor", me)
            (cam.stride.collection or cam.users_collection[0]).objects.link(ob)
            ob.location = loc
            ob.rotation_euler.z = yaw
            floor.setup_object(ob)
            rig.add_floor(cam, ob, owned=True)
        elif self.kind == "STAIRS":
            p = sc.stride
            rig.add_stairs(cam, loc, yaw, steps=p.stairs_steps, rise=p.stairs_rise, run=p.stairs_run,
                           width=p.stairs_width)
        else:
            added = 0
            mine = rig.rig_objects(cam)
            for ob in context.selected_objects:
                if ob.type == "MESH" and ob not in mine:
                    rig.add_floor(cam, ob, owned=False)
                    added += 1
            if not added:
                self.report({"WARNING"}, "Select one or more meshes to walk on")
                return {"CANCELLED"}
        cam.stride.floor_index = len(cam.stride.floors) - 1
        handlers.request(cam)
        return {"FINISHED"}


class STRIDE_OT_remove_floor(_RigOp, bpy.types.Operator):
    bl_idname = "stride.remove_floor"
    bl_label = "Remove Floor"
    bl_description = "Stop walking on this floor (floors the walk created are deleted)"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        cam = _rig(context)
        r = cam.stride
        if not (0 <= r.floor_index < len(r.floors)):
            return {"CANCELLED"}
        it = r.floors[r.floor_index]
        ob, owned = it.obj, it.owned
        r.floors.remove(r.floor_index)
        if ob is not None and owned:
            bpy.data.objects.remove(ob, do_unlink=True)
        r.floor_index = max(0, min(r.floor_index, len(r.floors) - 1))
        handlers.request(cam)
        return {"FINISHED"}


class STRIDE_OT_edit_floor(_RigOp, bpy.types.Operator):
    bl_idname = "stride.edit_floor"
    bl_label = "Edit Floor Shape"
    bl_description = "Edit the floor mesh: move, extrude or bevel it to match steps and slopes. The walk updates live"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        cam = _rig(context)
        r = cam.stride
        if not (0 <= r.floor_index < len(r.floors)) or r.floors[r.floor_index].obj is None:
            return {"CANCELLED"}
        ob = r.floors[r.floor_index].obj
        if context.mode != "OBJECT":
            bpy.ops.object.mode_set(mode="OBJECT")
        for o in context.selected_objects:
            o.select_set(False)
        ob.hide_set(False)
        ob.select_set(True)
        context.view_layer.objects.active = ob
        bpy.ops.object.mode_set(mode="EDIT")
        return {"FINISHED"}


class STRIDE_OT_conform_floor(_RigOp, bpy.types.Operator):
    bl_idname = "stride.conform_floor"
    bl_label = "Drop onto Scene"
    bl_description = ("Drop every vertex of this floor onto the scene geometry under it, so a flat grid "
                      "follows real stairs, slopes and paving")
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        cam = _rig(context)
        r = cam.stride
        if not (0 <= r.floor_index < len(r.floors)) or r.floors[r.floor_index].obj is None:
            return {"CANCELLED"}
        ob = r.floors[r.floor_index].obj
        if context.mode != "OBJECT":
            bpy.ops.object.mode_set(mode="OBJECT")
        moved = floor.conform(ob, rig.rig_objects(cam) | {ob}, context.evaluated_depsgraph_get())
        self.report({"INFO"}, f"{moved} floor points dropped onto the scene")
        handlers.request(cam)
        return {"FINISHED"}


# -- look moves and hand actions ---------------------------------------------------------------

class STRIDE_OT_add_look(_RigOp, bpy.types.Operator):
    bl_idname = "stride.add_look"
    bl_label = "Add Look Move"
    bl_description = "Add a head move starting on the current frame"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        cam = _rig(context)
        sc = context.scene
        r = cam.stride
        from . import props
        props._suspend["on"] = True
        try:
            it = r.looks.add()
            it.kind = sc.stride.new_look
            amount, duration = motion.LOOK_DEFAULTS[it.kind]
            it.amount, it.duration = amount, duration
            it.frame = sc.frame_current
            if it.kind == "AT":
                sel = [o for o in context.selected_objects if o not in rig.rig_objects(cam)]
                it.target = sel[0] if sel else None
        finally:
            props._suspend["on"] = False
        r.look_index = len(r.looks) - 1
        handlers.request(cam)
        return {"FINISHED"}


class STRIDE_OT_remove_look(_RigOp, bpy.types.Operator):
    bl_idname = "stride.remove_look"
    bl_label = "Remove Look Move"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        cam = _rig(context)
        r = cam.stride
        if 0 <= r.look_index < len(r.looks):
            r.looks.remove(r.look_index)
            r.look_index = max(0, r.look_index - 1)
            handlers.request(cam)
        return {"FINISHED"}


class STRIDE_OT_add_arms(_RigOp, bpy.types.Operator):
    bl_idname = "stride.add_arms"
    bl_label = "Add Hands"
    bl_description = "Give the walk arms and hands (the first time builds the meshes, which takes a moment)"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        cam = _rig(context)
        r = cam.stride
        if context.window:
            context.window.cursor_set("WAIT")
        try:
            arms.add(cam, r.build, r.skin_tone, r.sleeve, r.watch)
        finally:
            if context.window:
                context.window.cursor_set("DEFAULT")
        _update_now(cam)
        return {"FINISHED"}


class STRIDE_OT_remove_arms(_RigOp, bpy.types.Operator):
    bl_idname = "stride.remove_arms"
    bl_label = "Remove Hands"
    bl_description = "Remove the arms, hands and props"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        cam = _rig(context)
        from . import items
        for ob in items.owned(cam):
            bpy.data.objects.remove(ob, do_unlink=True)
        arms.remove(cam)
        handlers.request(cam)
        return {"FINISHED"}


class STRIDE_OT_add_clip(_RigOp, bpy.types.Operator):
    bl_idname = "stride.add_clip"
    bl_label = "Add Action"
    bl_description = "Add the hand action starting on the current frame"
    bl_options = {"REGISTER", "UNDO"}

    clip: EnumProperty(items=lambda self, context: clips.enum_items())

    def invoke(self, context, event):
        self.clip = context.scene.stride.new_clip
        return self.execute(context)

    def execute(self, context):
        cam = _rig(context)
        r = cam.stride
        if r.arms is None:
            arms.add(cam, r.build, r.skin_tone, r.sleeve, r.watch)
        from . import props
        props._suspend["on"] = True
        try:
            it = r.clips.add()
            it.clip = self.clip
            it.duration = clips.CLIP_BY_ID[self.clip].default_duration
            it.frame = context.scene.frame_current
        finally:
            props._suspend["on"] = False
        r.clip_index = len(r.clips) - 1
        _update_now(cam)
        return {"FINISHED"}


class STRIDE_OT_remove_clip(_RigOp, bpy.types.Operator):
    bl_idname = "stride.remove_clip"
    bl_label = "Remove Action"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        cam = _rig(context)
        r = cam.stride
        if 0 <= r.clip_index < len(r.clips):
            r.clips.remove(r.clip_index)
            r.clip_index = max(0, r.clip_index - 1)
            handlers.request(cam)
        return {"FINISHED"}


class STRIDE_OT_jump(bpy.types.Operator):
    bl_idname = "stride.jump"
    bl_label = "Go to Frame"
    bl_description = "Go to this frame"

    frame: IntProperty()

    def execute(self, context):
        context.scene.frame_set(self.frame)
        return {"FINISHED"}


CLASSES = (
    STRIDE_OT_create, STRIDE_OT_delete, STRIDE_OT_update, STRIDE_OT_fit_range, STRIDE_OT_look_through,
    STRIDE_OT_footstep_markers,
    STRIDE_OT_add_waypoint, STRIDE_OT_remove_point, STRIDE_OT_move_point, STRIDE_OT_select,
    STRIDE_OT_add_floor, STRIDE_OT_remove_floor, STRIDE_OT_edit_floor, STRIDE_OT_conform_floor,
    STRIDE_OT_add_look, STRIDE_OT_remove_look, STRIDE_OT_add_arms, STRIDE_OT_remove_arms,
    STRIDE_OT_add_clip, STRIDE_OT_remove_clip, STRIDE_OT_jump,
)


def register():
    for c in CLASSES:
        bpy.utils.register_class(c)


def unregister():
    for c in reversed(CLASSES):
        bpy.utils.unregister_class(c)
