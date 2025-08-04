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
import uuid
from typing import Dict

from cbng_trainer.common.consts import THREASHOLDS_PLOT, FALSE_POSITIVES_PLOT
from cbng_trainer.common.toolforge import run_job

logger = logging.getLogger(__name__)


class Steps:
    def __init__(
        self,
        job_name: str,
        toolforge_user: str,
        image_name: str,
        release_ref: str,
    ):
        self.job_name = job_name
        self.toolforge_user = toolforge_user
        self.image_name = image_name
        self.release_ref = release_ref

    def store_edit_sets(self, mapping: Dict[str, str]) -> bool:
        commands = []
        for download_url, upload_url in mapping.items():
            temp_path = f"/tmp/{uuid.uuid4().hex}"
            commands.append(f"curl --fail --progress-bar -sL --output '{temp_path}' '{download_url}'")
            commands.append(f'upload_file "{temp_path}" "{upload_url}"')

        return run_job(
            target_user=self.toolforge_user,
            job_name=f"{self.job_name}-store-edit-sets",
            image_name=self.image_name,
            skip_setup=True,
            run_commands=commands,
        )

    def run_bayes_train(
        self,
        download_edit_set_url: str,
        upload_files_url: str,
    ) -> bool:
        return run_job(
            target_user=self.toolforge_user,
            job_name=f"{self.job_name}-bayes-train",
            image_name=self.image_name,
            release_ref=self.release_ref,
            download_edit_set_url=download_edit_set_url,
            skip_binary_setup=True,
            run_commands=[
                "cd /tmp/cbng-core && mkdir data/ && ./cluebotng -c conf -m bayes_train -f edits.xml",
                f'upload_file "data/main_bayes_train.dat" "{upload_files_url}/main_bayes_train.dat"',
                f'upload_file "data/two_bayes_train.dat" "{upload_files_url}/two_bayes_train.dat"',
            ],
        )

    def create_main_bayes_db(
        self,
        download_edit_set_url: str,
        upload_files_url: str,
    ) -> bool:
        return run_job(
            target_user=self.toolforge_user,
            job_name=f"{self.job_name}-create-main-bayes-db",
            image_name=self.image_name,
            release_ref=self.release_ref,
            download_edit_set_url=download_edit_set_url,
            skip_binary_setup=True,
            override_file_urls={
                # Produced by `run_bayes_train`
                "data/main_bayes_train.dat": f"{upload_files_url}/main_bayes_train.dat",
            },
            run_commands=[
                "cd /tmp/cbng-core && ./create_bayes_db data/bayes.db data/main_bayes_train.dat",
                f'upload_file "data/bayes.db" "{upload_files_url}/bayes.db"',
            ],
        )

    def create_two_bayes_db(
        self,
        download_edit_set_url: str,
        upload_files_url: str,
    ) -> bool:
        return run_job(
            target_user=self.toolforge_user,
            job_name=f"{self.job_name}-create-two-bayes-db",
            image_name=self.image_name,
            release_ref=self.release_ref,
            download_edit_set_url=download_edit_set_url,
            skip_binary_setup=True,
            override_file_urls={
                # Produced by `run_bayes_train`
                "data/two_bayes_train.dat": f"{upload_files_url}/two_bayes_train.dat",
            },
            run_commands=[
                "cd /tmp/cbng-core && ./create_bayes_db data/two_bayes.db data/two_bayes_train.dat",
                f'upload_file "data/two_bayes.db" "{upload_files_url}/two_bayes.db"',
            ],
        )

    def run_ann_train(
        self,
        download_edit_set_url: str,
        upload_files_url: str,
    ) -> bool:
        return run_job(
            target_user=self.toolforge_user,
            job_name=f"{self.job_name}-ann-train",
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
                "cd /tmp/cbng-core && ./cluebotng -c conf -m ann_train -f edits.xml",
                f'upload_file "data/main_ann_train.dat" "{upload_files_url}/main_ann_train.dat"',
            ],
        )

    def run_create_ann(
        self,
        download_edit_set_url: str,
        upload_files_url: str,
    ) -> bool:
        return run_job(
            target_user=self.toolforge_user,
            job_name=f"{self.job_name}-create-ann",
            image_name=self.image_name,
            release_ref=self.release_ref,
            download_edit_set_url=download_edit_set_url,
            skip_binary_setup=True,
            override_file_urls={
                # Produced by `run_ann_train`
                "data/main_ann_train.dat": f"{upload_files_url}/main_ann_train.dat",
            },
            run_commands=[
                "cd /tmp/cbng-core && ./create_ann data/main_ann.fann data/main_ann_train.dat 150 0.037 100",
                f'upload_file "data/main_ann.fann" "{upload_files_url}/main_ann.fann"',
            ],
        )

    def run_trial_report(
        self,
        download_edit_set_url: str,
        download_bins_url: str,
        upload_report_url: str,
    ) -> bool:
        return run_job(
            target_user=self.toolforge_user,
            job_name=f"{self.job_name}-trial-report",
            image_name=self.image_name,
            release_ref=self.release_ref,
            download_bins_url=download_bins_url,
            download_edit_set_url=download_edit_set_url,
            run_commands=[
                "cd /tmp/cbng-core && mkdir trialreport/ && ./cluebotng -c conf -m trial_run -f edits.xml",
            ]
            + [
                f'upload_file "trialreport/{file_name}" "{upload_report_url}/{file_name}"'
                for file_name in [
                    "debug.xml",
                    "details.txt",
                    "falsenegatives.txt",
                    "falsepositives.txt",
                    "report.txt",
                    "thresholdtable.txt",
                ]
            ],
        )

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

        return run_job(
            target_user=self.toolforge_user,
            job_name=f"{self.job_name}-create-plots",
            image_name=self.image_name,
            skip_setup=True,
            override_file_urls={
                "trialreport/thresholdtable.txt": f"{upload_report_url}/thresholdtable.txt",
            },
            run_commands=run_commands,
        )
