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
from random import Random

import aiohttp
import aiohttp_retry

from cbng_trainer.common.models import ReviewedEdit, User, Page, Diff

logger = logging.getLogger(__name__)


async def fetch_edits(session, settings, include_edit_sets, use_random_edits, random_edits_limit):
    logger.info('Fetching edits from review interface')
    async with session.get(f'https://{settings.api_hosts.review}/api/export/trainer.json') as r:
        data = await r.json()

    random = Random()
    included_edits = 0
    for edit_group_id, reviewed_edits in data.items():
        if include_edit_sets is None or int(edit_group_id) in include_edit_sets:
            for edit_id, edit_is_vandalism in reviewed_edits.items():
                if use_random_edits and included_edits > random_edits_limit:
                    break
                if not use_random_edits or random.getrandbits(1):
                    yield (int(edit_id), edit_is_vandalism)
                included_edits += 1


async def build_edit_data(session, settings, edit_id, edit_is_vandalism):
    logger.info(f'Fetching extended edit info for {edit_id}')
    async with session.get(f'https://{settings.api_hosts.api}', params={
        'action': 'training.data',
        'rev_id': edit_id,
        'include_text': '1',
    }) as r:
        edit_data = await r.json()

    if 'error' in edit_data:
        logger.error(f'Failed to get edit data for {edit_id}: {edit_data}')
        return None

    logger.info(f'Emitting ReviewedEdit for {edit_id}')
    return ReviewedEdit(
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
            edit_data['current']['text'],
        ),
        Diff(
            edit_data['previous']['minor'],
            edit_data['previous']['timestamp'],
            edit_data['previous']['text'],
        ),
        edit_is_vandalism,
    )


async def load_edits(settings, include_edit_sets, use_random_edits, random_edits_limit):
    async with aiohttp_retry.RetryClient(
        timeout=aiohttp.ClientTimeout(total=300, sock_read=300, connect=60),
        connector=aiohttp.TCPConnector(limit_per_host=settings.max_host_connections),
        raise_for_status=False,
        retry_options=aiohttp_retry.ExponentialRetry(attempts=5),
    ) as session:
        edits = await asyncio.gather(*[
            build_edit_data(session, settings, edit_id, edit_is_vandalism)
            async for edit_id, edit_is_vandalism in fetch_edits(session, settings,
                                                                include_edit_sets,
                                                                use_random_edits,
                                                                random_edits_limit)
        ])
        return [edit for edit in edits if edit is not None]


async def dump_edits(settings,
                     target_path,
                     include_edit_sets,
                     use_random_edits,
                     random_edits_limit):
    edits = await load_edits(settings,
                             include_edit_sets,
                             use_random_edits,
                             random_edits_limit)
    with target_path.open('w') as fh:
        fh.write('<?xml version="1.0"?>\n')
        fh.write('<WPEditSet>\n')
        for edit in edits:
            logger.info(f'Adding edit {edit.id} to dataset')
            fh.write(f'{edit.as_xml()}\n')
        fh.write('</WPEditSet>\n')
