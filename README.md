## Installation

You'll need `credentials.json` from your Google account.  You can get this
by enabling the Google Drive API on your account.  Follow the
[Google Drive API v3 Quickstart][].

    python3 -m venv $PWD/google-api
    source google-api/bin/activate
    pip install -r requirements.txt 

[Google Drive API v3 Quickstart]: https://developers.google.com/drive/api/v3/quickstart/python

## Usage

    ./run_backups.sh

## Testing

To test the `backup_mud.py` script, just pass it a non-production backup folder
name:

    ./backup_mud.py --token-file ./token.pickle \
            --client-secrets ./credentials.json \
            --backup-dir "testdir" \
            --backup-prefix "mud_1316" \
            --keep-old 3 \
            $HOME/1316

You will still have to `source google-api/bin/activate` first.
