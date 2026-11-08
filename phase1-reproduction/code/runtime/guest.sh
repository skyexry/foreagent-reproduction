#!/bin/bash
# Reuse the pinned root filesystem and inject only the instance's NVIDIA driver.
set -euo pipefail
base=/root/autodl-tmp/foreagent
rootfs=$base/author-bundle/rootfs
runtime=$base/runtime
scope=${1:?run name}
shift
[[ "$scope" =~ ^[a-z0-9-]+$ ]] || exit 2
work=$runtime/$scope
mkdir -p "$work/jobs"
install -d -o foreagentx -g foreagentx "$work/workspace" "$work/tmp" "$work/home"
setpriv --reuid=foreagentx --regid=foreagentx --clear-groups --no-new-privs bash -c '
  mkdir -p "$1/workspace/working" "$1/workspace/submission" "$1/workspace/best_submission" "$1/workspace/best_solution" "$1/workspace/all_nodes"
  if [ ! -e "$1/workspace/input" ] && [ ! -L "$1/workspace/input" ]; then ln -s /home/data "$1/workspace/input"; fi' _ "$work"
mkdir -p "$runtime/driver"
for lib in /usr/lib/x86_64-linux-gnu/libcuda.so* /usr/lib/x86_64-linux-gnu/libnvidia-*.so*; do
    [[ -e "$lib" ]] || continue
    ln -sfn "/run/host-libs/$(basename "$lib")" "$runtime/driver/$(basename "$lib")"
done
binds=(-b /proc -b /sys -b /dev -b "$work/tmp:/tmp" -b "$work/home:/home/foreagentx" -b /etc/resolv.conf
       -b /usr/lib/x86_64-linux-gnu:/run/host-libs -b "$runtime/driver:/run/driver"
       -b /usr/bin/nvidia-smi:/usr/bin/nvidia-smi -b "$base/preflight/task:/home/data"
       -b "$base/preflight/upstream/mle-bench/agents/aide:/home/agent"
       -b "$work/workspace:/home/agent/workspaces/exp" -b "$work/jobs:/jobs"
       -b "$work/workspace/best_submission:/home/submission" -b "$work/workspace/best_solution:/home/code"
       -b "$runtime/worker.py:/worker.py")
exec setpriv --reuid=foreagentx --regid=foreagentx --clear-groups --no-new-privs env -i HOME=/home/foreagentx USER=foreagentx LANG=C.UTF-8 PATH=/opt/conda/envs/agent/bin:/opt/conda/bin:/usr/bin:/bin \
    PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=/home/agent LD_LIBRARY_PATH=/run/driver \
    CONDA_DEFAULT_ENV=agent CONDA_PREFIX=/opt/conda/envs/agent HF_ENDPOINT=https://hf-mirror.com/ \
    AGENT_DIR=/home/agent CODE_DIR=/home/code LOGS_DIR=/home/logs SUBMISSION_DIR=/home/submission \
    COMPETITION_ID=stanford-covid-vaccine STEP_LIMIT=5000 TIME_LIMIT_SECS=43200 \
    /usr/bin/proot -r "$rootfs" "${binds[@]}" -w /home/agent/workspaces/exp "$@"
