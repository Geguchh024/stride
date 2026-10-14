# SPDX-License-Identifier: GPL-3.0-or-later
"""Sidebar panels (3D View > POV): the walk, its path and floors, walking style, head and hands."""

import bpy

from . import clips, motion, rig, solve

ROLE_ICON = {"START": "PLAY", "END": "SNAP_FACE", "WAY": "DOT"}
LOOK_ICON = {k[0]: k[3] for k in motion.LOOK_KINDS}


def _fps(context):
    return solve.fps(context.scene)


class STRIDE_UL_points(bpy.types.UIList):
    def draw_item(self, context, layout, data, item, icon, active_data, active_prop, index):
        row = layout.row(align=True)
        name = item.obj.name if item.obj else "(missing)"
        row.label(text=name, icon=ROLE_ICON[item.role])
        if item.role == "WAY" and item.wait > 0:
            row.label(text=f"wait {item.wait:g}s")
        if item.obj is not None:
            op = row.operator("stride.select", text="", icon="RESTRICT_SELECT_OFF", emboss=False)
            op.name = item.obj.name


class STRIDE_UL_floors(bpy.types.UIList):
    def draw_item(self, context, layout, data, item, icon, active_data, active_prop, index):
        row = layout.row(align=True)
        row.label(text=item.obj.name if item.obj else "(missing)",
                  icon="MESH_GRID" if item.owned else "OUTLINER_OB_MESH")
        if item.obj is not None:
            op = row.operator("stride.select", text="", icon="RESTRICT_SELECT_OFF", emboss=False)
            op.name = item.obj.name


class STRIDE_UL_looks(bpy.types.UIList):
    def draw_item(self, context, layout, data, item, icon, active_data, active_prop, index):
        row = layout.row(align=True)
        label = next(k[1] for k in motion.LOOK_KINDS if k[0] == item.kind)
        if item.kind == "AT" and item.target is not None:
            label = f"Look at {item.target.name}"
        row.label(text=label, icon=LOOK_ICON[item.kind])
        row.operator("stride.jump", text=str(item.frame), emboss=False).frame = item.frame


class STRIDE_UL_clips(bpy.types.UIList):
    def draw_item(self, context, layout, data, item, icon, active_data, active_prop, index):
        row = layout.row(align=True)
        c = clips.CLIP_BY_ID.get(item.clip)
        row.label(text=(c.label if c else item.clip) + ("  (other hand)" if item.mirror else ""),
                  icon=c.icon if c else "HAND")
        row.operator("stride.jump", text=str(item.frame), emboss=False).frame = item.frame


class STRIDE_PT_base:
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "POV"


class STRIDE_PT_main(STRIDE_PT_base, bpy.types.Panel):
    bl_label = "Stride POV"
    bl_idname = "STRIDE_PT_main"

    def draw(self, context):
        layout = self.layout
        sc = context.scene
        cam = rig.active_rig(context)
        if cam is None:
            col = layout.column()
            col.label(text="Walk through your scene in first person.")
            col.label(text="Adds a camera, start and end boxes and")
            col.label(text="an invisible floor at the 3D cursor.")
            row = col.row()
            row.scale_y = 2.0
            row.operator("stride.create", icon="CON_FOLLOWPATH")
            return
        r = cam.stride
        col = layout.column()
        row = col.row(align=True)
        row.prop(sc.stride, "rig", text="", icon="OUTLINER_OB_CAMERA")
        row.operator("stride.create", text="", icon="ADD")
        row.operator("stride.delete", text="", icon="TRASH")

        pl = solve.cached_plan(cam)
        if pl is not None:
            f = _fps(context)
            first, last = solve.frame_range(cam, sc, pl)
            box = col.box()
            b = box.column(align=True)
            b.label(text=f"{pl.length:.1f} m  ·  {pl.duration:.1f} s  ·  {len(pl.plants) - 1} steps",
                    icon="TRACKING_FORWARDS")
            b.label(text=f"Arrives on frame {r.frame_start + int(round(pl.duration * f))}, "
                         f"keys {first} to {last}", icon="TIME")
            if pl.hit.size and pl.hit.any() and not pl.hit.all():
                b.label(text="Part of the path is off the floor (red)", icon="ERROR")

        row = col.row(align=True)
        row.scale_y = 1.4
        row.operator("stride.look_through", icon="VIEW_CAMERA")
        row.operator("stride.fit_range", icon="ARROW_LEFTRIGHT")
        row = col.row(align=True)
        row.prop(r, "live", toggle=True, icon="FILE_REFRESH" if r.live else "FREEZE")
        row.operator("stride.update", text="", icon="PLAY")
        row = col.row(align=True)
        row.prop(sc.stride, "show_path", toggle=True, icon="CURVE_PATH")
        sub = row.row(align=True)
        sub.active = sc.stride.show_path
        sub.prop(sc.stride, "show_steps", toggle=True, text="", icon="MOD_DYNAMICPAINT")
        sub.prop(sc.stride, "show_time", toggle=True, text="", icon="TIME")


