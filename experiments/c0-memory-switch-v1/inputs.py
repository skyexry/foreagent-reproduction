"""Recover ordered fresh-query endpoints from logged, verbatim program texts."""
import hashlib
import re

STAMP = r'^\[\d{4}-\d\d-\d\d \d\d:\d\d:\d\d,\d+\] '
QUERY = re.compile(STAMP + r"INFO: Querying model '([^']+)' with message:")
CACHE = re.compile(STAMP + r'INFO: Cache hit for pair: \((-?\d+), (-?\d+)\)$')
RECORD = re.compile(STAMP + r'(?:INFO|WARNING|ERROR|DEBUG|CRITICAL):')
HEAD = 'Provided solutions:\n### Solution 0:\n' + chr(96)*3 + 'python\n\n'
MID = '\n' + chr(96)*3 + '\n\n### Solution 1:\n' + chr(96)*3 + 'python\n\n'
END = '\n' + chr(96)*3


def code_digest(code):
    return hashlib.sha256(code.replace('\r\n', '\n').replace('\r', '\n').encode()).hexdigest()


def _transport(lines, start0, stop0):
    i = start0
    while i < stop0:
        line = lines[i]
        if cache := CACHE.match(line):
            yield i, 'cache', tuple(map(int, cache.groups()))
        query = QUERY.match(line)
        if not query or 'thinking' not in query[1].lower():
            i += 1
            continue
        end = i + 1
        while end < stop0 and not RECORD.match(lines[end]):
            end += 1
        prompt = '\n'.join(lines[i+1:end]).rstrip('\n')
        if HEAD not in prompt or not prompt.endswith(END):
            raise ValueError(f'Unexpected comparison prompt format at line {i+1}')
        payload = prompt.rsplit(HEAD, 1)[1][:-len(END)]
        left, sep, right = payload.partition(MID)
        if not sep or MID in right:
            raise ValueError(f'Ambiguous comparison separator at line {i+1}')
        yield i, 'query', (left, right)
        i = end


def past_query_index(lines):
    """Earliest observed fresh query for a code pair anywhere in this run (0-based)."""
    index = {}
    for line, mode, pair in _transport(lines, 0, len(lines)):
        if mode == 'query':
            index.setdefault(frozenset(map(code_digest, pair)), line)
    return index


def transport_events(lines, start0, stop0, candidates):
    """Return query ID pairs and salted cache-key pairs (log line indices start at 0).

    The journal's evaluated response is a separate source. No response body or
    asynchronous completion order is assumed to belong to a given prompt.
    """
    by_code = {}
    for n in candidates:
        by_code.setdefault(code_digest(n['code']), []).append(n['id'])
    events = []
    for line, mode, pair in _transport(lines, start0, stop0):
        if mode == 'query':
            endpoints = [by_code.get(code_digest(code), []) for code in pair]
            if any(len(ids) != 1 for ids in endpoints):
                raise ValueError(f'Non-unique or absent candidate text at line {line+1}: {endpoints}')
            pair = endpoints[0][0], endpoints[1][0]
        events.append((line, mode, pair))
    return events
