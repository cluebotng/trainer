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
from pathlib import PosixPath
from typing import Optional, Dict

from cbng_trainer.common.kubernetes import (
    run_container,
    execute_in_container,
    store_container_file,
)

logger = logging.getLogger(__name__)


def run_bayes_train(
    container_namespace: str,
    container_name: str,
    download_edit_set_url: str,
    upload_files_url: str,
    release_ref: str,
) -> bool:
    with run_container(
        namespace=container_namespace,
        name=container_name,
        release_ref=release_ref,
        download_edit_set_url=download_edit_set_url,
    ) as container_id:
        success, stdout, stderr = execute_in_container(
            container_namespace, container_id, "./cluebotng -c conf -m bayes_train -f edits.xml"
        )
        if not success:
            logger.info(f"Failed bayes_train: {stdout} / {stderr}")
            return False

        logger.info(f"Finished bayes_train: {stdout} / {stderr}")
        is_success = True
        for file_name in ["main_bayes_train.dat", "two_bayes_train.dat"]:
            if not store_container_file(
                container_namespace, container_id, (PosixPath("data") / file_name), f"{upload_files_url}/{file_name}"
            ):
                logger.warning(f"Failed to store {file_name}")
                is_success &= False
        return is_success


def create_main_bayes_db(
    container_namespace: str,
    container_name: str,
    download_edit_set_url: str,
    upload_files_url: str,
    release_ref: str,
) -> bool:
    with run_container(
        namespace=container_namespace,
        name=container_name,
        release_ref=release_ref,
        download_edit_set_url=download_edit_set_url,
        override_file_urls={
            # Produced by `run_bayes_train`
            "main_bayes_train.dat": f"{upload_files_url}/main_bayes_train.dat",
            # We will generate this
            "bayes.db": None,
        },
    ) as container_id:
        success, stdout, stderr = execute_in_container(
            container_namespace, container_id, "./create_bayes_db data/bayes.db data/main_bayes_train.dat"
        )
        if not success:
            logger.info(f"Failed create_bayes_db (bayes): {stdout} / {stderr}")
            return False

        logger.info(f"Finished create_bayes_db (bayes): {stdout} / {stderr}")
        if not store_container_file(
            container_namespace, container_id, (PosixPath("data") / "bayes.db"), f"{upload_files_url}/bayes.db"
        ):
            logger.warning("Failed to store bayes.db")
            return False
        return True


def create_two_bayes_db(
    container_namespace: str,
    container_name: str,
    download_edit_set_url: str,
    upload_files_url: str,
    release_ref: str,
) -> bool:
    with run_container(
        namespace=container_namespace,
        name=container_name,
        release_ref=release_ref,
        download_edit_set_url=download_edit_set_url,
        override_file_urls={
            # Produced by `run_bayes_train`
            "two_bayes_train.dat": f"{upload_files_url}/two_bayes_train.dat",
            # We will generate this
            "two_bayes.db": None,
        },
    ) as container_id:
        success, stdout, stderr = execute_in_container(
            container_namespace, container_id, "./create_bayes_db data/two_bayes.db data/two_bayes_train.dat"
        )
        if not success:
            logger.info(f"Failed create_bayes_db (two_bayes): {stdout} / {stderr}")
            return False

        logger.info(f"Finished create_bayes_db (two_bayes): {stdout} / {stderr}")
        if not store_container_file(
            container_namespace, container_id, (PosixPath("data") / "two_bayes.db"), f"{upload_files_url}/two_bayes.db"
        ):
            logger.warning("Failed to store two_bayes.db")
            return False
        return True


def run_ann_train(
    container_namespace: str,
    container_name: str,
    download_edit_set_url: str,
    upload_files_url: str,
    release_ref: str,
) -> bool:
    with run_container(
        namespace=container_namespace,
        name=container_name,
        release_ref=release_ref,
        download_edit_set_url=download_edit_set_url,
        override_file_urls={
            # Produced by `create_main_bayes_db` & create_two_bayes_db
            "bayes.db": f"{upload_files_url}/bayes.db",
            "two_bayes.db": f"{upload_files_url}/two_bayes.db",
        },
    ) as container_id:
        success, stdout, stderr = execute_in_container(
            container_namespace, container_id, "./cluebotng -c conf -m ann_train -f edits.xml"
        )
        if not success:
            logger.info(f"Failed ann_train: {stdout} / {stderr}")
            return False
        logger.info(f"Finished ann_train: {stdout} / {stderr}")

        if not store_container_file(
            container_namespace,
            container_id,
            (PosixPath("data") / "main_ann_train.dat"),
            f"{upload_files_url}/main_ann_train.dat",
        ):
            return False
        return True


