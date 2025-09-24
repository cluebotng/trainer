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
import logging
import sys
import time
from datetime import datetime, timezone
from typing import Optional, List

import click

from cbng_trainer.common.files import calculate_target_path
from cbng_trainer.common.steps import Steps
from cbng_trainer.common.toolforge import run_job, number_of_running_jobs
from cbng_trainer.common.utils import (
    get_target_edit_groups,
    get_latest_github_release,
    clean_job_name,
)

logger = logging.getLogger(__name__)


@click.group()
def cli() -> None:
    logging.basicConfig(level=logging.INFO, stream=sys.stderr, format="%(asctime)s [%(levelname)s] %(message)s")


# "Job runner" - spawns kubernetes pods to run through our steps
@cli.command()
# Run specific
@click.option("--target-name", required=True)
@click.option("--instance-name", required=True)
@click.option("--download-training", required=True)
@click.option("--download-trial", required=False)
# Internal
@click.option("--toolforge-user", default="cluebotng-trainer", required=True)
@click.option("--image-name", required=True)
@click.option("--release-ref", required=True)
@click.option("--trainer-host", required=True)
def run_edit_set(
    target_name: str,
    instance_name: str,
    toolforge_user: str,
    image_name: str,
    release_ref: str,
    trainer_host: str,
    download_training: str,
    download_trial: Optional[str],
) -> None:
    steps = Steps(
        toolforge_user=toolforge_user,
        target_name=target_name,
        image_name=image_name,
        release_ref=release_ref,
        upload_logs=calculate_target_path(trainer_host, target_name, instance_name, "logs"),
    )

    # Download the files
    files_to_download = {
        download_training: calculate_target_path(trainer_host, target_name, instance_name, "edit-sets", "train.xml")
    }
    if download_trial:
        files_to_download |= {
            download_trial: calculate_target_path(trainer_host, target_name, instance_name, "edit-sets", "trial.xml")
        }

    # logger.info("Downloading files")
    if not steps.store_edit_sets(mapping=files_to_download):
        logger.error("Downloading files failed")
        return

    # Build
    logger.info("Running bayes train")
    if not steps.run_bayes_train(
        download_edit_set_url=files_to_download[download_training],
        upload_files_url=calculate_target_path(trainer_host, target_name, instance_name, "artifacts"),
    ):
        logger.error("Bayes train failed")
        return

    logger.info("Creating bayes databases")
    if not steps.create_main_bayes_db(
        download_edit_set_url=files_to_download[download_training],
        upload_files_url=calculate_target_path(trainer_host, target_name, instance_name, "artifacts"),
    ):
        logger.error("Main main bayes db failed")
        return

    logger.info("Creating two bayes databases")
    if not steps.create_two_bayes_db(
        download_edit_set_url=files_to_download[download_training],
        upload_files_url=calculate_target_path(trainer_host, target_name, instance_name, "artifacts"),
    ):
        logger.error("Two bayes db failed")
        return

    logger.info("Running ann train")
    if not steps.run_ann_train(
        download_edit_set_url=files_to_download[download_training],
        upload_files_url=calculate_target_path(trainer_host, target_name, instance_name, "artifacts"),
    ):
        logger.error("Ann train failed")
        return

    logger.info("Running ann create")
    if not steps.run_create_ann(
        download_edit_set_url=files_to_download[download_training],
        upload_files_url=calculate_target_path(trainer_host, target_name, instance_name, "artifacts"),
    ):
        logger.error("Ann create failed")
        return

    # Run trial
    if download_trial:
        logger.info("Executing trial")
        if not steps.run_trial_report(
            download_edit_set_url=files_to_download[download_trial],
            download_bins_url=calculate_target_path(trainer_host, target_name, instance_name, "artifacts"),
            upload_report_url=calculate_target_path(trainer_host, target_name, instance_name, "trial"),
        ):
            logger.error("Trial report failed")
            return

        logger.info("Creating plots")
        if not steps.create_plots(
            upload_report_url=calculate_target_path(trainer_host, target_name, instance_name, "trial"),
        ):
            logger.error("Result plotting failed")
            return


# "Job coordinator" - figures out which groups we need to perform a run for and creates a job for each
@cli.command()
@click.option("--edit-set", multiple=True, default=None)
@click.option("--print-only/--no-print-only", default=False)
# These are essentially constants
@click.option("--toolforge-user", default="cluebotng-trainer", required=True)
@click.option("--max-jobs", default=1, required=True)
@click.option("--image-name", default="tools-harbor.wmcloud.org/tool-cluebotng-trainer/trainer:latest", required=True)
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
    image_name: str,
    review_host: str,
    trainer_host: str,
    release_ref: Optional[str],
    max_jobs: int,
) -> None:
    if not release_ref:
        release_ref = get_latest_github_release("cluebotng", "core")
    target_groups = get_target_edit_groups(review_host, edit_set)

    run_instance = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S")

    targets = []
    for target_name, groups in target_groups.items():
        if ("Training" in groups or "Reported False Positives" in groups) and "Trial" not in groups:
            if sampled_group_id := target_groups.get("Original Testing Training Set - Random Edits 50/50", {}).get(
                "Trial"
            ):
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
                "launcher",
                "cbng-trainer",
                "run-edit-set",
                f'--image-name="{image_name}"',
                f'--target-name="{target_name}"',
                f'--instance-name="{run_instance}"',
                f'--release-ref="{release_ref}"',
                f'--trainer-host="{trainer_host}"',
            ]
            if group_name in {"Generic", "Reported False Positives", "Training"}:
                script.append(
                    f'--download-training="{review_host.rstrip("/")}/api/v1/edit-groups/{group_id}/dump-editset/"'
                )
            if "Trial" in groups:
                script.append(
                    f'--download-trial="{review_host.rstrip("/")}/api/v1/edit-groups/{groups["Trial"]}/dump-editset/"'
                )

            if print_only:
                print(" ".join(script))
                print("")
            else:
                targets.append(
                    (
                        clean_job_name(target_name, prefix="coord"),
                        " ".join(script),
                    )
                )

    # We get 15 total one-off jobs
    # Each coord will spawn 1 child at a time, so each job counts for 2
    # We also need 1 for ourselves so 15 - 1 = 14, 14/2 = 7...
    for container_name, script in targets:
        if max_jobs > 1:
            while True:
                currently_running_jobs = number_of_running_jobs(toolforge_user, "coord-")
                if currently_running_jobs is not None and currently_running_jobs < max_jobs:
                    logger.info(f"Have quota [{currently_running_jobs} vs {max_jobs}]... spawning")
                    break

                logger.info(f"Have no quota [{currently_running_jobs} vs {max_jobs}]... waiting")
                time.sleep(1)

        success, _ = run_job(
            target_user=toolforge_user,
            job_name=container_name,
            image_name=image_name,
            skip_setup=True,
            run_commands=[script],
            wait_for_completion=(max_jobs == 1),
            wait_for_job_logs_marker=False,
        )
        if not success:
            logger.warning(f"Job failed for {container_name}")


if __name__ == "__main__":
    cli()
