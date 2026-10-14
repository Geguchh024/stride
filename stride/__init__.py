# SPDX-License-Identifier: GPL-3.0-or-later
"""Stride: first-person walks for Blender. A POV camera walks from a start box to an end box
over an invisible floor, with natural head motion and animated hands."""


def register():
    from . import handlers, ops, overlay, props, ui
    props.register()
    ops.register()
    ui.register()
    overlay.register()
    handlers.register()


def unregister():
    from . import handlers, ops, overlay, props, ui
    handlers.unregister()
    overlay.unregister()
    ui.unregister()
    ops.unregister()
    props.unregister()
