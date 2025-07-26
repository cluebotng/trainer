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
import hashlib
import logging
import sys
import time
from datetime import datetime, timezone
from pathlib import PosixPath
from typing import Optional, List

import click

from cbng_trainer.api import FileApi
from cbng_trainer.common import steps
from cbng_trainer.common.files import calculate_target_path
from cbng_trainer.common.steps import (
    store_edit_sets,
    run_bayes_train,
    create_main_bayes_db,
    create_two_bayes_db,
    run_ann_train,
    run_create_ann,
    create_plots,
)
from cbng_trainer.common.toolforge import launch_job, job_has_completed
from cbng_trainer.common.utils import (
    get_target_edit_groups,
    get_latest_github_release,
)

logger = logging.getLogger(__name__)


@click.group()
def cli() -> None:
    logging.basicConfig(level=logging.INFO, stream=sys.stderr)


# "Job runner" - spawns kubernetes pods to run through our steps
@cli.command()
# Run specific
@click.option("--target-name", required=True)
@click.option("--instance-name", required=True)
@click.option("--download-training", required=True)
@click.option("--download-trial", required=False)
# Internal
@click.option("--kubernetes-namespace", required=True)
@click.option("--container-image", default="tool-cluebotng-trainer/backend-service:latest", required=True)
@click.option("--release-ref", required=True)
@click.option("--trainer-host", required=True)
def run_edit_set(
    target_name: str,
    instance_name: str,
    kubernetes_namespace: str,
    container_image: str,
    release_ref: str,
    trainer_host: str,
    download_training: str,
    download_trial: Optional[str],
) -> None:
    job_id = hashlib.sha256(target_name.encode("utf-8")).hexdigest()[0:30]

    # Download the files
    files_to_download = {
        download_training: calculate_target_path(trainer_host, target_name, instance_name, "edit-sets", "train.xml")
    }
    if download_trial:
        files_to_download |= {
            download_trial: calculate_target_path(trainer_host, target_name, instance_name, "edit-sets", "trial.xml")
        }

    logger.info("Downloading files")
    if not store_edit_sets(
        container_namespace=kubernetes_namespace,
        container_name=f"{job_id}-download",
        mapping=files_to_download,
    ):
        return

    # Build
    logger.info("Running bayes train")
    if not run_bayes_train(
        download_edit_set_url=files_to_download[download_training],
        upload_files_url=calculate_target_path(trainer_host, target_name, instance_name, "artifacts"),
        container_namespace=kubernetes_namespace,
        container_name=f"{job_id}-bayes-train",
        release_ref=release_ref,
    ):
        return

    logger.info("Creating main bayes database")
    if not create_main_bayes_db(
        download_edit_set_url=files_to_download[download_training],
        upload_files_url=calculate_target_path(trainer_host, target_name, instance_name, "artifacts"),
        container_namespace=kubernetes_namespace,
        container_name=f"{job_id}-main-bayes-db",
        release_ref=release_ref,
    ):
        return

    logger.info("Creating two bayes database")
    if not create_two_bayes_db(
        download_edit_set_url=files_to_download[download_training],
        upload_files_url=calculate_target_path(trainer_host, target_name, instance_name, "artifacts"),
        container_namespace=kubernetes_namespace,
        container_name=f"{job_id}-two-bayes-db",
        release_ref=release_ref,
    ):
        return

    logger.info("Running ann train")
    if not run_ann_train(
        download_edit_set_url=files_to_download[download_training],
        upload_files_url=calculate_target_path(trainer_host, target_name, instance_name, "artifacts"),
        container_namespace=kubernetes_namespace,
        container_name=f"{job_id}-ann-train",
        release_ref=release_ref,
    ):
        return

    logger.info("Running ann create")
    if not run_create_ann(
        download_edit_set_url=files_to_download[download_training],
        upload_files_url=calculate_target_path(trainer_host, target_name, instance_name, "artifacts"),
        container_namespace=kubernetes_namespace,
        container_name=f"{job_id}-ann-create",
        release_ref=release_ref,
    ):
        return

    # Run trial
    if download_trial:
        logger.info("Executing trial")
        steps.run_trial_report(
            download_edit_set_url=files_to_download[download_trial],
            download_bins_url=calculate_target_path(trainer_host, target_name, instance_name, "artifacts"),
            upload_report_url=calculate_target_path(trainer_host, target_name, instance_name, "trial"),
            container_namespace=kubernetes_namespace,
            container_name=f"{job_id}-trial",
            release_ref=release_ref,
        )

        logger.info("Creating plots via API")
        create_plots(
            container_namespace=kubernetes_namespace,
            container_name=f"{job_id}-create-plots",
            image_tag=container_image,
            upload_report_url=calculate_target_path(trainer_host, target_name, instance_name, "trial"),
        )


