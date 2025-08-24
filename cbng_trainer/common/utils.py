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


def get_latest_github_release(org: str, repo: str):
    r = requests.get(f"https://api.github.com/repos/{org}/{repo}/releases/latest")
    r.raise_for_status()
    return r.json()["tag_name"]


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


def generate_execution_script(
    release_ref: str,
    download_bins_url: Optional[str] = None,
    download_edit_set_url: Optional[str] = None,
    override_file_urls: Optional[Dict[str, str]] = None,
    skip_setup: bool = False,
    skip_binary_setup: bool = False,
    run_commands: Optional[List[str]] = None,
) -> str:
    setup_script = "#!/bin/bash\n"
    # Don't expose the secret
    setup_script += 'echo -e "Authorization:Bearer ${CBNG_TRAINER_FILE_API_KEY}" > /tmp/file-api-headers\n'
    # Expose everything else
    setup_script += "set -xe\n"
    # Emit a know message on exit, so we can parse the logs later
    setup_script += f"trap \"echo '{JOB_LOGS_END_MARKER}'\" EXIT\n"

    # Helper functions
    setup_script += """
    # Helper function, similar to what we had in Python
    # Note: Avoids the secret being exposed by reading the headers from disk
    function upload_file() {
        source_path=$1
        target_url=$2
        if [ -s "${source_path}" ];
        then
            curl \
                --fail \
                --connect-timeout 5 \
                --max-time 60 \
                --retry 5 \
                -H@/tmp/file-api-headers \
                --data-binary "@${source_path}" \
                "${target_url}"
        else
            echo "Not upload ${source_path} - source is empty"
        fi
    }
    """

    files_to_download = {}
    if not skip_setup:
        setup_script += f"""
        mkdir -p /tmp/cbng-core

        # Binaries we need to run
        for bin in cluebotng create_ann create_bayes_db print_bayes_db;
        do
            curl --fail -s -L --output /tmp/cbng-core/$bin https://github.com/cluebotng/core/releases/download/{release_ref}/$bin
            chmod 755 /tmp/cbng-core/$bin
        done

        # Config we need to run
        curl --fail -s -L --output /tmp/conf.tar.gz https://github.com/cluebotng/core/releases/download/{release_ref}/conf.tar.gz
        tar -C /tmp/cbng-core/ -xvf /tmp/conf.tar.gz

        # Hack to not require a tty
        sed -i s'/, "train_outputs"//g' /tmp/cbng-core/conf/cluebotng.conf
        """

        if not skip_binary_setup:
            download_url = (
                download_bins_url
                if download_bins_url
                else f"https://github.com/cluebotng/core/releases/download/{release_ref}"
            )

            files_to_download |= {
                "data/bayes.db": f"{download_url}/bayes.db",
                "data/two_bayes.db": f"{download_url}/two_bayes.db",
                "data/main_ann.fann": f"{download_url}/main_ann.fann",
            }

        if download_edit_set_url:
            files_to_download |= {"edits.xml": download_edit_set_url}

    for name, url in (override_file_urls or {}).items():
        if url is None:
            if name in files_to_download:
                del files_to_download[name]
            continue
        files_to_download[name] = url

    if files_to_download:
        setup_script += "# Ensure target directories exist\n"
        for path in set([PosixPath(path).parent for path in files_to_download if PosixPath(path).parent != "."]):
            setup_script += f"mkdir -p '/tmp/cbng-core/{path}'\n"

        setup_script += "# Download files\n"
        for path, url in files_to_download.items():
            setup_script += f"curl --fail -s -L --output '/tmp/cbng-core/{path}' '{url}'\n"

    if run_commands:
        setup_script += "# Commands\n"
        for command in run_commands:
            setup_script += f"{command}\n"
    else:
        setup_script += "# Wait for interaction\n"
        setup_script += "touch /tmp/container_ready\n"
        setup_script += "sleep infinity\n"
    return setup_script


def generate_command_command(setup_script: str, run_timeout: str) -> str:
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
