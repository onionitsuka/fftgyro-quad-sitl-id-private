#!/usr/bin/env bash
set -euo pipefail
source "$(dirname "$0")/env.sh"
root="$HAKO_DESKTOP_ROOT"
project="$root/hakoniwa-unity-drone/simulation"
editor="${UNITY_EDITOR:-$HOME/Unity/Hub/Editor/6000.3.10f1/Editor/Unity}"
mkdir -p "$project/Assets/Editor" "$root/Build"
cp "$(dirname "$0")/LocalOfficialLinux.cs" "$project/Assets/Editor/LocalOfficialLinux.cs"
python3 "$(dirname "$0")/prepare-desktop-packages.py"
build() {
  "$editor" -batchmode -nographics -quit -projectPath "$project" -buildTarget Linux64 \
    -executeMethod LocalOfficialLinux.Build -logFile "$root/avatar-build.log"
}
if ! build; then
  if grep -q 'OVRManagerEditor.cs.*error CS0103' "$root/avatar-build.log"; then
    cp "$root/avatar-build.log" "$root/avatar-build-before-meta-fix.log"
    python3 "$(dirname "$0")/patch-meta-linux.py"
    build
  else
    exit 1
  fi
fi
# Unity's bundled core uses a different lock protocol. Match the launcher core.
test -f "$root/lib/libshakoc.so"
cp -L "$root/lib/libshakoc.so" "$root/Build/Hakoniwa_Data/Plugins/libshakoc.so"
for file in drone-pdudef-1.json drone-pdutypes.json drone_config.json monitor_camera_config.json; do
  cp "$project/$file" "$root/Build/$file"
done
cp -R "$project/ros_types" "$root/Build/"
echo "Built: $root/Build/Hakoniwa.x86_64"
