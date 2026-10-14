# SPDX-License-Identifier: GPL-3.0-or-later
"""Writing the solved motion as plain keyframes, one per frame.

Keys keep the result portable: it renders without the add-on, exports to
game engines, and shows up in the Graph Editor like any animation.
"""

import numpy as np
from bpy_extras import anim_utils


def channelbag(id_data, action_name, slot_type="OBJECT"):
    """The channelbag for ``id_data``'s own action, created if needed."""
    import bpy
    ad = id_data.animation_data or id_data.animation_data_create()
    act = ad.action
    if act is None:
        act = bpy.data.actions.new(action_name)
        ad.action = act
    if ad.action_slot is None:
        slot = act.slots[0] if len(act.slots) else act.slots.new(id_type=slot_type, name=id_data.name)
        ad.action_slot = slot
    return anim_utils.action_ensure_channelbag_for_slot(act, ad.action_slot)


def write(bag, path, index, frames, values, group=None, constant=False):
    """Replace one F-curve's keys with (frames, values)."""
    fc = bag.fcurves.find(path, index=index)
    if fc is None:
        fc = bag.fcurves.new(path, index=index, group_name=group or "")
    kp = fc.keyframe_points
    n = len(frames)
    if len(kp) != n:
        kp.clear()
        kp.add(n)
    co = np.empty(2 * n, np.float32)
    co[0::2] = frames
    co[1::2] = values
    kp.foreach_set("co", co)
    if constant:
        for k in kp:
            k.interpolation = "CONSTANT"
    fc.update()
    return fc


def write_vector(bag, path, frames, rows, group=None, constant=False):
    rows = np.asarray(rows, np.float64)
    for i in range(rows.shape[1]):
        write(bag, path, i, frames, rows[:, i], group, constant)


def remove_missing(bag, keep):
    """Drop F-curves this bake no longer writes (e.g. a removed prop)."""
    for fc in list(bag.fcurves):
        if (fc.data_path, fc.array_index) not in keep:
            bag.fcurves.remove(fc)


def euler_rows(matrices):
    """Locations and continuous XYZ Euler rotations of a list of matrices."""
    locs, rots = [], []
    prev = None
    for m in matrices:
        locs.append(tuple(m.translation))
        e = m.to_euler("XYZ", prev) if prev is not None else m.to_euler("XYZ")
        rots.append(tuple(e))
        prev = e
    return np.array(locs), np.array(rots)


def bake_object(ob, frames, matrices, action_name):
    """Key an unparented object's transform on every frame."""
    ob.rotation_mode = "XYZ"
    bag = channelbag(ob, action_name)
    locs, rots = euler_rows(matrices)
    write_vector(bag, "location", frames, locs, "Object Transforms")
    write_vector(bag, "rotation_euler", frames, rots, "Object Transforms")
    return bag
