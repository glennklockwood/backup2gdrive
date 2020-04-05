#!/usr/bin/env bash

HERE=$(dirname $(readlink -f ${BASH_SOURCE[0]}))
MUD_ROOT=$HOME

for port in 1313 1314 1316
do
    cd "$MUD_ROOT" && \
    ${HERE}/backup_mud.py \
        --token-file "${HERE}/token.pickle" \
	--client-secrets "${HERE}/credentials.json" \
	--backup-dir "Mud Backups" \
	--backup-prefix "mud_${port}" \
	${port} >> "${HERE}/backups.log"
done
