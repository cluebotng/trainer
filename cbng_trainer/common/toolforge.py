import json
import logging
import time
from typing import Optional, Dict, List

from requests import HTTPError
from toolforge_weld.api_client import ToolforgeClient
from toolforge_weld.config import load_config
from toolforge_weld.kubernetes_config import Kubeconfig

from cbng_trainer.common.kubernetes import get_pod_name_for_job, is_container_running
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


def _read_logs(target_user: str, job_name: str) -> List:
    api = _client_config(target_user)

    log_lines = []
    for raw_line in api.get_raw_lines(
        f"/jobs/v1/tool/{target_user}/jobs/{job_name}/logs/",
        params={"follow": "false"},
        timeout=None,
    ):
        parsed = json.loads(raw_line)
        log_lines.append(f"[{parsed['pod']}] {parsed['message']}")

    return log_lines


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

    kubernetes_namespace = f"tool-{target_user}"
    job_has_been_running = False
    while True:
        if _job_is_running(target_user, job_name):
            job_has_been_running = True
            pod_name = get_pod_name_for_job(kubernetes_namespace, job_name)
            if is_container_running(kubernetes_namespace, pod_name):
                logger.info("Container has actually started...")
                break
            logger.info("Job is running, but container is not...")
        else:
            if job_has_been_running:
                logger.error("Job is not running, but was previously... likely failed")
                return False
            logger.info("Job is not running...")
        time.sleep(1)

    logs = []
    logger.debug("Waiting for job to finish")
    while True:
        if not _job_is_running(target_user, job_name):
            logger.info("Job is no longer running...")
            for line in logs:
                logger.info(line)
            break

        logger.debug("Job is still running, grabbing logs...")
        logs = _read_logs(target_user=target_user, job_name=job_name)
        time.sleep(1)

    return _job_was_successful(target_user, job_name)