class _RigPanel(STRIDE_PT_base):
    bl_parent_id = "STRIDE_PT_main"

    @classmethod
    def poll(cls, context):
        return rig.active_rig(context) is not None


class STRIDE_PT_path(_RigPanel, bpy.types.Panel):
    bl_label = "Path"

    def draw(self, context):
        cam = rig.active_rig(context)
        r = cam.stride
        layout = self.layout
        row = layout.row()
        row.template_list("STRIDE_UL_points", "", r, "points", r, "point_index", rows=3)
        side = row.column(align=True)
        side.operator("stride.add_waypoint", text="", icon="ADD")
        side.operator("stride.remove_point", text="", icon="REMOVE")
        side.separator()
        side.operator("stride.move_point", text="", icon="TRIA_UP").direction = "UP"
        side.operator("stride.move_point", text="", icon="TRIA_DOWN").direction = "DOWN"
        if 0 <= r.point_index < len(r.points):
            it = r.points[r.point_index]
            col = layout.column(align=True)
            if it.role == "WAY":
                col.prop(it, "wait", text="Wait (s)")
            if it.role != "END":
                col.prop(it, "speed", text="Speed to Next", slider=True)
        col = layout.column(align=True)
        col.prop(r, "frame_start")
        col.prop(r, "start_delay", text="Wait at Start (s)")
        col.prop(r, "end_hold", text="Hold at End (s)")
        col = layout.column(align=True)
        col.prop(r, "use_start_facing")
        col.prop(r, "use_end_facing")
        layout.operator("stride.footstep_markers", icon="MARKER_HLT")


class STRIDE_PT_floor(_RigPanel, bpy.types.Panel):
    bl_label = "Floor"

    def draw(self, context):
        cam = rig.active_rig(context)
        r = cam.stride
        sc = context.scene
        layout = self.layout
        row = layout.row()
        row.template_list("STRIDE_UL_floors", "", r, "floors", r, "floor_index", rows=2)
        side = row.column(align=True)
        side.operator_menu_enum("stride.add_floor", "kind", text="", icon="ADD")
        side.operator("stride.remove_floor", text="", icon="REMOVE")
        row = layout.row(align=True)
        row.operator("stride.edit_floor", icon="EDITMODE_HLT")
        row.operator("stride.conform_floor", icon="SNAP_FACE")
        box = layout.box()
        box.label(text="New Stairs", icon="MOD_ARRAY")
        grid = box.grid_flow(columns=2, align=True)
        grid.prop(sc.stride, "stairs_steps")
        grid.prop(sc.stride, "stairs_rise")
        grid.prop(sc.stride, "stairs_run")
        grid.prop(sc.stride, "stairs_width")
        box.operator("stride.add_floor", text="Add Stairs at Cursor", icon="ADD").kind = "STAIRS"


class STRIDE_PT_walk(_RigPanel, bpy.types.Panel):
    bl_label = "Walk"

    def draw(self, context):
        r = rig.active_rig(context).stride
        layout = self.layout
        layout.grid_flow(columns=3, align=True).prop(r, "style", expand=True)
        col = layout.column(align=True)
        col.prop(r, "speed")
        col.prop(r, "step")
        col = layout.column(align=True)
        col.prop(r, "eye")
        col.prop(r, "crouch")


class STRIDE_PT_walk_feel(_RigPanel, bpy.types.Panel):
    bl_label = "Body Motion"
    bl_parent_id = "STRIDE_PT_walk"
    bl_options = {"DEFAULT_CLOSED"}

    def draw(self, context):
        r = rig.active_rig(context).stride
        col = self.layout.column(align=True)
        col.prop(r, "bob")
        col.prop(r, "sway")
        col.prop(r, "roll")
        col = self.layout.column(align=True)
        col.prop(r, "accel")
        col.prop(r, "stairs")
        col.prop(r, "stair_rhythm", slider=True)


