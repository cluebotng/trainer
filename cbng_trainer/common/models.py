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

import dataclasses
import logging
from typing import Optional
from xml.etree import ElementTree

logger = logging.getLogger(__name__)


@dataclasses.dataclass(frozen=True, repr=True)
class Diff:
    minor: bool
    timestamp: int
    text: str


@dataclasses.dataclass(frozen=True, repr=True)
class User:
    name: str
    edit_count: Optional[int]
    distinct_pages: Optional[int]
    warns: Optional[int]
    registration_time: Optional[int]


@dataclasses.dataclass(frozen=True, repr=True)
class Page:
    title: str
    namespace: str
    creator: str
    creation_time: int
    recent_edit_count: int
    recent_reversion_count: int


@dataclasses.dataclass(frozen=True, repr=True)
class Edit:
    id: int
    comment: str
    user: User
    previous_user: User
    page: Page
    current_diff: Diff
    previous_diff: Diff

    def as_xml(self):
        edit = ElementTree.Element('WPEdit')

        ElementTree.SubElement(edit, 'EditType').text = 'change'
        ElementTree.SubElement(edit, 'EditID').text = f'{self.id}'
        ElementTree.SubElement(edit, 'comment').text = self.comment

        if hasattr(self, 'is_vandalism'):
            ElementTree.SubElement(edit, 'isvandalism').text = ('true' if getattr(self, 'is_vandalism') else 'false')

        ElementTree.SubElement(edit, 'user').text = self.user.name
        ElementTree.SubElement(edit, 'user_edit_count').text = f'{self.user.edit_count}'
        ElementTree.SubElement(edit, 'user_distinct_pages').text = f'{self.user.distinct_pages}'
        ElementTree.SubElement(edit, 'user_warns').text = f'{self.user.warns}'
        ElementTree.SubElement(edit, 'user_reg_time').text = f'{self.user.registration_time}'
        ElementTree.SubElement(edit, 'prev_user').text = f'{self.previous_user.name}'

        common = ElementTree.SubElement(edit, 'common')
        ElementTree.SubElement(common, 'page_made_time').text = f'{self.page.creation_time}'
        ElementTree.SubElement(common, 'title').text = self.page.title
        ElementTree.SubElement(common, 'namespace').text = self.page.namespace
        ElementTree.SubElement(common, 'creator').text = self.page.creator
        ElementTree.SubElement(common, 'num_recent_edits').text = f'{self.page.recent_edit_count}'
        ElementTree.SubElement(common, 'num_recent_reversions').text = f'{self.page.recent_reversion_count}'

        current = ElementTree.SubElement(edit, 'current')
        ElementTree.SubElement(current, 'minor').text = 'true' if self.current_diff.minor else 'false'
        ElementTree.SubElement(current, 'timestamp').text = f'{self.current_diff.timestamp}'
        ElementTree.SubElement(current, 'text').text = self.current_diff.text

        previous = ElementTree.SubElement(edit, 'previous')
        ElementTree.SubElement(previous, 'timestamp').text = f'{self.previous_diff.timestamp}'
        ElementTree.SubElement(previous, 'text').text = self.previous_diff.text

        return ElementTree.tostring(edit).decode()


@dataclasses.dataclass(frozen=True, repr=True)
class ReviewedEdit(Edit):
    is_vandalism: bool


@dataclasses.dataclass(frozen=True, repr=True)
class CoreScore:
    id: int
    score: float
    think_vandalism: bool


@dataclasses.dataclass(frozen=True, repr=True)
class Enquiry:
    edit: Edit
    dataset: str
    is_vandalism: Optional[bool]


@dataclasses.dataclass(frozen=True, repr=True)
class EnquiryResult:
    enquiry: Enquiry
    base_result: CoreScore
    target_result: CoreScore
    results_match: bool
    expected_match: bool
