import logging
import os

from requests import HTTPError
from toolforge_weld.api_client import ToolforgeClient
from toolforge_weld.config import load_config
from toolforge_weld.kubernetes_config import Kubeconfig

logger = logging.getLogger(__name__)


def _client_config():
    tool_name = os.environ.get("TOOL_NAME", "cluebotng-trainer")
    config = load_config(tool_name)
    return ToolforgeClient(
        server=f"{config.api_gateway.url}",
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
