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
import socket
from xml.etree import ElementTree

from cbng_trainer.common.models import Edit, CoreScore

logger = logging.getLogger(__name__)


async def score_edit_via_core(edit: Edit, port: int):
    xml = edit.as_xml()
    logger.debug(f'Sending to {port}: {xml}')

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.connect(('127.0.0.1', port))
        s.sendall(f'<?xml version="1.0"?>\n<WPEditSet>\n{xml}\n</WPEditSet>'.encode('utf-8'))

        response = ''
        while True:
            data = s.recv(1024).decode('utf-8')
            if data == '':
                break
            response += data

    et = ElementTree.fromstring(response)
    cs = CoreScore(
        int(et.find('./WPEdit/editid').text),
        float(et.find('./WPEdit/score').text),
        et.find('./WPEdit/think_vandalism').text == 'true',
    )
    logger.info(f'[{edit.id}] returning from {port}: {cs}')
    return cs
