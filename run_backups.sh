#!/usr/bin/env bash

for port in 1313 1314 1316
do
    python3 poker.py --token-file token.pickle --client-secrets credentials.json --backup-dir "Mud Backups" --backup-prefix "mud_${port}" ${port} >> backups.log
done
