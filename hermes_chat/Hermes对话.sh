#!/bin/bash

progdir="$(cd "$(dirname "$0")" || exit; pwd)"

export PYSDL2_DLL_PATH="/usr/lib"

program="python3 ${progdir}/hermes_chat/main.py"
log_file="${progdir}/hermes_chat/log.txt"

[ -f /mnt/mod/ctrl/volumeCtrl.dge ] && /mnt/mod/ctrl/volumeCtrl.dge &

$program > "$log_file" 2>&1

kill -9 $(pidof volumeCtrl.dge) 2>/dev/null

exit 0
