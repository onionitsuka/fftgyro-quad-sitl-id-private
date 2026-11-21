#!/usr/bin/env bash
set -euo pipefail
source "$(dirname "$0")/env.sh"
root="$HAKO_DESKTOP_ROOT"
build="$root/core-build"
cmake -S "$root/hakoniwa-core-pro" -B "$build" \
  -DCMAKE_BUILD_TYPE=Release \
  -DHAKO_ENABLE_GTEST=OFF -DHAKO_CORE_PRO_BUILD_PYTHON_BINDINGS=OFF \
  -DHAKO_CORE_PRO_BUILD_EXAMPLES=OFF
cmake --build "$build" -j 6
mkdir -p "$root/lib"
cc -shared -fPIC -O2 "$(dirname "$0")/tcp-nodelay.c" -o "$root/lib/libsitl_tcp_nodelay.so" -ldl
for name in assets shakoc conductor; do
  target=$(find "$build" -name "lib${name}.so.1.0.0" -print -quit)
  test -n "$target"
  ln -sfn "$target" "$root/lib/lib${name}.so.1"
  ln -sfn "$target" "$root/lib/lib${name}.so"
done
ldd "$root/runtime-v5.0.0/lnx/linux-main_hako_aircraft_service_px4"