# "Job coordinator" - figures out which groups we need to perform a run for and creates a job for each
@cli.command()
@click.option("--edit-set", multiple=True, default=None)
@click.option("--print-only/--no-print-only", default=False)
# These are essentially constants
@click.option("--toolforge-user", default="cluebotng-trainer", required=True)
@click.option("--kubernetes-namespace", default="tool-cluebotng-trainer", required=True)
@click.option(
    "--container-image", default="tools-harbor.wmcloud.org/tool-cluebotng-trainer/backend-service:latest", required=True
)
@click.option(
    "--review-host", default="http://cluebotng-review.tool-cluebotng-review.svc.tools.local:8000", required=True
)
@click.option(
    "--trainer-host", default="http://cluebotng-trainer.tool-cluebotng-trainer.svc.tools.local:8000", required=True
)
@click.option("--release-ref", required=False)
def run_edit_sets(
    edit_set: List[str],
    print_only: bool,
    toolforge_user: str,
    kubernetes_namespace: str,
    container_image: str,
    review_host: str,
    trainer_host: str,
    release_ref: Optional[str],
) -> None:
    if not release_ref:
        release_ref = get_latest_github_release("cluebotng", "core")
    target_groups = get_target_edit_groups(review_host, edit_set)

    run_instance = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S")

    targets = []
    for target_name, groups in target_groups.items():
        if ("Training" in groups or "Reported False Positives" in groups) and "Trial" not in groups:
            if sampled_group_id := target_groups.get("Sampled Main Namespace Edits", {}).get("Generic"):
                logger.info(f"Using sampled edits as fallback trial group for {target_name}")
                groups["Trial"] = sampled_group_id

        for group_name, group_id in groups.items():
            # We will use the training set, no need to download the redundant file
            if group_name == "Generic" and "Training" in groups:
                logger.warning(f"Ignoring generic group in place of training for {target_name}")
                continue

            if group_name == "Generic" and "Reported False Positives" in groups:
                logger.warning(f"Ignoring generic group in place of reported false positives for {target_name}")
                continue

            if group_name == "Trial":
                logger.debug("Ignoring trial group")
                continue

            script = [
                "cbng-trainer",
                "run-edit-set",
                f'--kubernetes-namespace="{kubernetes_namespace}"',
                f'--target-name="{target_name}"',
                f'--container-image="{container_image}"',
                f'--instance-name="{run_instance}"',
                f'--release-ref="{release_ref}"',
                f'--trainer-host="{trainer_host}"',
            ]
            if group_name in {"Generic", "Reported False Positives", "Training"}:
                script.append(f'--download-training="{review_host}/api/v1/edit-groups/{group_id}/dump-editset/"')
            if "Trial" in groups:
                script.append(f'--download-trial="{review_host}/api/v1/edit-groups/{groups["Trial"]}/dump-editset/"')

            if print_only:
                print(" ".join(script))
                print("")
            else:
                job_id = hashlib.sha256(target_name.encode("utf-8")).hexdigest()[0:30]
                targets.append(
                    (
                        f"coord-{job_id}",
                        " ".join(script),
                    )
                )

    for container_name, script in targets:
        launch_job(
            target_user=toolforge_user,
            name=container_name,
            image=container_image,
            command=script,
        )

        while True:
            if job_has_completed(toolforge_user, container_name):
                logger.info(f"Job has completed: {container_name}")
                break

            logger.info(f"Waiting for job to complete: {container_name}")
            time.sleep(1)


@cli.command()
@click.option("--base-dir", type=click.Path(), default="/data/project/cluebotng-trainer/public_html")
def run_file_api(base_dir: str) -> None:
    file_api = FileApi(PosixPath(base_dir))
    file_api.run()


if __name__ == "__main__":
    cli()
