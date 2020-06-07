#!/usr/bin/env python3
"""Creates and uploads backups of the different MUD ports to Google Drive.

See <https://developers.google.com/drive/api/v3/reference/files/> for
information on this API.
"""
import os
import tarfile
import argparse
import datetime
import pickle

import googleapiclient.discovery
import googleapiclient.http
import google_auth_oauthlib.flow
import google.auth.transport.requests

SCOPES = ['https://www.googleapis.com/auth/drive']
BACKUP_DIR = "Mud Backups"

def filter_mud_tarfile(tarinfo):
    basename = os.path.basename(tarinfo.name)
    if tarinfo.name.endswith('.o') \
    or os.sep + ".git" in tarinfo.name \
    or basename == "rom" \
    or basename == "core" \
    or basename.startswith("core.") \
    or basename.endswith(".log") \
    or basename.endswith(".bak"):
        return None
    return tarinfo

def get_credentials(client_secrets_file, token_file, scopes=SCOPES):
    creds = None
    if os.path.exists(token_file):
        with open(token_file, 'rb') as token:
            creds = pickle.load(token)

    # If there are no (valid) credentials available, let the user log in.
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(google.auth.transport.requests.Request())
        else:
            flow = google_auth_oauthlib.flow.InstalledAppFlow.from_client_secrets_file(
                client_secrets_file, scopes)
            creds = flow.run_local_server(port=0)

        # Save the credentials for the next run
        with open(token_file, 'wb') as token:
            pickle.dump(creds, token)

    return creds

def tar_directory(input_dir, output_file):
    with tarfile.open(output_file, "w:xz") as tar:
        tar.add(input_dir, filter=filter_mud_tarfile )

def find_deletion_candidates(file_list, filename_prefix, max_keep=4):
    matching_files = []
    for file_entry in file_list:
        if file_entry.get('name').startswith(filename_prefix):
            matching_files.append(file_entry)

    if len(matching_files) <= max_keep:
        return []
    return matching_files[:-max_keep]

class BackerUpper(object):
    def __init__(self, client_secrets, token_file):
        creds = get_credentials(client_secrets_file=client_secrets, token_file=token_file)
        self.service = googleapiclient.discovery.build('drive', 'v3', credentials=creds)

    def find_matching_folders(self, folder_name):
        query_str = "mimeType='application/vnd.google-apps.folder' and name='%s' and trashed = false" % folder_name
        return self.query_files(query_str)

    def find_files_in_folder(self, folder_id):
        query_str = "parents in '%s' and trashed = false" % folder_id
        return self.query_files(query_str)

    def init_backup_folder(self, backup_dir):
        # find the parent folder if it exists
        backup_dirs = self.find_matching_folders(backup_dir)
        if not backup_dirs:
            results = self.service.files().create(body={
                    "name": backup_dir,
                    "mimeType": "application/vnd.google-apps.folder"
                },
                fields="id").execute()
            parent_folder_id = results.get("id")
            print("Created new backup directory %s" % parent_folder_id)
            return parent_folder_id

        parent_folder_id = backup_dirs[0].get('id')
        print("Found existing backup directory %s" % parent_folder_id)
        return parent_folder_id

    def delete_files(self, file_list, trash=True):
        """Deletes files
        Args:
            trash (bool): Moves file into trash rather than permanently deleting
                unless trash=False
        """
        deleted = []
        for file_entry in file_list:
            if trash:
                print("Trashing old backup %s created on %s" % (file_entry.get('name'), file_entry.get('createdTime')))
                self.service.files().update(
                    fileId=file_entry.get('id'),
                    body={"trashed": True}).execute()
            else:
                print("Deleting old backup %s created on %s" % (file_entry.get('name'), file_entry.get('createdTime')))
                self.service.files().delete(
                    fileId=file_entry.get('id')).execute()

    def query_files(self, query_str):
        page_token = None
        matches = []
        while True:
            # See https://developers.google.com/drive/api/v3/ref-search-terms
            results = self.service.files().list(
                q=query_str,
                spaces='drive',
                fields='nextPageToken, files(id, name, createdTime)',
                pageToken=page_token,
                orderBy="createdTime").execute()
            for filename in results.get('files', []):
                matches.append(filename)
            page_token = results.get('nextPageToken')
            if page_token is None:
                break
        return matches

    def upload_file(self, local_file_path, parent_folder_id=None):
        body = {
            "name": os.path.basename(local_file_path),
            "mimeType": "application/octet-stream",
        }
        if parent_folder_id:
            body["parents"] = [parent_folder_id]

        # upload the file to the directory
        results = self.service.files().create(
            body=body,
            media_body=local_file_path,
            fields='id').execute()

        return results

def main(argv=None):
    """Shows basic usage of the Drive v3 API.
    Prints the names and ids of the first 10 files the user has access to.
    """

    parser = argparse.ArgumentParser()
    parser.add_argument("-p", "--backup-prefix", type=str, default=None,
        help="Prefix for backup file names")
    parser.add_argument("-k", "--keep-old", type=int, default=4,
        help="Number of old backups to keep on GDrive with the same --backup-prefix")
    parser.add_argument("--token-file", type=str, default='token.pickle',
        help="Path to cached GDrive API credentials (default: token.pickle)")
    parser.add_argument("--client-secrets", type=str, default="credentials.json",
        help="Path to client secrets/credentials json (default: credentials.json)")
    parser.add_argument("--backup-dir", type=str, default=BACKUP_DIR,
        help="Name of top-level subdirectory into which MUD backups should be stored on GDrive (default: %s)" % BACKUP_DIR)
    parser.add_argument("directory", type=str,
        help="Directory to back up")
    parser.add_argument("--dry-run", action='store_true',
        help="Do not actually create, upload, or delete any backups")
    args = parser.parse_args(argv)

    backup_prefix = args.backup_prefix
    if not args.backup_prefix:
        backup_prefix = os.path.basename(args.directory.rstrip(os.sep))

    backup_maker = BackerUpper(client_secrets=args.client_secrets, token_file=args.token_file)

    # make the parent folder if it does not exist
    parent_folder_id = backup_maker.init_backup_folder(args.backup_dir)

    # find old tarfiles
    old_files = backup_maker.find_files_in_folder(parent_folder_id)
    delete_list = find_deletion_candidates(old_files, '%s_' % backup_prefix, max_keep=args.keep_old)
    if not args.dry_run:
        backup_maker.delete_files(delete_list, trash=False)

    # create backup tarfile
    tarfile = datetime.datetime.now().strftime("%s_%%Y-%%m-%%d.tar.xz" % backup_prefix)
    if not args.dry_run:
        tar_directory(args.directory, tarfile)

    # upload backup tarfile
    if not args.dry_run:
        results = backup_maker.upload_file(tarfile, parent_folder_id)
        print("Uploaded %s as file id %s" % (tarfile, results.get("id")))
    else:
        print("Uploaded %s" % (tarfile))

    # don't keep local copy of tarfile
    if not args.dry_run:
        os.unlink(tarfile)

if __name__ == '__main__':
    main()
