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

import logging

from cbng_trainer.common.models import Edit, EnquiryResult
from cbng_trainer.comparator.core import score_edit_via_core
from cbng_trainer.comparator.sampler import load_samples

logger = logging.getLogger(__name__)


async def compare_edit(edit: Edit, base_port: int, target_port: int):
    logger.debug(f'Starting comparison using {base_port} vs {target_port} for {edit}')
    base_result = await score_edit_via_core(edit, base_port)
    target_result = await score_edit_via_core(edit, target_port)

    return base_result == target_result, base_result, target_result


async def compare_samples(base_port: int, target_port: int):
    results = []
    async for sample in load_samples():
        matches, base, target = await compare_edit(sample.edit, base_port, target_port)
        results.append(EnquiryResult(
            sample,
            base,
            target,
            matches,
            (sample.is_vandalism is None or target.think_vandalism == sample.is_vandalism),
        ))
    return results
