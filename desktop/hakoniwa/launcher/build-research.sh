#!/usr/bin/env bash
set -euo pipefail
source "$(dirname "$0")/env.sh"
root="$HAKO_DESKTOP_ROOT"
cc -O2 -fPIC -c "$(dirname "$0")/physics_bridge.c" -I "$root/hakoniwa-drone-core/include" -o "$root/lib/physics_bridge.o"
c++ -shared "$root/lib/physics_bridge.o" "$root/runtime-v5.0.0/lnx/libdrone_physics_c.a" "$root/runtime-v5.0.0/lnx/libdrone_physics.a" -o "$root/lib/libphysics_bridge.so"
