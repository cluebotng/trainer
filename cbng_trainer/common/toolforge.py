import functools
import logging
import os
import re
import time
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import requests
import urllib3
import yaml
from requests.exceptions import HTTPError, ReadTimeout

from cbng_trainer.common.consts import JOB_LOGS_END_MARKER
from cbng_trainer.common.utils import generate_command_command, generate_execution_script

logger = logging.getLogger(__name__)

DEFAULT_API_GATEWAY_URL = "https://api.svc.tools.eqiad1.wikimedia.cloud:30003"


@dataclass(frozen=True)
class KubeConfig:
    client_cert_file: Path
    client_key_file: Path


def _resolve_path(base: Path, path: str) -> Path:
    resolved = Path(path).expanduser()
    return resolved if resolved.is_absolute() else (base / resolved).resolve()


@functools.cache
def load_kube_config() -> KubeConfig:
    path = Path(os.environ.get("KUBECONFIG", "~/.kube/config")).expanduser()
    data = yaml.safe_load(path.read_text())

    context = next(c["context"] for c in data["contexts"] if c["name"] == data["current-context"])
    user = next(u["user"] for u in data["users"] if u["name"] == context["user"])
    return KubeConfig(
        client_cert_file=_resolve_path(path.parent, user["client-certificate"]),
        client_key_file=_resolve_path(path.parent, user["client-key"]),
    )


class ToolforgeClient:
    def __init__(self, server: str, kube_config: KubeConfig, timeout: int = 20):
        self.server = server.rstrip("/")
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers["User-Agent"] = "ClueBot NG Trainer"
        self.session.cert = (str(kube_config.client_cert_file), str(kube_config.client_key_file))
        # The API gateway certificate is not signed by the kubeconfig CA (T253412)
        self.session.verify = False
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

    def _request(self, method: str, url: str, **kwargs) -> dict[str, Any]:
        kwargs.setdefault("timeout", self.timeout)
        response = self.session.request(method, f"{self.server}/{url.lstrip('/')}", **kwargs)
        response.raise_for_status()
        return response.json()

    def get(self, url: str, **kwargs) -> dict[str, Any]:
        return self._request("GET", url, **kwargs)

    def post(self, url: str, **kwargs) -> dict[str, Any]:
        return self._request("POST", url, **kwargs)

    def delete(self, url: str, **kwargs) -> dict[str, Any]:
        return self._request("DELETE", url, **kwargs)


@functools.cache
def _client_config(target_user: str) -> ToolforgeClient:
    return ToolforgeClient(
        server=os.environ.get("TOOL_TOOLFORGE_API_URL", DEFAULT_API_GATEWAY_URL),
        kube_config=load_kube_config(),
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
        if e.response is None or e.response.status_code != 404:
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


def _wait_for_job_to_start(target_user: str, job_name: str) -> datetime | bool | None:
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


def _read_logs(target_user: str, job_name: str, start_time: datetime) -> list[dict[str, Any]]:
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


def _peak_at_logs(target_user: str, job_name: str, start_time: datetime, seen_logs: list[tuple[datetime, str]]):
    for log in _read_logs(target_user, job_name, start_time):
        # Work around T410055
        if log["pod"] == "nopod" and log["container"] == "nocontainer":
            continue

        log_line = f'{log["datetime"].isoformat()}: {log["message"]}'
        if (log["datetime"], log_line) in seen_logs:
            continue
        # Emit what we have not yet emitted "sad streaming"
        logger.info(f"[{job_name}] {log['message']}")
        seen_logs.append((log["datetime"], log_line))


def _wait_for_logs_end_marker(
    target_user: str, job_name: str, start_time: datetime, seen_logs: list[tuple[datetime, str]], timeout: int = 300
):
    waiting_start_time = time.time()
    checked_up_to = 0
    while True:
        _peak_at_logs(target_user, job_name, start_time, seen_logs)

        for _, line in seen_logs[checked_up_to:]:
            if line.strip().endswith(f": {JOB_LOGS_END_MARKER}"):
                logger.info(f"[{job_name}] Found log end marker")
                return
        checked_up_to = len(seen_logs)

        if waiting_start_time + timeout < time.time():
            logger.error(f"[{job_name}] Timed out before log end marker")
            return

        time.sleep(1)


def run_job(
    target_user: str,
    job_name: str,
    image_name: str,
    download_file_urls: dict[str, str] | None = None,
    run_commands: list[str] | None = None,
    wait_for_completion: bool = True,
    run_timeout: int = 7200,
    start_timeout: int = 300,
    wait_for_job_logs_marker: bool = True,
    configure_upload_file_helper: bool | None = None,
) -> tuple[bool, list[tuple[datetime, str]]]:
    execution_script = generate_execution_script(
        download_file_urls=download_file_urls,
        run_commands=run_commands,
        configure_upload_file_helper=configure_upload_file_helper is True
        or (
            configure_upload_file_helper is None
            and run_commands is not None
            and any(run_command.strip().startswith("upload_file") for run_command in run_commands)
        ),
    )

    logger.info(f"[{job_name}] Creating job")
    job_request_time = datetime.now(UTC)
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
    waiting_start_time = datetime.now(tz=UTC)
    while True:
        start_time = _wait_for_job_to_start(
            target_user=target_user,
            job_name=job_name,
        )

        if start_time is not None:
            break

        if waiting_start_time + timedelta(seconds=start_timeout) < datetime.now(tz=UTC):
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

    if wait_for_job_logs_marker:
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
