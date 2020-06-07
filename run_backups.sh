#!/usr/bin/env bash
#
# Wrapper for backup_mud.py.  Insert into crontab, e.g.,
#
#     @daily source /home/mud/backup/google-api/bin/activate && /home/mud/backup/run_backups.sh
#

HERE=$(dirname $(readlink -f ${BASH_SOURCE[0]}))
MUD_ROOT=$HOME

for port in 1313 1314 1315 1316
do
    if [ ! -d "${port}" ]; then
	echo "Port ${port} does not exist; skipping" | gawk '{ print strftime("[%Y-%m-%d %H:%M:%S]"), $0 }' >> "${HERE}/backups.log"
    fi
    cd "$MUD_ROOT" && \
    ${HERE}/backup_mud.py \
        --token-file "${HERE}/token.pickle" \
	--client-secrets "${HERE}/credentials.json" \
	--backup-dir "Mud Backups" \
	--backup-prefix "mud_${port}" \
	--keep-policy-days 7 \
	--keep-policy-weeks 4 \
	--keep-policy-months 12 \
	--keep-policy-years 100 \
	${port} | gawk '{ print strftime("[%Y-%m-%d %H:%M:%S]"), $0 }' >> "${HERE}/backups.log"

    	# old policy was --keep-old 4
done
