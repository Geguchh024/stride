# SPDX-License-Identifier: GPL-3.0-or-later
"""The hand action library.

An action is a few keys per hand: where the wrist is (body frame, metres;
or head frame, so it follows the head, e.g. at the mouth), which way the
fingers point and the palm faces, and a finger pose. ``REST`` keys mean the
arm hanging at the side (swinging with the walk). Everything is written for
the right hand; *Other Hand* mirrors it. A ``loop`` span repeats to fill a
longer duration (another drag, another sip).

Body frame: origin at the eyes, +X right, +Y forward, +Z up. The right
shoulder is at about (0.17, -0.07, -0.21).
"""

from dataclasses import dataclass, field

# head-frame places (from the eyes)
MOUTH = (0.0, 0.03, -0.078)


@dataclass
class Key:
    t: float
    at: tuple = None              # wrist position; None = arm at rest by the side
    fingers: tuple = (0.0, 1.0, 0.0)
    palm: tuple = (0.0, 0.0, -1.0)
    pose: str = "RELAXED"
    elbow: tuple = (0.6, -0.3, -1.0)
    head: bool = False            # 'at' is in the head frame
    prop_to: tuple = None         # put the prop's tip here (head frame) instead of the wrist


def REST(t, pose="LIMP"):
    return Key(t, None, pose=pose)


@dataclass
class Clip:
    id: str
    label: str
    description: str
    icon: str
    category: str
    length: float                          # natural length of the keys (s)
    hands: dict = field(default_factory=dict)      # "R"/"L" -> [Key]
    props: dict = field(default_factory=dict)      # "R"/"L" -> (item id, grip id)
    head: list = field(default_factory=list)       # (t, yaw, pitch) degrees
    events: list = field(default_factory=list)     # (t, item, channel, value)
    loop: tuple = None                             # (t0, t1) repeated for longer durations
    default_duration: float = 0.0

    def __post_init__(self):
        if not self.default_duration:
            self.default_duration = self.length


CATEGORIES = [
    ("HABITS", "Habits", "Smoking, drinking, phones", "GHOST_ENABLED"),
    ("GESTURES", "Gestures", "Waving, pointing, signs", "HAND"),
    ("EXPLORE", "Explore", "Touching, pushing, light", "VIEWZOOM"),
]

# shorthand for directions (right hand, body frame)
UP, FWD, LEFT, RIGHT, DOWN, BACK = (0, 0, 1), (0, 1, 0), (-1, 0, 0), (1, 0, 0), (0, 0, -1), (0, -1, 0)


def _v(*parts):
    x = sum(p[0] for p in parts)
    y = sum(p[1] for p in parts)
    z = sum(p[2] for p in parts)
    return (x, y, z)


