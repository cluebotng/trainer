#!/usr/bin/env python3
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
import logging
import os
import uuid
from typing import Dict, List

import requests

from cbng_trainer.common.consts import THREASHOLDS_PLOT, FALSE_POSITIVES_PLOT, JOB_LOGS_END_MARKER
from cbng_trainer.common.toolforge import run_job
from cbng_trainer.common.utils import clean_job_name

logger = logging.getLogger(__name__)


class Steps:
    def __init__(
        self,
        target_name: str,
        toolforge_user: str,
        image_name: str,
        release_ref: str,
        upload_logs: str,
    ):
        self.target_name = target_name
        self.toolforge_user = toolforge_user
        self.image_name = image_name
        self.release_ref = release_ref
        self.upload_logs = upload_logs
        self._file_api_key = os.environ.get("FILE_API_KEY", "")

    def _clean_log_lines(self, logs: List[str]) -> List[str]:
        clean_lines = []
        for line in logs:
            # Remove the internal marker
            if line.strip().endswith(f": {JOB_LOGS_END_MARKER}"):
                continue

            # This shouldn't happen as we load the headers in from disk, but just in case
            # Worst case the only thing someone can do with it is upload files that don't already exist
            line = line.replace(self._file_api_key, "*****")

            clean_lines.append(line)

        return clean_lines

    def _upload_logs(self, identifier: str, logs: List[str]) -> None:
        if not logs:
            logger.debug(f"No logs to upload for {identifier}")
            return

        if not self._file_api_key:
            logger.error(f"Failed to find api key, skipping log upload")
            return

        # Note: we are not in a container at this point, so access the API directly,
        #       this logic is the equivalent to `upload_file` in bash
        target_url = f'{self.upload_logs.rstrip("/")}/{identifier}.log'
        logger.info(f"Publishing logs to {target_url}")
        r = requests.post(
            target_url,
            headers={"Authorization": f"Bearer {self._file_api_key}"},
            data="\n".join(self._clean_log_lines(logs)),
        )
        if r.status_code != 201:
            logger.warning(f"Failed to upload logs for {identifier}: {r.status_code} ({r.text})")

    def store_edit_sets(self, mapping: Dict[str, str]) -> bool:
        commands = []
        for download_url, upload_url in mapping.items():
            temp_path = f"/tmp/{uuid.uuid4().hex}"
            commands.extend(
                [
                    f"echo \"Downloading '{download_url}' to '{temp_path}'\"",
                    f"curl --fail --progress-bar -sL --output '{temp_path}' '{download_url}'",
                    f'upload_file "{temp_path}" "{upload_url}"',
                ]
            )

        success, logs = run_job(
            target_user=self.toolforge_user,
            job_name=clean_job_name(self.target_name, postfix="store-edit-sets"),
            image_name=self.image_name,
            skip_setup=True,
            run_commands=commands,
        )
        self._upload_logs("store-edit-sets", logs)
        return success

    def run_bayes_train(
        self,
        download_edit_set_url: str,
        upload_files_url: str,
    ) -> bool:
        success, logs = run_job(
            target_user=self.toolforge_user,
            job_name=clean_job_name(self.target_name, postfix="bayes-train"),
            image_name=self.image_name,
            release_ref=self.release_ref,
            download_edit_set_url=download_edit_set_url,
            skip_binary_setup=True,
            run_commands=[
                'echo "Executing bayes_train"',
                "cd /tmp/cbng-core && mkdir data/ && ./cluebotng -c conf -m bayes_train -f edits.xml",
                f'upload_file "data/main_bayes_train.dat" "{upload_files_url}/main_bayes_train.dat"',
                f'upload_file "data/two_bayes_train.dat" "{upload_files_url}/two_bayes_train.dat"',
            ],
        )
        self._upload_logs("bayes-train", logs)
        return success

    def create_main_bayes_db(
        self,
        download_edit_set_url: str,
        upload_files_url: str,
    ) -> bool:
        success, logs = run_job(
            target_user=self.toolforge_user,
            job_name=clean_job_name(self.target_name, postfix="create-main-bayes-db"),
            image_name=self.image_name,
            release_ref=self.release_ref,
            download_edit_set_url=download_edit_set_url,
            skip_binary_setup=True,
            override_file_urls={
                # Produced by `run_bayes_train`
                "data/main_bayes_train.dat": f"{upload_files_url}/main_bayes_train.dat",
            },
            run_commands=[
                'echo "Executing create_bayes_db"',
                "cd /tmp/cbng-core && ./create_bayes_db data/bayes.db data/main_bayes_train.dat",
                f'upload_file "data/bayes.db" "{upload_files_url}/bayes.db"',
            ],
        )
        self._upload_logs("create-main-bayes-db", logs)
        return success

    def create_two_bayes_db(
        self,
        download_edit_set_url: str,
        upload_files_url: str,
    ) -> bool:
        success, logs = run_job(
            target_user=self.toolforge_user,
            job_name=clean_job_name(self.target_name, postfix="create-two-bayes-db"),
            image_name=self.image_name,
            release_ref=self.release_ref,
            download_edit_set_url=download_edit_set_url,
            skip_binary_setup=True,
            override_file_urls={
                # Produced by `run_bayes_train`
                "data/two_bayes_train.dat": f"{upload_files_url}/two_bayes_train.dat",
            },
            run_commands=[
                'echo "Executing create_bayes_db"',
                "cd /tmp/cbng-core && ./create_bayes_db data/two_bayes.db data/two_bayes_train.dat",
                f'upload_file "data/two_bayes.db" "{upload_files_url}/two_bayes.db"',
            ],
        )
        self._upload_logs("create-two-bayes-db", logs)
        return success

    def run_ann_train(
        self,
        download_edit_set_url: str,
        upload_files_url: str,
    ) -> bool:
        success, logs = run_job(
            target_user=self.toolforge_user,
            job_name=clean_job_name(self.target_name, postfix="ann-train"),
            image_name=self.image_name,
            release_ref=self.release_ref,
            download_edit_set_url=download_edit_set_url,
            skip_binary_setup=True,
            override_file_urls={
                # Produced by `create_main_bayes_db` & `create_two_bayes_db`
                "data/bayes.db": f"{upload_files_url}/bayes.db",
                "data/two_bayes.db": f"{upload_files_url}/two_bayes.db",
            },
            run_commands=[
                'echo "Executing ann_train"',
                "cd /tmp/cbng-core && ./cluebotng -c conf -m ann_train -f edits.xml",
                f'upload_file "data/main_ann_train.dat" "{upload_files_url}/main_ann_train.dat"',
            ],
        )
        self._upload_logs("ann-train", logs)
        return success

    def run_create_ann(
        self,
        download_edit_set_url: str,
        upload_files_url: str,
    ) -> bool:
        success, logs = run_job(
            target_user=self.toolforge_user,
            job_name=clean_job_name(self.target_name, postfix="create-ann"),
            image_name=self.image_name,
            release_ref=self.release_ref,
            download_edit_set_url=download_edit_set_url,
            skip_binary_setup=True,
            override_file_urls={
                # Produced by `run_ann_train`
                "data/main_ann_train.dat": f"{upload_files_url}/main_ann_train.dat",
            },
            run_commands=[
                'echo "Executing create_ann"',
                "cd /tmp/cbng-core && ./create_ann data/main_ann.fann data/main_ann_train.dat 150 0.037 100",
                f'upload_file "data/main_ann.fann" "{upload_files_url}/main_ann.fann"',
            ],
        )
        self._upload_logs("create-ann", logs)
        return success

    def run_trial_report(
        self,
        download_edit_set_url: str,
        download_bins_url: str,
        upload_report_url: str,
    ) -> bool:
        run_commands = [
            'echo "Executing trial_run"',
            "cd /tmp/cbng-core && mkdir trialreport/ && ./cluebotng -c conf -m trial_run -f edits.xml",
        ]
        for file_name in [
            "debug.xml",
            "details.txt",
            "falsenegatives.txt",
            "falsepositives.txt",
            "report.txt",
            "thresholdtable.txt",
        ]:
            run_commands.append(f'upload_file "trialreport/{file_name}" "{upload_report_url}/{file_name}"')

        success, logs = run_job(
            target_user=self.toolforge_user,
            job_name=clean_job_name(self.target_name, postfix="trial-report"),
            image_name=self.image_name,
            release_ref=self.release_ref,
            download_bins_url=download_bins_url,
            download_edit_set_url=download_edit_set_url,
            run_commands=run_commands,
        )
        self._upload_logs("trial-report", logs)
        return success

    def create_plots(self, upload_report_url: str) -> bool:
        run_commands = []
        for name, plot in {
            "falsepositives": FALSE_POSITIVES_PLOT,
            "thresholds": THREASHOLDS_PLOT,
        }.items():
            run_commands.extend(
                [
                    "cd /tmp/cbng-core/trialreport",
                    "set +e",
                    f'base64 -d <<<{base64.b64encode(plot.encode("utf-8")).decode("utf-8")} > {name}.gnuplot',
                    f'echo "Generating plot for {name}"',
                    f"gnuplot-qt {name}.gnuplot",
                    (
                        f'if [ -s "{name}.gnuplot" ] && [ -s "{name}.png" ]; then'
                        f'  upload_file "{name}.gnuplot" "{upload_report_url}/{name}.gnuplot";'
                        f'  upload_file "{name}.png" "{upload_report_url}/{name}.png";'
                        "fi"
                    ),
                    "set -e",
                ]
            )

        success, logs = run_job(
            target_user=self.toolforge_user,
            job_name=clean_job_name(self.target_name, postfix="create-plots"),
            image_name=self.image_name,
            skip_setup=True,
            override_file_urls={
                "trialreport/thresholdtable.txt": f"{upload_report_url}/thresholdtable.txt",
            },
            run_commands=run_commands,
        )
        self._upload_logs("create-plots", logs)
        return success
