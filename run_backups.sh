#!/usr/bin/env bash
#
# Wrapper for backup_mud.py.  Insert into crontab, e.g.,
#
#     @daily source /home/mud/backup/google-api/bin/activate && /home/mud/backup/run_backups.sh
#

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
	${port} | gawk '{ print strftime("[%Y-%m-%d %H:%M:%S]"), $0 }' >> "${HERE}/backups.log"
done
