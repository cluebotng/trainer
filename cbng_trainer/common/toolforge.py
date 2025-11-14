import logging
import re
import time
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, List, Any, Tuple, Union

from requests.exceptions import HTTPError, ReadTimeout
from toolforge_weld.api_client import ToolforgeClient
from toolforge_weld.config import load_config
from toolforge_weld.kubernetes_config import Kubeconfig

from cbng_trainer.common.consts import JOB_LOGS_END_MARKER
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
) -> bool:
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
        logger.error(f"Failed to create {job_name}: {e}")
        return False
    return True


def _delete_job(target_user: str, name: str):
    api = _client_config(target_user)
    try:
        api.delete(f"/jobs/v1/tool/{target_user}/jobs/{name}/")
    except HTTPError as e:
        logger.warning(f"Failed to delete {name}: {e}")


def _job_was_successful(target_user: str, name: str) -> bool:
    api = _client_config(target_user)
    try:
        resp = api.get(f"/jobs/v1/tool/{target_user}/jobs/{name}/")
    except HTTPError as e:
        logger.error(f"Failed to get {name}: {e}")
        return False
    return resp["job"]["status_short"] == "Completed" and "Exit code '0'" in resp["job"]["status_long"]


def _job_is_running(target_user: str, name: str) -> bool:
    api = _client_config(target_user)
    try:
        resp = api.get(f"/jobs/v1/tool/{target_user}/jobs/{name}/")
    except HTTPError as e:
        if e.response is None or e.response.status_code != 404:
            logger.error(f"Failed to get {name}: {e}")
        return False

    return "Running for " in resp["job"]["status_short"]


def _wait_for_job_to_start(target_user: str, job_name: str) -> Optional[Union[datetime, bool]]:
    api = _client_config(target_user)
    try:
        resp = api.get(f"/jobs/v1/tool/{target_user}/jobs/{job_name}/")
    except HTTPError as e:
        if e.response is None or e.response.status_code != 404:
            logger.error(f"Failed to get {job_name}: {e}")
        return None

    if resp["job"]["status_short"] == "Failed":
        return False

    if match := re.match(r"^Last run at (.+)\. Pod in 'Running' phase\.", resp["job"]["status_long"]):
        return datetime.fromisoformat(match.group(1))
    return None


def _read_logs(target_user: str, job_name: str, start_time: datetime) -> List[Dict[str, Any]]:
    api = _client_config(target_user)

    logs = []
    try:
        response = api.get(f"/logs/v1/tool/{target_user}/job/{job_name}/logs", timeout=60)
        for log in response["data"]["logs"]:
            log["datetime"] = datetime.fromisoformat(log["datetime"])
            if log["datetime"] >= start_time:
                logs.append(log)
    except (HTTPError, ReadTimeout) as e:
        if e.response is None or e.response.status_code != 404:
            logger.warning(f"Failed to get logs for {job_name}: {e}")
    return logs


def _peak_at_logs(target_user: str, job_name: str, start_time: datetime, seen_logs: List[str]):
    for log in _read_logs(target_user, job_name, start_time):
        # Work around T410055
        if log["pod"] == "nopod" and log["container"] == "nocontainer":
            continue

        log_line = f'{log["datetime"].isoformat()}: {log["message"]}'
        if log_line in seen_logs:
            continue
        # Emit what we have not yet emitted "sad streaming"
        logger.info(f"[{job_name}] {log['message']}")
        seen_logs.append(log_line)


def _wait_for_logs_end_marker(
    target_user: str, job_name: str, start_time: datetime, seen_logs: List[str], timeout: int = 300
):
    waiting_start_time = time.time()
    while True:
        _peak_at_logs(target_user, job_name, start_time, seen_logs)

        for line in seen_logs:
            if line.strip().endswith(f": {JOB_LOGS_END_MARKER}"):
                logger.info(f"[{job_name}] Found log end marker")
                return

        if waiting_start_time + timeout < time.time():
            logger.error(f"[{job_name}] Timed out before log end marker")
            return

        time.sleep(1)


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
    start_timeout: int = 300,
    wait_for_job_logs_marker: bool = True,
) -> Tuple[bool, List[str]]:
    execution_script = generate_execution_script(
        release_ref,
        download_bins_url,
        download_edit_set_url,
        override_file_urls,
        skip_setup,
        skip_binary_setup,
        run_commands,
    )

    logger.info(f"[{job_name}] Creating job")
    job_request_time = datetime.now(timezone.utc)
    if not _run_job(
        target_user=target_user,
        job_name=job_name,
        image=image_name,
        command=generate_command_command(execution_script, run_timeout),
    ):
        return False, []

    if not wait_for_completion:
        return True, []

    logger.info(f"[{job_name}] Waiting for job to start")
    waiting_start_time = datetime.now(tz=timezone.utc)
    while True:
        start_time = _wait_for_job_to_start(
            target_user=target_user,
            job_name=job_name,
        )

        if start_time is not None:
            break

        if waiting_start_time + timedelta(seconds=start_timeout) < datetime.now(tz=timezone.utc):
            logger.error(f"[{job_name}] Job failed to start within timeout")
            return False, []

        time.sleep(0.5)

    seen_logs = []
    if start_time is False:
        logger.error(f"[{job_name}] Job failed to start")
        _peak_at_logs(target_user=target_user, job_name=job_name, start_time=job_request_time, seen_logs=seen_logs)
        _delete_job(target_user, job_name)
        return False, seen_logs

    logger.info(f"[{job_name}] Job started, waiting for job to finish")
    while True:
        _peak_at_logs(target_user=target_user, job_name=job_name, start_time=start_time, seen_logs=seen_logs)

        if not _job_is_running(target_user, job_name):
            break

        time.sleep(1)

    success = _job_was_successful(target_user, job_name)
    if success:
        logger.info(f"[{job_name}] Job succeeded")
    else:
        logger.error(f"[{job_name}] Job failed")

    if wait_for_job_logs_marker and success:
        # If we are a step, then we wait for the explicit end marker
        _wait_for_logs_end_marker(
            target_user=target_user, job_name=job_name, start_time=waiting_start_time, seen_logs=seen_logs
        )
    else:
        # If we are a coord job, then just grab what we have and exit
        _peak_at_logs(target_user=target_user, job_name=job_name, start_time=start_time, seen_logs=seen_logs)

    _delete_job(target_user, job_name)
    return success, seen_logs


def create_or_update_envvar(target_user: str, name: str, value: str) -> None:
    api = _client_config(target_user)

    try:
        resp = api.get(f"/envvars/v1/tool/{target_user}/envvars/{name}")
    except HTTPError as e:
        if e.response is None or e.response.status_code != 404:
            logger.error(f"Failed to get envvar: {e}")
            return

        logger.info(f"Creating envvar {name}")
    else:
        if resp["envvar"]["value"] == value:
            logger.info(f"Skipping envvar {name}, contents matches")
            return
        logger.info(f"Updating envvar {name}")

    try:
        api.post(f"/envvars/v1/tool/{target_user}/envvars", json={"name": name, "value": value})
    except HTTPError as e:
        logger.error(f"Failed to write envvar: {e}")
