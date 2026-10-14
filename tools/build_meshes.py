# SPDX-License-Identifier: GPL-3.0-or-later
"""Prebuild the arm and sleeve meshes into stride/data/ so 'Add Hands' is instant.

    python tools/build_meshes.py              # average build, every sleeve
    python tools/build_meshes.py --all        # every build

Needs numpy only (no Blender). Builds that aren't shipped are made on first
use inside Blender and cached in the user's folder.
"""

import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from stride import anatomy, handmesh  # noqa: E402

DATA = os.path.join(ROOT, "stride", "data")


def main():
    builds = list(anatomy.BUILDS) if "--all" in sys.argv else ["AVERAGE"]
    os.makedirs(DATA, exist_ok=True)
    for b in builds:
        t = time.time()
        handmesh.save(handmesh.build(b), os.path.join(DATA, f"arm_{b.lower()}.npz"))
        print(f"arm {b}: {time.time() - t:.1f}s")
        for kind in handmesh.SLEEVE_CUT:
            t = time.time()
            handmesh.save(handmesh.build_sleeve(b, kind), os.path.join(DATA, f"sleeve_{b.lower()}_{kind}.npz"))
            print(f"  sleeve {kind}: {time.time() - t:.1f}s")
    total = sum(os.path.getsize(os.path.join(DATA, f)) for f in os.listdir(DATA))
    print(f"data: {total / 1e6:.1f} MB")


if __name__ == "__main__":
    main()
