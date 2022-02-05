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

from cbng_trainer.common.models import ReviewedEdit, User, Page, Diff

logger = logging.getLogger(__name__)


async def fetch_reviewed_edits(session):
    logger.info('Fetching completed edits from review interface')
    async with session.get('https://cluebotng-review.toolforge.org/api/export/done.json') as r:
        data = await r.json()

    for edit_group in data['EditGroups']:
        for edit in edit_group['Done']:
            yield edit


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
    }) as r:
        return await r.json()


async def load_reviewed_edits():
    async with aiohttp.ClientSession(
        timeout=aiohttp.ClientTimeout(total=600, connect=60)
    ) as session:
        async for edit in fetch_reviewed_edits(session):
            is_vandalism = (edit['RealClassification'] == 'V')
            edit_data = await fetch_edit_data(session, edit['Id'])
            if 'error' in edit_data:
                logger.error(f'Failed to fetch edit data for {edit["Id"]}: {edit_data}')
                continue

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
                is_vandalism,
            )


async def dump_reviewed_edits(target_path):
    with target_path.open('w') as fh:
        fh.write('<?xml version="1.0"?>\n')
        fh.write('<WPEditSet>\n')
        async for edit in load_reviewed_edits():
            logger.info(f'Adding edit {edit.id} to dataset')
            fh.write(f'{edit.as_xml()}\n')
        fh.write('</WPEditSet>\n')
