"""
MIT License

Copyright (c) 2025 Damian Zaremba

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
"""

from typing import Dict, List

import requests


def get_latest_github_release(org: str, repo: str):
    r = requests.get(f"https://api.github.com/repos/{org}/{repo}/releases/latest")
    r.raise_for_status()
    return r.json()["tag_name"]


def download_wp_edit(edit_id: int) -> str:
    r = requests.get(f"https://cluebotng-review.toolforge.org/api/v1/edit/{edit_id}/dump-wpedit/")
    r.raise_for_status()
    return r.text


def wp_edit_as_edit_set(wp_edit: str) -> str:
    return f'<?xml version="1.0"?><WPEditSet>{wp_edit}</WPEditSet>'


def get_target_edit_groups(review_host: str, filter_edit_set: List[str]) -> Dict[str, Dict[str, int]]:
    r = requests.get(f"{review_host}/api/v1/edit-groups/")
    r.raise_for_status()
    data = r.json()

    edit_groups_by_id = {edit_group["id"]: edit_group for edit_group in data}
    mapped_edit_groups = {}
    for edit_group in data:
        parent_group = (
            edit_groups_by_id[edit_group["related_to"]]["name"] if edit_group["related_to"] else edit_group["name"]
        )
        if parent_group not in mapped_edit_groups:
            mapped_edit_groups[parent_group] = {}
        mapped_edit_groups[parent_group][edit_group["type"]] = edit_group["id"]

    return {
        name: groups for name, groups in mapped_edit_groups.items() if not filter_edit_set or name in filter_edit_set
    }
