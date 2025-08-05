import json
import logging
import re
import time
from datetime import datetime
from typing import Optional, Dict, List, Any

from requests import HTTPError
from toolforge_weld.api_client import ToolforgeClient
from toolforge_weld.config import load_config
from toolforge_weld.kubernetes_config import Kubeconfig

from cbng_trainer.common.utils import generate_execution_script, generate_command_command

logger = logging.getLogger(__name__)


def _client_config(target_user: str):
    config = load_config(target_user)
    return ToolforgeClient(
        server=f"{config.api_gateway.url}",
        kubeconfig=Kubeconfig.load(),
        user_agent="ClueBot NG Trainer",
    )


def _run_job(
    target_user: str,
    job_name: str,
    image: str,
    command: str,
):
    logger.info(f"Starting job {job_name}")
    api = _client_config(target_user)
    try:
        api.post(
            f"/jobs/v1/tool/{target_user}/jobs/",
            json={
                "name": job_name,
                "imagename": image.replace("tools-harbor.wmcloud.org/", ""),  # host is implicit
                "cmd": command,
                "mount": "none",
            },
        )
    except HTTPError as e:
        raise Exception(f"Failed to create {job_name}: [{e.response.status_code}] {e.response.text}")


def _job_was_successful(target_user: str, name: str) -> bool:
    api = _client_config(target_user)
    try:
        resp = api.get(f"/jobs/v1/tool/{target_user}/jobs/{name}/")
    except HTTPError as e:
        logger.error(f"Failed to get {name}: [{e.response.status_code}] {e.response.text}")
        return False

    return resp["job"]["status_short"] == "Completed" and "Exit code '0'" in resp["job"]["status_long"]


def _job_is_running(target_user: str, name: str) -> bool:
    api = _client_config(target_user)
    try:
        resp = api.get(f"/jobs/v1/tool/{target_user}/jobs/{name}/")
    except HTTPError as e:
        if e.response.status_code == 404:
            return False
        logger.error(f"Failed to get {name}: [{e.response.status_code}] {e.response.text}")
        return False

    return "Running for " in resp["job"]["status_short"]


def _wait_for_job_to_start(target_user: str, job_name: str) -> Optional[datetime]:
    api = _client_config(target_user)
    try:
        resp = api.get(f"/jobs/v1/tool/{target_user}/jobs/{job_name}/")
    except HTTPError as e:
        if e.response.status_code == 404:
            return None
        logger.error(f"Failed to get {job_name}: [{e.response.status_code}] {e.response.text}")
        return None

    if match := re.match(r"^Last run at (.+)\. Pod in 'Running' phase\.", resp["job"]["status_long"]):
        return datetime.fromisoformat(match.group(1))
    return None


def _read_logs(target_user: str, job_name: str, start_time: datetime) -> List[Dict[str, Any]]:
    api = _client_config(target_user)

    logs = []
    for raw_line in api.get_raw_lines(
        f"/jobs/v1/tool/{target_user}/jobs/{job_name}/logs/",
        params={"follow": "false"},
        timeout=10,
    ):
        log = json.loads(raw_line)
        log["datetime"] = datetime.fromisoformat(log["datetime"])
        if log["datetime"] >= start_time:
            logs.append(log)
    return logs


def _peak_at_logs(target_user: str, job_name: str, start_time: datetime, seen_logs: List[str]):
    for log in _read_logs(target_user, job_name, start_time):
        log_line = f'[{log["pod"]}] {log["datetime"].isoformat()}: {log["message"]}'
        if log_line in seen_logs:
            continue
        # Emit what we have not yet emitted "sad streaming"
        logger.info(log_line)
        seen_logs.append(log_line)


def number_of_running_jobs(target_user: str) -> Optional[int]:
    api = _client_config(target_user)
    try:
        resp = api.get(f"/jobs/v1/tool/{target_user}/jobs/")
    except HTTPError as e:
        logger.error(f"Failed to get jobs: [{e.response.status_code}] {e.response.text}")
        return None

    return len([job for job in resp["jobs"] if "Running for " in job["status_short"]])


def run_job(
    target_user: str,
    job_name: str,
    image_name: str,
    release_ref: Optional[str] = None,
    download_edit_set_url: Optional[str] = None,
    download_bins_url: Optional[str] = None,
    override_file_urls: Optional[Dict[str, str]] = None,
    run_commands: Optional[List[str]] = None,
    skip_setup: bool = False,
    skip_binary_setup: bool = False,
    wait_for_completion: bool = True,
    run_timeout: str = "2h",
):
    execution_script = generate_execution_script(
        release_ref,
        download_bins_url,
        download_edit_set_url,
        override_file_urls,
        skip_setup,
        skip_binary_setup,
        run_commands,
    )

    _run_job(
        target_user=target_user,
        job_name=job_name,
        image=image_name,
        command=generate_command_command(execution_script, run_timeout),
    )

    if not wait_for_completion:
        return True

    while True:
        start_time = _wait_for_job_to_start(
            target_user=target_user,
            job_name=job_name,
        )
        if start_time is not None:
            break
        time.sleep(0.5)

    seen_logs = []
    logger.debug("Waiting for job to finish")
    while True:
        _peak_at_logs(target_user=target_user, job_name=job_name, start_time=start_time, seen_logs=seen_logs)

        if not _job_is_running(target_user, job_name):
            logger.info("Job has stopped running")
            break

        time.sleep(1)

    _peak_at_logs(target_user=target_user, job_name=job_name, start_time=start_time, seen_logs=seen_logs)
    return _job_was_successful(target_user, job_name)