def run_create_ann(
    container_namespace: str,
    container_name: str,
    download_edit_set_url: str,
    upload_files_url: str,
    release_ref: str,
) -> bool:
    with run_container(
        namespace=container_namespace,
        name=container_name,
        release_ref=release_ref,
        download_edit_set_url=download_edit_set_url,
        override_file_urls={
            # Produced by `run_ann_train`
            "main_ann_train.dat": f"{upload_files_url}/main_ann_train.dat",
            # We will generate this
            "main_ann.fann": None,
        },
    ) as container_id:
        success, stdout, stderr = execute_in_container(
            container_namespace, container_id, "./create_ann data/main_ann.fann data/main_ann_train.dat 150 0.037 100"
        )
        if not success:
            logger.info(f"Failed create_ann: {stdout} / {stderr}")
            return False
        logger.info(f"Finished create_ann: {stdout} / {stderr}")

        if not store_container_file(
            container_namespace,
            container_id,
            (PosixPath("data") / "main_ann.fann"),
            f"{upload_files_url}/main_ann.fann",
        ):
            return False
        return True


def run_trial_report(
    container_namespace: str,
    container_name: str,
    download_edit_set_url: str,
    download_bins_url: str,
    upload_report_url: str,
    release_ref: str,
) -> bool:
    with run_container(
        namespace=container_namespace,
        name=container_name,
        download_bins_url=download_bins_url,
        download_edit_set_url=download_edit_set_url,
        release_ref=release_ref,
    ) as container_id:
        success, stdout, stderr = execute_in_container(
            container_namespace, container_id, "mkdir -p trialreport && ./cluebotng -c conf -m trial_run -f edits.xml"
        )
        if not success:
            logger.info(f"Trial run failed: {stdout} / {stderr}")
            return False
        logger.info(f"Finished trial_run: {stdout}")

        # Stash results
        is_success = True
        for file_name in [
            "debug.xml",
            "details.txt",
            "falsenegatives.txt",
            "falsepositives.txt",
            "report.txt",
            "thresholdtable.txt",
        ]:
            if not store_container_file(
                container_namespace,
                container_id,
                (PosixPath("trialreport") / file_name),
                f"{upload_report_url}/{file_name}",
            ):
                logger.warning(f"Failed to store {file_name}")
                is_success &= False
        return is_success


def store_edit_sets(container_namespace: str, container_name: Optional[str], mapping: Dict[str, str]) -> bool:
    with run_container(namespace=container_namespace, name=container_name, skip_setup=True) as container_id:
        is_success = True
        for download_url, upload_url in mapping.items():
            # Download to a temp file
            temp_path = f"/tmp/{uuid.uuid4().hex}"

            logger.info(f"Downloading {download_url} to {temp_path}")
            success, stdout, stderr = execute_in_container(
                container_namespace,
                container_id,
                f"curl -sL --output '{temp_path}' '{download_url}'",
            )
            if not success:
                logger.error(f"Failed to download: {stdout} / {stderr}")
                return False

            if not store_container_file(
                container_namespace,
                container_id,
                PosixPath(temp_path),
                upload_url,
            ):
                logger.warning(f"Failed to store {upload_url}")
                is_success &= False
        return is_success


def create_plots(
    container_namespace: str, container_name: Optional[str], image_tag: str, upload_report_url: str
) -> bool:
    with run_container(
        namespace=container_namespace,
        name=container_name,
        skip_setup=True,
        override_file_urls={
            "thresholdtable.txt": f"{upload_report_url}/thresholdtable.txt",
        },
        image=image_tag,
    ) as container_id:
        logger.info("Generating plots")
        is_success = True
        for name, plot in {
            "falsepositives": """
set terminal png
set output '/tmp/cbng-core/data/falsepositives.png'

set title 'Vandalism Detection Rate by False Positives'
set xlabel 'False Positive Rate'
set ylabel 'Portion of Vandalism'
set xrange [0.0:0.02]
set grid

plot '/tmp/cbng-core/data/thresholdtable.txt' using 3:2 title 'Vandalism Detection Rate' with lines
            """,
            "thresholds": """
set terminal png
set output '/tmp/cbng-core/data/thresholds.png'

set title 'Detection Rates By Threshold'
set xlabel 'Score Vandalism Threshold'
set ylabel 'Detection Rate'

plot '/tmp/cbng-core/data/thresholdtable.txt' using 1:2 title 'Correct Positive %' with lines, '/tmp/cbng-core/data/thresholdtable.txt' using 1:3 title 'False Positive %' with lines
            """,
        }.items():
            success, stdout, stderr = execute_in_container(
                container_namespace,
                container_id,
                f'base64 -d <<<{base64.b64encode(plot.encode("utf-8")).decode("utf-8")} > /tmp/{name}.gnuplot',
            )
            if not success:
                logger.error(f"Could not write plot: {stdout} / {stderr}")
                return False

            # Note: non-standard path from pack
            success, stdout, stderr = execute_in_container(
                container_namespace,
                container_id,
                f"launcher gnuplot-qt /tmp/{name}.gnuplot",
            )
            if not success:
                logger.error(f"Failed to generate plot: {stdout} / {stderr}")
                is_success &= False
            else:
                logger.error(f"Generated plot: {stdout}")
                if not store_container_file(
                    container_namespace,
                    container_id,
                    PosixPath("/tmp/cbng-core/data") / f"{name}.png",
                    f"{upload_report_url}/{name}.png",
                ):
                    logger.warning(f"Failed to store {f'{name}.png'}")
                    is_success &= False
        return is_success
