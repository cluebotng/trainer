'''
MIT License

Copyright (c) 2021 Damian Zaremba

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
'''

import asyncio
import logging

import aiohttp

from cbng_trainer.common.models import Edit, User, Page, Diff, Enquiry

logger = logging.getLogger(__name__)


async def build_edit_from_revision_id(session, rev_id: int):
    logger.info(f'Fetching training data for {rev_id}')
    async with session.get('http://localhost:8081/api/', params={
        'action': 'training.data',
        'rev_id': rev_id,
    }) as r:
        extended_data = await r.json()
        if 'error' in extended_data:
            logger.error(f'Failed to get training data for {rev_id}: {extended_data}')
            return None

    logger.info(f'Fetching edit data for {rev_id}')
    async with session.get('https://en.wikipedia.org/w/api.php', params={
        'action': 'query',
        'prop': 'revisions',
        'titles': f"{extended_data['page']['title']}",
        'rvstartid': f"{extended_data['current']['id']}",
        'rvlimit': 2,
        'rvprop': 'ids|content',
        'rvslots': '*',
        'format': 'json',
    }) as r:
        api_data = await r.json()
    if 'query' not in api_data:
        return None

    revisions = api_data['query']['pages'][extended_data['page']['id']]['revisions']

    assert revisions[0]['revid'] == extended_data['current']['id']
    extended_data['current']['text'] = revisions[0]['slots']['main']['*'] if '*' in revisions[0]['slots'][
        'main'] else ''

    assert revisions[1]['revid'] == extended_data['previous']['id']
    extended_data['previous']['text'] = revisions[1]['slots']['main']['*'] if '*' in revisions[1]['slots'][
        'main'] else ''

    return Edit(
        extended_data['current']['id'],
        extended_data['current']['comment'],
        User(
            extended_data['current']['user']['name'],
            extended_data['current']['user']['edit_count'],
            extended_data['current']['user']['distinct_pages_count'],
            extended_data['current']['user']['warning_count'],
            extended_data['current']['user']['registration_time'],
        ),
        User(
            extended_data['previous']['user']['name'],
            None,
            None,
            None,
            None,
        ),
        Page(
            extended_data['page']['title'],
            extended_data['page']['namespace'],
            extended_data['page']['creator'],
            extended_data['page']['creation_time'],
            extended_data['page']['recent_edit_count'],
            extended_data['page']['recent_reversion_count'],
        ),
        Diff(
            extended_data['current']['minor'],
            extended_data['current']['timestamp'],
            extended_data['current']['text'],
        ),
        Diff(
            extended_data['previous']['minor'],
            extended_data['previous']['timestamp'],
            extended_data['previous']['text'],
        )
    )


async def load_reviewed_vandalism(session):
    samples = []
    async with session.get('http://localhost:8081/api/', params={
        'action': 'reports.list',
        'status': 8,
        'limit': 10,
        'random': 1,
    }) as r:
        reports = await r.json()
        for report in reports.values():
            if report['revid'] is None:
                print(report)
            edit = await build_edit_from_revision_id(session, report['revid'])
            if edit:
                samples.append(Enquiry(edit, "reviewed-vandalism", True))
    return samples


async def load_reviewed_constructive(session):
    samples = []
    async with session.get('http://localhost:8081/api/', params={
        'action': 'reports.list',
        'status': 7,
        'limit': 10,
        'random': 1,
    }) as r:
        reports = await r.json()
        for report in reports.values():
            if report['revid'] is None:
                print(report)
            edit = await build_edit_from_revision_id(session, report['revid'])
            if edit:
                samples.append(Enquiry(edit, "reviewed-constructive", False))
    return samples


async def load_reported_pending(session):
    samples = []
    async with session.get('http://localhost:8081/api/', params={
        'action': 'reports.list',
        'status': 6,
        'limit': 10,
        'random': 1,
    }) as r:
        reports = await r.json()
        for report in reports.values():
            if report['revid'] is None:
                print(report)
            edit = await build_edit_from_revision_id(session, report['revid'])
            if edit:
                samples.append(Enquiry(edit, "reported-pending-review", None))
    return samples


async def load_random(session):
    samples = []
    async with session.get('http://localhost:8081/api/', params={
        'action': 'edits.list',
        'limit': 10,
        'random': 1,
    }) as r:
        reports = await r.json()
        for report in reports.values():
            if report['new_id'] is None:
                print(report)
            edit = await build_edit_from_revision_id(session, report['new_id'])
            if edit:
                samples.append(Enquiry(edit, "random-edits", None))
    return samples


async def load_samples():
    async with aiohttp.ClientSession(connector=aiohttp.TCPConnector(limit_per_host=20)) as session:
        results = await asyncio.gather(
            load_reviewed_vandalism(session),
            load_reviewed_constructive(session),
            load_reported_pending(session),
            load_random(session),
        )
    for result in results:
        for enquiry in result:
            yield enquiry
