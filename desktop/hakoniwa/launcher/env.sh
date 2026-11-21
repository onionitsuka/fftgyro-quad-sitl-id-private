#!/usr/bin/env bash
export HAKO_DESKTOP_ROOT="${HAKO_DESKTOP_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
export HAKO_CONFIG_PATH="$HAKO_DESKTOP_ROOT/cpp_core_config.json"
export LD_LIBRARY_PATH="$HAKO_DESKTOP_ROOT/lib:$HAKO_DESKTOP_ROOT/runtime-v5.0.0/lnx:$HAKO_DESKTOP_ROOT/dependencies/root/usr/lib/x86_64-linux-gnu${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
if [[ "${HAKO_USE_NVIDIA:-1}" == 1 ]] && command -v nvidia-smi >/dev/null && nvidia-smi -L >/dev/null 2>&1; then
  export __NV_PRIME_RENDER_OFFLOAD=1
  export __GLX_VENDOR_LIBRARY_NAME=nvidia
fi

export HAKO_PYTHON="${HAKO_PYTHON:-$HAKO_DESKTOP_ROOT/.venv/bin/python}"
