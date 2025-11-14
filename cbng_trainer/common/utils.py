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

import base64
import re
from pathlib import PosixPath
from typing import Dict, List, Optional

import requests

from cbng_trainer.common.consts import JOB_LOGS_END_MARKER


def get_target_edit_groups(review_host: str, filter_edit_set: List[str]) -> Dict[str, Dict[str, int]]:
    r = requests.get(f"{review_host}/api/v1/edit-groups/", params={"exclude_empty_editsets": "1"}, timeout=10)
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


def generate_execution_script(
    download_file_urls: Optional[Dict[str, str]] = None,
    run_commands: Optional[List[str]] = None,
    configure_upload_file_helper: bool = False,
) -> str:
    setup_script = "#!/bin/bash\n"
    setup_script += "set -e\n"

    # Emit a know message on exit, so we can parse the logs later
    setup_script += f"trap \"echo '{JOB_LOGS_END_MARKER}'\" EXIT\n"

    # Helper functions
    if configure_upload_file_helper:
        # Stash the secret, so we don't expose it e.g. when using set -x
        setup_script += 'echo -e "Authorization:Bearer ${FILE_API_KEY}" > /tmp/file-api-headers\n'

        setup_script += """
# Helper function, similar to what we had in Python
# Note: Avoids the secret being exposed by reading the headers from disk
function upload_file() {
    source_path=$1
    target_url=$2
    if [ -s "${source_path}" ];
    then
        echo "Uploading ${source_path} to ${target_url}"

        curl \
            --fail \
            --connect-timeout 300 \
            --max-time 300 \
            --retry 5 \
            -s \
            -H@/tmp/file-api-headers \
             --upload-file "${source_path}" \
            "${target_url}"
    else
        echo "Skipping upload of ${source_path} to ${target_url}"
    fi
}
"""

    setup_script += "set -x\n"
    if download_file_urls:
        base_dir = PosixPath("/workspace")
        for path, url in download_file_urls.items():
            target_path = (base_dir / path).absolute()

            if target_path.parent.relative_to(base_dir) != ".":
                setup_script += "# Ensure the target directory exists\n"
                setup_script += f"test -d '{target_path.parent.as_posix()}' ||"
                setup_script += f"mkdir -p '{target_path.parent.as_posix()}'\n"

            setup_script += "# Download the file into the target path\n"
            setup_script += "curl --fail -s --connect-timeout 600 --max-time 600 "
            setup_script += f"--retry 5 -L --output '{target_path.as_posix()}' '{url}'\n"

    if run_commands:
        for command in run_commands:
            setup_script += f"{command}\n"
    return setup_script


def generate_command_command(setup_script: str, run_timeout: int) -> str:
    encoded_script = base64.b64encode(setup_script.encode("utf-8")).decode("utf-8")
    return (
        f"bash -c 'base64 -d <<<{encoded_script} > /tmp/setup.sh && "
        f"chmod 755 /tmp/setup.sh && "
        f"timeout {run_timeout} /tmp/setup.sh'"
    )


def clean_job_name(name: str, prefix: Optional[str] = None, postfix: Optional[str] = None) -> str:
    job_name = name
    if prefix:
        job_name = f"{prefix}-{job_name}"
    if postfix:
        job_name = f"{job_name}-{postfix}"
    job_name = re.sub(r"[^A-Za-z0-9]", "-", job_name).lower()
    while "--" in job_name:
        job_name = job_name.replace("--", "")
    return job_name[0:50]
