#!/usr/bin/env python3
"""Creates and uploads backups of the different MUD ports to Google Drive.

See <https://developers.google.com/drive/api/v3/reference/files/> for
information on this API.
"""
import os
import tarfile
import argparse
import datetime
import collections
import pickle

import dateutil.parser
import dateutil.relativedelta
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

def find_deletion_candidates(file_list, filename_prefix, max_keep=None, keep_policy=None):
    """Identifies files in backup that should be deleted.

    Args:
        file_list: Iterable with dict-like elements that contain the ``name``
            (filename) key.  If using ``keep_policy``, should also contain the
            ``createdTime`` key.
        filename_prefix (str): Only consider file entries in ``file_list`` whose
            ``name`` key begins with this string.
        max_keep (int or None): When specified, keep only this many of the last
            files in ``file_list``.  This implies that ``file_list`` is already
            sorted in some meaningful way (e.g., from oldest to newest)
        keep_policy (dict or None): When specified, should contain the keys
            ``days``, ``weeks``, ``months``, and/or ``years`` whose values are
            int that represent how many days/weeks/months/years should be
            represented in backups.  For example, if
            ``keep_policy={'years': 5}``, delete all backups more than 5 years
            old.  When multiple keys are specified, policies are additive; for
            example, ``keep_policy={'years': 5, 'months': 12}`` will keep one
            backup from each of the last five years __AND__ one backup from each
            of the last twelve months.  Note that this may result in six years
            and thirteen months of backups since the current month may also be
            included.  This parameter does nothing if ``max_keep`` is specified.

    Returns:
        list of the same type as ``file_list`` containing all the elements of
        ``file_list`` that should be deleted according to ``filename_prefix``,
        ``max_keep``, and ``keep_policy``.
    """
    def date_component(dtobj, component):
        if component == 'days':
            return dtobj.toordinal()
        if component == 'weeks':
            return dtobj.toordinal() // 7
        return getattr(dtobj, component[:-1])

    matching_files = []
    for file_entry in file_list:
        if file_entry.get('name').startswith(filename_prefix):
            matching_files.append(file_entry)

    # if max_keep, do not enforce a age-based retention policy and just bail here
    if max_keep:
        if len(matching_files) <= max_keep:
            return []
        return matching_files[:-max_keep]

    for matching_file in matching_files:
        if 'createdTime' in matching_file:
            # datetime.datetime.fromisoformat(matching_file.get('createdTime').replace("Z", "+00:00")) # Python 3.7+ only
            matching_file['created_datetime'] = dateutil.parser.isoparse(matching_file.get('createdTime'))

    if keep_policy:
        # order here matters - that way we are saving recent days before saving recent weeks
        _keep_policy = collections.OrderedDict()
        _keep_policy['days'] = keep_policy.get('days', 7) # keep up to 7 days of old logs
        _keep_policy['weeks'] = keep_policy.get('weeks', 0) # keep up to 4 weeks of old logs
        _keep_policy['months'] = keep_policy.get('months', 0) # keep up to 12 months of old logs
        _keep_policy['years'] = keep_policy.get('years', 0) # keep up to five years of old logs
    else:
        raise RuntimeError("must specify max_keep or keep_policy")

    grouped_by_time = {}
    for interval in _keep_policy:
        grouped_by_time[interval] = {}

    # hash every file by its day
    for matching_file in matching_files:
        created = matching_file.get('created_datetime')
        if not created:
            continue

        for interval in _keep_policy:
            if date_component(created, interval) not in grouped_by_time[interval]:
                grouped_by_time[interval][date_component(created, interval)] = []
            grouped_by_time[interval][date_component(created, interval)].append(matching_file)

    keep = {}
    for interval in _keep_policy: # interval = year, month, week, ...
        # **{interval: ...} is super hacky; safer thing to do is factor
        # out into a function that properly converts valid ``interval`` values
        # into proper dateutil.relativedelta.relativedelta() parameters
        window_start = datetime.datetime.now(datetime.timezone.utc) \
            - dateutil.relativedelta.relativedelta(**{interval: _keep_policy[interval]})

        for key in sorted(grouped_by_time[interval], reverse=True): # key = 2019, 2018, 2017, ...
            files_in_interval = sorted(grouped_by_time[interval][key], key=lambda x: x.get('created_datetime'), reverse=True)
            keep_file = files_in_interval[0]
            if keep_file.get('id') in keep:
                continue
            if keep_file['created_datetime'] > window_start:
                keep[keep_file.get('id')] = keep_file
                # why = "%s (%s > %s)" % (interval, str(keep_file['created_datetime']), str(window_start))
                # keep_file['why'] = keep_file['why'] + [why] if 'why' in keep_file else [why]
                # print("Keeping %s because of %s" % (keep_file['name'], why))
            else:
                print("Deleting %s because of %s (%s <= %s)" % (keep_file['name'], interval, keep_file['created_datetime'], window_start))

    return sorted([x for x in matching_files if x.get('id') not in keep], key=lambda x: x.get('created_datetime'), reverse=True)

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
            file_list: Any iterable whose elements are dict-like and have the
                ``id`` key defined.  Optionally, ``name`` and ``createdTime``
                keys can also be defined.
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

    # retention policy
    parser.add_argument("-k", "--keep-old", type=int, default=None,
            help="Number of old backups to keep on GDrive with the same --backup-prefix (default: 4)")
    parser.add_argument("--keep-policy-days", type=int, default=0,
        help="Number of previous days to keep backed up (default: 0)")
    parser.add_argument("--keep-policy-weeks", type=int, default=0,
        help="Number of previous weeks to keep backed up (default: 0)")
    parser.add_argument("--keep-policy-months", type=int, default=0,
        help="Number of previous months to keep backed up (default: 0)")
    parser.add_argument("--keep-policy-years", type=int, default=0,
        help="Number of previous years to keep backed up (default: 0)")

    args = parser.parse_args(argv)

    keep_old = args.keep_old
    keep_policy = None
    if (args.keep_policy_days or args.keep_policy_weeks or args.keep_policy_months or args.keep_policy_years):
        if keep_old:
            parser.error("--keep-old and --keep-policy cannot be used together")
        keep_policy = {
            "days": args.keep_policy_days,
            "weeks": args.keep_policy_weeks,
            "months": args.keep_policy_months,
            "years": args.keep_policy_years,
        }
        print("Using a policy of preserving %d days, %d weeks, %d months, and %d years" % (
            keep_policy['days'],
            keep_policy['weeks'],
            keep_policy['months'],
            keep_policy['years']))
    elif not keep_old:
        keep_old = 4

    backup_prefix = args.backup_prefix
    if not args.backup_prefix:
        backup_prefix = os.path.basename(args.directory.rstrip(os.sep))

    backup_maker = BackerUpper(client_secrets=args.client_secrets, token_file=args.token_file)

    # make the parent folder if it does not exist
    parent_folder_id = backup_maker.init_backup_folder(args.backup_dir)

    # find old tarfiles
    old_files = backup_maker.find_files_in_folder(parent_folder_id)
    delete_list = find_deletion_candidates(old_files, '%s_' % backup_prefix, max_keep=keep_old, keep_policy=keep_policy)
    if delete_list:
        if args.dry_run:
            print("Deleting the following: \n", "\n  ".join([x.get('name', '<unknown>') for x in delete_list]))
        else:
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