CLIPS = [
    Clip(
        "SMOKE", "Smoke a Cigarette", "Bring a cigarette to the lips, take a drag, lower it and breathe out",
        "GHOST_ENABLED", "HABITS", 7.0,
        hands={"R": [
            REST(0.0),
            Key(1.0, (0.13, 0.34, -0.40), fingers=(-0.25, 0.75, 0.6), palm=(-0.7, -0.1, -0.5), pose="CIG_V"),
            Key(1.7, None, fingers=(-0.45, 0.05, 0.9), palm=(0.12, -0.88, 0.45), pose="CIG_V",
                prop_to=MOUTH, elbow=(0.7, -0.1, -1.0)),
            Key(3.0, None, fingers=(-0.45, 0.05, 0.9), palm=(0.12, -0.88, 0.45), pose="CIG_V",
                prop_to=MOUTH, elbow=(0.7, -0.1, -1.0)),
            Key(3.8, (0.14, 0.36, -0.38), fingers=(-0.25, 0.75, 0.6), palm=(-0.7, -0.1, -0.5), pose="CIG_V"),
            Key(5.0, (0.14, 0.37, -0.37), fingers=(-0.2, 0.8, 0.55), palm=(-0.7, -0.1, -0.5), pose="CIG_V"),
            # flick the ash
            Key(5.25, (0.145, 0.375, -0.36), fingers=(-0.1, 0.9, 0.4), palm=(-0.75, 0.0, -0.6), pose="CIG_V"),
            Key(5.45, (0.14, 0.37, -0.37), fingers=(-0.2, 0.8, 0.55), palm=(-0.7, -0.1, -0.5), pose="CIG_V"),
            REST(7.0),
        ]},
        props={"R": ("CIGARETTE", "CIG_V")},
        head=[(0.0, 0, 0), (1.5, 0, -6), (3.0, 0, -6), (3.6, 4, 6), (4.6, 4, 6), (5.4, 0, -4), (7.0, 0, 0)],
        events=[(1.9, "CIGARETTE", "ember", 0.15), (2.2, "CIGARETTE", "ember", 1.0), (2.9, "CIGARETTE", "ember", 1.0),
                (3.4, "CIGARETTE", "ember", 0.15), (3.7, "SMOKE", "puff", 1.0)],
        loop=(1.0, 5.5), default_duration=9.0),

    Clip(
        "PHONE", "Check Phone", "Take out a phone, look down at it and scroll with the thumb",
        "MOD_PHYSICS", "HABITS", 7.0,
        hands={"L": [
            REST(0.0),
            Key(1.1, (-0.05, 0.33, -0.31),
                fingers=(0.95, 0.15, 0.25), palm=(0.1, -0.7, 0.7), pose="PHONE", elbow=(-0.5, -0.3, -1.0)),
            Key(1.8, (-0.05, 0.33, -0.31),
                fingers=(0.95, 0.15, 0.25), palm=(0.1, -0.7, 0.7), pose="PHONE_TAP", elbow=(-0.5, -0.3, -1.0)),
            Key(2.4, (-0.05, 0.33, -0.31),
                fingers=(0.95, 0.15, 0.25), palm=(0.1, -0.7, 0.7), pose="PHONE", elbow=(-0.5, -0.3, -1.0)),
            Key(3.4, (-0.05, 0.335, -0.305),
                fingers=(0.95, 0.15, 0.25), palm=(0.1, -0.7, 0.7), pose="PHONE", elbow=(-0.5, -0.3, -1.0)),
            Key(4.0, (-0.05, 0.335, -0.305),
                fingers=(0.95, 0.15, 0.25), palm=(0.1, -0.7, 0.7), pose="PHONE_TAP", elbow=(-0.5, -0.3, -1.0)),
            Key(4.6, (-0.05, 0.33, -0.31),
                fingers=(0.95, 0.15, 0.25), palm=(0.1, -0.7, 0.7), pose="PHONE", elbow=(-0.5, -0.3, -1.0)),
            Key(6.0, (-0.05, 0.33, -0.31),
                fingers=(0.95, 0.15, 0.25), palm=(0.1, -0.7, 0.7), pose="PHONE", elbow=(-0.5, -0.3, -1.0)),
            REST(7.0),
        ]},
        props={"L": ("PHONE", "PHONE")},
        head=[(0.0, 0, 0), (1.0, 4, -30), (6.0, 4, -30), (7.0, 0, 0)],
        events=[(1.0, "PHONE", "screen", 0.0), (1.3, "PHONE", "screen", 1.0), (6.0, "PHONE", "screen", 1.0),
                (6.4, "PHONE", "screen", 0.0)],
        loop=(1.8, 4.6), default_duration=8.0),

    Clip(
        "COFFEE", "Sip Coffee", "Raise a to-go cup, take a sip, lower it",
        "OUTLINER_OB_FORCE_FIELD", "HABITS", 6.0,
        hands={"R": [
            REST(0.0),
            Key(1.0, (0.13, 0.33, -0.40), fingers=(-0.3, 0.95, 0.0), palm=(-0.95, -0.3, 0.0), pose="CUP"),
            Key(1.9, None, fingers=(-0.85, 0.42, 0.32), palm=(-0.53, -0.68, -0.51), pose="CUP", prop_to=MOUTH,
                elbow=(0.8, -0.2, -0.8)),
            Key(3.0, None, fingers=(-0.83, 0.33, 0.44), palm=(-0.55, -0.5, -0.66), pose="CUP", prop_to=MOUTH,
                elbow=(0.8, -0.2, -0.8)),
            Key(3.9, (0.13, 0.34, -0.39), fingers=(-0.3, 0.95, 0.0), palm=(-0.95, -0.3, 0.0), pose="CUP"),
            Key(4.8, (0.13, 0.34, -0.39), fingers=(-0.3, 0.95, 0.0), palm=(-0.95, -0.3, 0.0), pose="CUP"),
            REST(6.0),
        ]},
        props={"R": ("CUP", "CUP")},
        head=[(0.0, 0, 0), (1.6, 0, -4), (2.2, 0, 10), (3.0, 0, 10), (3.8, 0, -6), (6.0, 0, 0)],
        loop=(1.0, 4.8), default_duration=6.0),

    Clip(
        "WATCH", "Check Watch", "Raise the left wrist and glance at the watch",
        "TIME", "HABITS", 3.6,
        hands={"L": [
            REST(0.0),
            Key(0.9, (-0.06, 0.36, -0.32), fingers=(0.95, 0.25, 0.1), palm=(0.0, 0.25, -0.97), pose="LOOSE_FIST",
                elbow=(-0.8, -0.2, -1.0)),
            Key(2.5, (-0.06, 0.36, -0.32), fingers=(0.95, 0.25, 0.1), palm=(0.0, 0.25, -0.97), pose="LOOSE_FIST",
                elbow=(-0.8, -0.2, -1.0)),
            REST(3.6),
        ]},
        head=[(0.0, 0, 0), (0.8, -6, -30), (2.6, -6, -30), (3.4, 0, 0)],
        loop=(0.9, 2.5), default_duration=3.6),

    Clip(
        "FLASHLIGHT", "Flashlight", "Hold a flashlight out in front, lighting the way",
        "LIGHT_SPOT", "EXPLORE", 8.0,
        hands={"R": [
            REST(0.0),
            Key(1.0, (0.13, 0.40, -0.33), fingers=(-0.15, 0.80, -0.58), palm=(-0.98, 0.0, -0.2), pose="TUBE",
                elbow=(0.6, -0.3, -1.0)),
            Key(3.5, (0.11, 0.41, -0.32), fingers=(-0.30, 0.76, -0.58), palm=(-0.95, -0.15, -0.2), pose="TUBE"),
            Key(5.5, (0.15, 0.40, -0.33), fingers=(0.05, 0.80, -0.58), palm=(-0.98, 0.1, -0.2), pose="TUBE"),
            Key(7.0, (0.13, 0.40, -0.33), fingers=(-0.15, 0.80, -0.58), palm=(-0.98, 0.0, -0.2), pose="TUBE"),
            REST(8.0),
        ]},
        props={"R": ("FLASHLIGHT", "TUBE")},
        events=[(1.0, "FLASHLIGHT", "light", 0.0), (1.2, "FLASHLIGHT", "light", 1.0),
                (7.1, "FLASHLIGHT", "light", 1.0), (7.3, "FLASHLIGHT", "light", 0.0)],
        loop=(1.0, 7.0), default_duration=10.0),

    Clip(
        "WAVE", "Wave Hello", "Raise the right hand and wave",
        "HAND", "GESTURES", 3.2,
        hands={"R": [
            REST(0.0),
            Key(0.7, (0.22, 0.42, -0.10), fingers=(0.05, 0.1, 1.0), palm=(0.0, 1.0, 0.0), pose="OPEN",
                elbow=(1.0, 0.0, -0.6)),
            Key(1.0, (0.25, 0.42, -0.09), fingers=(0.35, 0.1, 0.94), palm=(0.0, 1.0, 0.0), pose="OPEN",
                elbow=(1.0, 0.0, -0.6)),
            Key(1.3, (0.20, 0.42, -0.09), fingers=(-0.3, 0.1, 0.95), palm=(0.0, 1.0, 0.0), pose="OPEN",
                elbow=(1.0, 0.0, -0.6)),
            Key(1.6, (0.25, 0.42, -0.09), fingers=(0.35, 0.1, 0.94), palm=(0.0, 1.0, 0.0), pose="OPEN",
                elbow=(1.0, 0.0, -0.6)),
            Key(1.9, (0.20, 0.42, -0.09), fingers=(-0.3, 0.1, 0.95), palm=(0.0, 1.0, 0.0), pose="OPEN",
                elbow=(1.0, 0.0, -0.6)),
            Key(2.2, (0.22, 0.42, -0.10), fingers=(0.05, 0.1, 1.0), palm=(0.0, 1.0, 0.0), pose="OPEN",
                elbow=(1.0, 0.0, -0.6)),
            REST(3.2),
        ]},
        loop=(1.0, 1.6), default_duration=3.2),

    Clip(
        "REACH", "Reach Out and Touch", "Stretch a hand out and touch what is in front",
        "VIEW_PAN", "EXPLORE", 3.4,
        hands={"R": [
            REST(0.0),
            Key(0.9, (0.12, 0.50, -0.20), fingers=(-0.15, 1.0, 0.25), palm=(-0.1, 0.3, -0.95), pose="RELAXED",
                elbow=(0.7, -0.2, -1.0)),
            Key(1.5, (0.10, 0.58, -0.16), fingers=(-0.1, 0.55, 0.85), palm=(0.0, 1.0, -0.2), pose="FLAT",
                elbow=(0.7, -0.2, -1.0)),
            Key(2.3, (0.10, 0.585, -0.16), fingers=(-0.1, 0.5, 0.86), palm=(0.0, 1.0, -0.2), pose="FLAT",
                elbow=(0.7, -0.2, -1.0)),
            REST(3.4),
        ]},
        head=[(0.0, 0, 0), (1.0, 0, -4), (2.4, 0, -4), (3.4, 0, 0)],
        loop=(1.5, 2.3), default_duration=3.4),

    Clip(
        "POINT", "Point Ahead", "Point at something ahead",
        "FORWARD", "GESTURES", 2.8,
        hands={"R": [
            REST(0.0),
            Key(0.8, (0.14, 0.50, -0.20), fingers=(-0.2, 1.0, 0.15), palm=(-0.75, 0.0, -0.66), pose="POINT",
                elbow=(0.7, -0.2, -1.0)),
            Key(1.9, (0.14, 0.51, -0.19), fingers=(-0.2, 1.0, 0.18), palm=(-0.75, 0.0, -0.66), pose="POINT",
                elbow=(0.7, -0.2, -1.0)),
            REST(2.8),
        ]},
        loop=(0.8, 1.9), default_duration=2.8),

    Clip(
        "WARM_HANDS", "Warm Hands", "Rub the hands together and blow into them",
        "FREEZE", "HABITS", 5.0,
        hands={"R": [
            REST(0.0),
            Key(0.9, (0.032, 0.33, -0.33), fingers=(0.0, 0.45, 0.9), palm=(-1.0, 0.0, 0.0), pose="FLAT",
                elbow=(0.7, -0.3, -1.0)),
            Key(1.2, (0.032, 0.34, -0.30), fingers=(0.0, 0.45, 0.9), palm=(-1.0, 0.0, 0.0), pose="FLAT"),
            Key(1.5, (0.032, 0.32, -0.34), fingers=(0.0, 0.45, 0.9), palm=(-1.0, 0.0, 0.0), pose="FLAT"),
            Key(1.8, (0.032, 0.34, -0.30), fingers=(0.0, 0.45, 0.9), palm=(-1.0, 0.0, 0.0), pose="FLAT"),
            Key(2.1, (0.032, 0.32, -0.34), fingers=(0.0, 0.45, 0.9), palm=(-1.0, 0.0, 0.0), pose="FLAT"),
            Key(2.8, (0.035, 0.15, -0.20), fingers=(-0.15, 0.25, 0.96), palm=(-0.7, -0.7, 0.1), pose="CUPPED",
                elbow=(0.7, -0.4, -1.0)),
            Key(3.9, (0.035, 0.15, -0.20), fingers=(-0.15, 0.25, 0.96), palm=(-0.7, -0.7, 0.1), pose="CUPPED",
                elbow=(0.7, -0.4, -1.0)),
            REST(5.0),
        ], "L": [
            REST(0.0),
            Key(0.9, (-0.032, 0.33, -0.33), fingers=(0.0, 0.45, 0.9), palm=(1.0, 0.0, 0.0), pose="FLAT",
                elbow=(-0.7, -0.3, -1.0)),
            Key(1.2, (-0.032, 0.32, -0.34), fingers=(0.0, 0.45, 0.9), palm=(1.0, 0.0, 0.0), pose="FLAT"),
            Key(1.5, (-0.032, 0.34, -0.30), fingers=(0.0, 0.45, 0.9), palm=(1.0, 0.0, 0.0), pose="FLAT"),
            Key(1.8, (-0.032, 0.32, -0.34), fingers=(0.0, 0.45, 0.9), palm=(1.0, 0.0, 0.0), pose="FLAT"),
            Key(2.1, (-0.032, 0.34, -0.30), fingers=(0.0, 0.45, 0.9), palm=(1.0, 0.0, 0.0), pose="FLAT"),
            Key(2.8, (-0.035, 0.15, -0.20), fingers=(0.15, 0.25, 0.96), palm=(0.7, -0.7, 0.1), pose="CUPPED",
                elbow=(-0.7, -0.4, -1.0)),
            Key(3.9, (-0.035, 0.15, -0.20), fingers=(0.15, 0.25, 0.96), palm=(0.7, -0.7, 0.1), pose="CUPPED",
                elbow=(-0.7, -0.4, -1.0)),
            REST(5.0),
        ]},
        head=[(0.0, 0, 0), (0.8, 0, -28), (2.3, 0, -28), (2.8, 0, -8), (3.9, 0, -8), (5.0, 0, 0)],
        events=[(3.0, "SMOKE", "breath", 1.0)],
        loop=(1.2, 2.1), default_duration=5.0),

    Clip(
        "SHIELD_EYES", "Shield Eyes", "Raise a hand to the brow against the sun and look into the distance",
        "LIGHT_SUN", "EXPLORE", 4.0,
        hands={"R": [
            REST(0.0),
            Key(1.0, (0.11, 0.11, 0.085), fingers=(-0.92, 0.3, 0.1), palm=(0.05, -0.25, -0.97), pose="FLAT",
                head=True, elbow=(1.0, 0.1, -0.5)),
            Key(3.0, (0.11, 0.11, 0.085), fingers=(-0.92, 0.3, 0.1), palm=(0.05, -0.25, -0.97), pose="FLAT",
                head=True, elbow=(1.0, 0.1, -0.5)),
            REST(4.0),
        ]},
        head=[(0.0, 0, 0), (1.0, 0, 4), (2.0, 12, 4), (3.0, -6, 4), (4.0, 0, 0)],
        loop=(1.0, 3.0), default_duration=4.0),

    Clip(
        "LOOK_HANDS", "Look at Hands", "Raise both hands and look at them",
        "VIEW_CAMERA", "GESTURES", 4.5,
        hands={"R": [
            REST(0.0),
            Key(1.1, (0.12, 0.36, -0.30), fingers=(-0.25, 0.6, 0.75), palm=(-0.2, -0.55, -0.8), pose="RELAXED"),
            Key(2.2, (0.12, 0.36, -0.30), fingers=(-0.3, 0.55, 0.78), palm=(-0.5, 0.8, 0.2), pose="RELAXED"),
            Key(3.3, (0.12, 0.36, -0.30), fingers=(-0.25, 0.6, 0.75), palm=(-0.2, -0.55, -0.8), pose="OPEN"),
            REST(4.5),
        ], "L": [
            REST(0.0),
            Key(1.1, (-0.12, 0.36, -0.30), fingers=(0.25, 0.6, 0.75), palm=(0.2, -0.55, -0.8), pose="RELAXED",
                elbow=(-0.6, -0.3, -1.0)),
            Key(2.2, (-0.12, 0.36, -0.30), fingers=(0.3, 0.55, 0.78), palm=(0.5, 0.8, 0.2), pose="RELAXED",
                elbow=(-0.6, -0.3, -1.0)),
            Key(3.3, (-0.12, 0.36, -0.30), fingers=(0.25, 0.6, 0.75), palm=(0.2, -0.55, -0.8), pose="OPEN",
                elbow=(-0.6, -0.3, -1.0)),
            REST(4.5),
        ]},
        head=[(0.0, 0, 0), (1.0, 0, -24), (3.4, 0, -24), (4.5, 0, 0)],
        loop=(1.1, 3.3), default_duration=4.5),

    Clip(
        "THUMBS_UP", "Thumbs Up", "Give a thumbs up",
        "CHECKMARK", "GESTURES", 2.6,
        hands={"R": [
            REST(0.0),
            Key(0.8, (0.12, 0.42, -0.25), fingers=(-0.2, 0.95, 0.25), palm=(-0.95, 0.1, 0.25), pose="THUMBS_UP",
                elbow=(0.7, -0.2, -1.0)),
            Key(1.8, (0.12, 0.42, -0.245), fingers=(-0.2, 0.95, 0.25), palm=(-0.95, 0.1, 0.25), pose="THUMBS_UP",
                elbow=(0.7, -0.2, -1.0)),
            REST(2.6),
        ]},
        loop=(0.8, 1.8), default_duration=2.6),

    Clip(
        "DRINK", "Drink from Bottle", "Unscrewed bottle up to the mouth, a long drink, down again",
        "MOD_FLUID", "HABITS", 5.5,
        hands={"R": [
            REST(0.0),
            Key(1.0, (0.13, 0.34, -0.40), fingers=(-0.3, 0.95, 0.0), palm=(-0.95, -0.3, 0.0), pose="BOTTLE"),
            Key(1.9, None, fingers=(-0.83, 0.33, 0.44), palm=(-0.55, -0.5, -0.66), pose="BOTTLE", prop_to=MOUTH,
                elbow=(0.8, -0.1, -0.8)),
            Key(3.4, None, fingers=(-0.8, 0.12, 0.58), palm=(-0.58, -0.3, -0.76), pose="BOTTLE", prop_to=MOUTH,
                elbow=(0.8, -0.1, -0.8)),
            Key(4.3, (0.13, 0.34, -0.40), fingers=(-0.3, 0.95, 0.0), palm=(-0.95, -0.3, 0.0), pose="BOTTLE"),
            REST(5.5),
        ]},
        props={"R": ("BOTTLE", "BOTTLE")},
        head=[(0.0, 0, 0), (1.6, 0, -2), (2.4, 0, 22), (3.4, 0, 24), (4.2, 0, -4), (5.5, 0, 0)],
        loop=(1.0, 4.3), default_duration=5.5),
]

CLIP_BY_ID = {c.id: c for c in CLIPS}
_items = []


def enum_items():
    if not _items:
        _items.extend((c.id, c.label, c.description, c.icon, i) for i, c in enumerate(CLIPS))
    return _items


def expand(clip, duration):
    """Key times for one use of a clip lasting ``duration`` seconds.

    Returns (scale, cycles): the loop span repeats ``cycles`` extra times and
    every time is then multiplied by ``scale``.
    """
    cycles = 0
    if clip.loop is not None and duration > clip.length:
        span = clip.loop[1] - clip.loop[0]
        cycles = max(0, int(round((duration - clip.length) / span)))
    total = clip.length + (clip.loop[1] - clip.loop[0]) * cycles if clip.loop else clip.length
    return duration / total, cycles


def warp(clip, t_local, duration):
    """Map a time within one use of the clip back to the clip's own key time."""
    scale, cycles = expand(clip, duration)
    t = t_local / scale
    if clip.loop is None or cycles == 0:
        return t
    t0, t1 = clip.loop
    span = t1 - t0
    if t <= t1:
        return t
    extra = t - t1
    if extra < span * cycles:
        return t0 + (extra % span)
    return t - span * cycles