class STRIDE_PT_head(_RigPanel, bpy.types.Panel):
    bl_label = "Head"

    def draw(self, context):
        cam = rig.active_rig(context)
        r = cam.stride
        sc = context.scene
        layout = self.layout
        col = layout.column(align=True)
        col.prop(r, "look_ahead")
        col.prop(r, "head_lag")
        col.prop(r, "pitch")
        col = layout.column(align=True)
        col.prop(r, "follow_slope", slider=True)
        col.prop(r, "watch_step")
        col = layout.column(align=True)
        col.prop(r, "shake")
        col.prop(r, "breathing")
        col.prop(r, "seed")

        layout.label(text="Look Moves", icon="HIDE_OFF")
        row = layout.row(align=True)
        row.prop(sc.stride, "new_look", text="")
        row.operator("stride.add_look", text=f"Add at {sc.frame_current}", icon="ADD")
        if len(r.looks):
            row = layout.row()
            row.template_list("STRIDE_UL_looks", "", r, "looks", r, "look_index", rows=2)
            row.operator("stride.remove_look", text="", icon="REMOVE")
            if 0 <= r.look_index < len(r.looks):
                it = r.looks[r.look_index]
                col = layout.column(align=True)
                col.prop(it, "kind")
                col.prop(it, "frame")
                col.prop(it, "duration", text="Duration (s)")
                if it.kind == "AT":
                    col.prop(it, "target")
                    col.prop(it, "amount", text="Strength")
                else:
                    col.prop(it, "amount", text="Angle")


class STRIDE_PT_hands(_RigPanel, bpy.types.Panel):
    bl_label = "Hands"

    def draw(self, context):
        cam = rig.active_rig(context)
        r = cam.stride
        sc = context.scene
        layout = self.layout
        col = layout.column(align=True)
        col.prop(r, "skin_tone")
        col.prop(r, "sleeve")
        col.prop(r, "build")
        col.prop(r, "watch")
        if r.arms is None:
            row = layout.row()
            row.scale_y = 1.6
            row.operator("stride.add_arms", icon="VIEW_PAN")
            return
        col.prop(r, "in_view", slider=True)
        col.prop(r, "hand_sway")
        layout.operator("stride.remove_arms", icon="TRASH")

        layout.label(text="Actions", icon="ARMATURE_DATA")
        col = layout.column(align=True)
        col.prop(sc.stride, "new_clip", text="")
        c = clips.CLIP_BY_ID.get(sc.stride.new_clip)
        row = col.row(align=True)
        row.scale_y = 1.4
        row.operator("stride.add_clip", text=f"Add at Frame {sc.frame_current}", icon="ADD").clip = \
            sc.stride.new_clip
        if c is not None:
            col.label(text=c.description, icon="INFO")
        if len(r.clips):
            row = layout.row()
            row.template_list("STRIDE_UL_clips", "", r, "clips", r, "clip_index", rows=3)
            row.operator("stride.remove_clip", text="", icon="REMOVE")
            if 0 <= r.clip_index < len(r.clips):
                it = r.clips[r.clip_index]
                col = layout.column(align=True)
                col.prop(it, "clip", text="")
                col.prop(it, "frame")
                col.prop(it, "duration", text="Duration (s)")
                col.prop(it, "head", slider=True)
                col.prop(it, "mirror")


class STRIDE_PT_camera(_RigPanel, bpy.types.Panel):
    bl_label = "Camera"
    bl_options = {"DEFAULT_CLOSED"}

    def draw(self, context):
        cam = rig.active_rig(context)
        col = self.layout.column(align=True)
        col.prop(cam.data, "lens")
        col.prop(cam.data, "sensor_width")
        col.prop(cam.data, "clip_start")
        col = self.layout.column()
        col.prop(context.scene.render, "use_motion_blur")


CLASSES = (STRIDE_UL_points, STRIDE_UL_floors, STRIDE_UL_looks, STRIDE_UL_clips, STRIDE_PT_main,
           STRIDE_PT_path, STRIDE_PT_floor, STRIDE_PT_walk, STRIDE_PT_walk_feel, STRIDE_PT_head,
           STRIDE_PT_hands, STRIDE_PT_camera)


def register():
    for c in CLASSES:
        bpy.utils.register_class(c)


def unregister():
    for c in reversed(CLASSES):
        bpy.utils.unregister_class(c)
