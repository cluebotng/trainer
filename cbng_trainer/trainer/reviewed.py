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
import aiohttp_retry

from cbng_trainer.common.models import ReviewedEdit, User, Page, Diff

logger = logging.getLogger(__name__)


async def fetch_reviewed_edits(session, include_edit_sets):
    logger.info('Fetching completed edits from review interface')
    async with session.get('https://cluebotng-review.toolforge.org/api/export/trainer.json') as r:
        data = await r.json()

    for edit_group_id, reviewed_edits in data.items():
        if include_edit_sets is None or int(edit_group_id) in include_edit_sets:
            for edit_id, edit_is_vandalism in reviewed_edits.items():
                yield (int(edit_id), edit_is_vandalism)


async def fetch_edit_contents(session, rev_id):
    logger.info(f'Fetching revision contents for {rev_id}')
    async with session.get('https://en.wikipedia.org/w/index.php', params={
        'action': 'raw',
        'diff': rev_id,
    }) as r:
        return await r.text()


async def fetch_edit_data(session, rev_id):
    logger.info(f'Fetching extended edit info for {rev_id}')
    async with session.get('https://cluebotng.toolforge.org/api/', params={
        'action': 'training.data',
        'rev_id': rev_id,
        'include_text': '1',
    }) as r:
        return await r.json()


async def load_reviewed_edits(include_edit_sets):
    async with aiohttp_retry.RetryClient(
        timeout=aiohttp.ClientTimeout(total=600, connect=60),
        connector=aiohttp.TCPConnector(limit_per_host=20),
        raise_for_status=False,
        retry_options=aiohttp_retry.ExponentialRetry(attempts=3),
    ) as session:
        async for edit_id, edit_is_vandalism in fetch_reviewed_edits(session, include_edit_sets):
            edit_data = await fetch_edit_data(session, edit_id)
            if 'error' in edit_data:
                logger.error(f'Failed to fetch edit data for {edit_id}: {edit_data}')
                continue

            if 'text' in edit_data['current'] and 'text' in edit_data['previous']:
                current_edit, previous_edit = (edit_data['current']['text'],
                                               edit_data['previous']['text'])
            else:
                current_edit, previous_edit = await asyncio.gather(
                    fetch_edit_contents(session, edit_data['current']['id']),
                    fetch_edit_contents(session, edit_data['previous']['id'])
                )

            yield ReviewedEdit(
                edit_data['current']['id'],
                edit_data['current']['comment'],
                User(
                    edit_data['current']['user']['name'],
                    edit_data['current']['user']['edit_count'],
                    edit_data['current']['user']['distinct_pages_count'],
                    edit_data['current']['user']['warning_count'],
                    edit_data['current']['user']['registration_time'],
                ),
                User(
                    edit_data['previous']['user']['name'],
                    None,
                    None,
                    None,
                    None,
                ),
                Page(
                    edit_data['page']['title'],
                    edit_data['page']['namespace'],
                    edit_data['page']['creator'],
                    edit_data['page']['creation_time'],
                    edit_data['page']['recent_edit_count'],
                    edit_data['page']['recent_reversion_count'],
                ),
                Diff(
                    edit_data['current']['minor'],
                    edit_data['current']['timestamp'],
                    current_edit,
                ),
                Diff(
                    edit_data['previous']['minor'],
                    edit_data['previous']['timestamp'],
                    previous_edit,
                ),
                edit_is_vandalism,
            )


async def dump_reviewed_edits(target_path, include_edit_sets):
    with target_path.open('w') as fh:
        fh.write('<?xml version="1.0"?>\n')
        fh.write('<WPEditSet>\n')
        async for edit in load_reviewed_edits(include_edit_sets):
            logger.info(f'Adding edit {edit.id} to dataset')
            fh.write(f'{edit.as_xml()}\n')
        fh.write('</WPEditSet>\n')
