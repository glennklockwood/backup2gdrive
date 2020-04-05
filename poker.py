#!/usr/bin/env python3
import os
import tarfile
import datetime
import pickle

import googleapiclient.discovery
import googleapiclient.http
import google_auth_oauthlib.flow
import google.auth.transport.requests


# If modifying these scopes, delete the file token.pickle.
SCOPES = ['https://www.googleapis.com/auth/drive']

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

def get_credentials(client_secrets_file='credentials.json', token_file='token.pickle', scopes=SCOPES):
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

def find_matching_folders(service, folder_name):
    query_str = "mimeType='application/vnd.google-apps.folder' and name='%s' and trashed = false" % folder_name
    return query_files(service, query_str)

def find_files_in_folder(service, folder_id):
    query_str = "parents in '%s' and trashed = false" % folder_id
    return query_files(service, query_str)

def query_files(service, query_str):
    page_token = None
    matches = []
    while True:
        # See https://developers.google.com/drive/api/v3/ref-search-terms
        results = service.files().list(
            q=query_str,
            spaces='drive',
            fields='nextPageToken, files(id, name)',
            pageToken=page_token).execute()
        for filename in results.get('files', []):
            matches.append(filename)
        page_token = results.get('nextPageToken')
        if page_token is None:
            break
    return matches

def upload_file(service, local_file_path, parent_folder_id=None):
    body = {
        "name": os.path.basename(local_file_path),
        "mimeType": "application/octet-stream",
    }
    if parent_folder_id:
        body["parents"] = [parent_folder_id]

    # upload the file to the directory
    results = service.files().create(
        body=body,
        media_body=local_file,
        fields='id').execute()

    return results

def tar_directory(input_dir, output_file):

    with tarfile.open(output_file, "w:xz") as tar:
        tar.add(input_dir, filter=filter_mud_tarfile )
        

def main():
    """Shows basic usage of the Drive v3 API.
    Prints the names and ids of the first 10 files the user has access to.
    """
    local_file = "testfile.bin"
    backup_dir = "Mud Backups"

    creds = get_credentials()

    service = googleapiclient.discovery.build('drive', 'v3', credentials=creds)

    # find the parent folder if it exists
    backup_dirs = find_matching_folders(service, backup_dir)

    # make the parent folder if it does not exist
    if not backup_dirs:
        results = service.files().create(body={
                "name": backup_dir,
                "mimeType": "application/vnd.google-apps.folder"
            },
            fields="id").execute()
        parent_folder_id = results.get("id")
        print("Created new backup directory %s" % parent_folder_id)
    else:
        parent_folder_id = backup_dirs[0].get('id')
        print("Found existing backup directory %s" % parent_folder_id)

    old_files = find_files_in_folder(service, parent_folder_id)
    print(old_files)

    output_file = datetime.datetime.now().strftime("mud_1316_%Y-%m-%d.tar.xz")
    tar_directory('1316', output_file)

#   results = upload_file(service, local_file, parent_folder_id)
#   print("Uploaded %s as file id %s" % (local_file, results.get("id")))

if __name__ == '__main__':
    main()
