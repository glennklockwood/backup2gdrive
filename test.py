import random
import datetime
import pprint
from backup_mud import find_deletion_candidates

KEEP_POLICY = {
    "days": 7,
    "weeks": 4,
    "months": 12,
    "years": 10,
}

DATE_RANGES = [
    (datetime.datetime(2019, 1, 1), 500),
    (datetime.datetime(2020, 1, 1), 500),
    (datetime.datetime.now() - datetime.timedelta(days=14), 200),
    (datetime.datetime.now() - datetime.timedelta(days=7), 200),
]

def gen_file_list(date_ranges):
    file_list = []
    for datestart, count in date_ranges:
        date_range = int((datetime.datetime.now() - datestart).total_seconds())
        for i in range(count):
            file_list.append(
            {
                'id': random.randint(0, 32767),
                'createdTime': '%s.000Z' % (datestart + datetime.timedelta(seconds=random.randint(0, date_range))).strftime("%Y-%m-%dT%H:%M:%S"),
                'name': '',
            })
    return file_list

def test_random(date_ranges=DATE_RANGES, keep_policy=KEEP_POLICY):
    file_list = gen_file_list(date_ranges=date_ranges)
    keeping = find_deletion_candidates(file_list=file_list, filename_prefix='', max_keep=None, keep_policy=keep_policy)
    counts = {}
    for val in keeping:
        print("Keeping %s because %s" % (val['created_datetime'], val['why']))
        for whystr in val['why']:
            why = whystr.split('(', 1)[0]
            counts[why] = counts[why] + 1 if why in counts else 1

    print("Policy is")
    pprint.pprint(keep_policy)
    print("\nActual count is")
    pprint.pprint(counts)
    for interval, count in counts.items():
        assert count <= keep_policy[interval] + 1

if __name__ == "__main__":
    test_random()
