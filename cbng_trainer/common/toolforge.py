import logging
import os
from urllib.parse import urlparse

from requests import HTTPError
from toolforge_weld.api_client import ToolforgeClient
from toolforge_weld.config import load_config
from toolforge_weld.kubernetes_config import Kubeconfig

logger = logging.getLogger(__name__)


def _client_config():
    try:
        # The common config isn't mounted in the container, so fallback to a known value
        config = load_config("cluebotng-trainer")
        server = f"{config.api_gateway.url}{config.jobs.jobs_endpoint}"
    except KeyError:
        server = os.environ.get("TOOL_TOOLFORGE_API_URL", "https://localhost:30003")

    return ToolforgeClient(
        server=server,
        kubeconfig=Kubeconfig.load(),
        user_agent="ClueBot NG Trainer",
    )


def launch_job(
    target_user: str,
    name: str,
    image: str,
    command: str,
):
    api = _client_config()
    try:
        api.post(
            f"/jobs/v1/tool/{target_user}/jobs/",
            json={
                "name": name,
                "imagename": image.replace("tools-harbor.wmcloud.org/", ""),  # host is implicit
                "cmd": command,
            },
        )
    except HTTPError as e:
        logger.error(f"Failed to create {name}: [{e.response.status_code}] {e.response.text}")


def job_has_completed(target_user: str, name: str) -> bool:
    api = _client_config()
    try:
        resp = api.get(f"/jobs/v1/tool/{target_user}/jobs/{name}/")
    except HTTPError as e:
        logger.error(f"Failed to get {name}: [{e.response.status_code}] {e.response.text}")
        return False

    if "Running for " in resp["job"]["status_short"]:
        return False

    return True
