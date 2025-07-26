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
import time
import uuid
from contextlib import contextmanager
from pathlib import PosixPath
from typing import Optional, Dict, Tuple

import urllib3
from kubernetes import config
from kubernetes.client import ApiException
from kubernetes.client.api import core_v1_api
from kubernetes.stream import stream
from kubernetes.stream.ws_client import ERROR_CHANNEL

logger = logging.getLogger(__name__)


def _get_client():
    urllib3.disable_warnings()
    config.load_kube_config()
    return core_v1_api.CoreV1Api()


def _generate_launch_script(
    release_ref: str,
    download_bins_url: Optional[str] = None,
    download_edit_set_url: Optional[str] = None,
    override_file_urls: Optional[Dict[str, str]] = None,
    run_core: bool = True,
    skip_setup: bool = False,
) -> str:
    setup_script = "#!/bin/bash\n"
    setup_script += "set -xe\n"
    setup_script += "mkdir -p /tmp/cbng-core/data\n"

    if not skip_setup:
        setup_script += f"""
        # Binaries we need to run
        for bin in cluebotng create_ann create_bayes_db print_bayes_db;
        do
            curl -sL --output /tmp/cbng-core/$bin https://github.com/cluebotng/core/releases/download/{release_ref}/$bin
            chmod 755 /tmp/cbng-core/$bin
        done
    
        # Config we need to run
        curl -sL --output /tmp/conf.tar.gz https://github.com/cluebotng/core/releases/download/{release_ref}/conf.tar.gz
        tar -C /tmp/cbng-core/ -xvf /tmp/conf.tar.gz
    
        # Hack to not require a tty
        sed -i s'/, "train_outputs"//g' /tmp/cbng-core/conf/cluebotng.conf
        """

        download_url = (
            download_bins_url
            if download_bins_url
            else f"https://github.com/cluebotng/core/releases/download/{release_ref}"
        )
        files_to_download = {
            "bayes.db": f"{download_url}/bayes.db",
            "two_bayes.db": f"{download_url}/two_bayes.db",
            "main_ann.fann": f"{download_url}/main_ann.fann",
        }
    else:
        files_to_download = {}

    for name, url in (override_file_urls or {}).items():
        if url is None:
            if name in files_to_download:
                del files_to_download[name]
            continue
        files_to_download[name] = url

    setup_script += "# Release database\n"
    for name, url in files_to_download.items():
        setup_script += f"curl -sL --output '/tmp/cbng-core/data/{name}' '{url}'\n"

    if download_edit_set_url:
        setup_script += f"curl -sL --output /tmp/cbng-core/edits.xml {download_edit_set_url}\n"

    if run_core:
        setup_script += "cd /tmp/cbng-core && ./cluebotng -l -m live_run"
    else:
        setup_script += "touch /tmp/container_ready\n"
        setup_script += "sleep infinity\n"

    return setup_script


def _launch_container(
    namespace: str,
    name: str,
    setup_script: str,
    run_core: bool,
    timeout: int,
    image: str,
):
    encoded_script = base64.b64encode(setup_script.encode("utf-8")).decode("utf-8")

    probe = {"tcpSocket": {"port": 3565}} if run_core else {"exec": {"command": ["test", "-f", "/tmp/container_ready"]}}

    # Create the pod
    core_v1 = _get_client()
    core_v1.create_namespaced_pod(
        body={
            "apiVersion": "v1",
            "kind": "Pod",
            "metadata": {
                "name": name,
                "labels": {
                    "toolforge": "tool",
                    "toolforge.org/mount-storage": "none",
                },
            },
            "spec": {
                "containers": [
                    {
                        "image": image,
                        "name": name,
                        "command": [
                            "/bin/bash",
                            "-c",
                            f"base64 -d <<<{encoded_script} > /tmp/setup.sh && "
                            "chmod 755 /tmp/setup.sh && "
                            "/tmp/setup.sh",
                        ],
                        "env": [
                            # Ensure we have the required secret for the file api
                            {
                                "name": "CBNG_TRAINER_FILE_API_KEY",
                                "valueFrom": {
                                    "secretKeyRef": {
                                        "key": "CBNG_TRAINER_FILE_API_KEY",
                                        "name": "toolforge.envvar.v1.cbng-trainer-file-api-key",
                                    }
                                },
                            }
                        ],
                        "ports": [{"containerPort": 3565, "protocol": "TCP"}] if run_core else [],
                        "readinessProbe": probe,
                        "livenessProbe": probe,
                    }
                ],
            },
        },
        namespace=namespace,
    )

    # Wait for the container to start
    start_time = time.time()
    while True:
        resp = core_v1.read_namespaced_pod(name=name, namespace=namespace)
        if resp.status.phase == "Running":
            break
        if time.time() > start_time + timeout:
            raise Exception("Container did not reach running status before timeout")
        time.sleep(1)

    # Wait for the readiness probe aka we finished the setup script
    while True:
        resp = core_v1.read_namespaced_pod_status(name=name, namespace=namespace)
        if all([container_status.ready for container_status in resp.status.container_statuses]):
            break
        if time.time() > start_time + timeout:
            raise Exception("Container did not become healthy before timeout")
        time.sleep(1)


@contextmanager
def run_container(
    namespace: str,
    name: Optional[str] = None,
    release_ref: Optional[str] = None,
    download_edit_set_url: Optional[str] = None,
    download_bins_url: Optional[str] = None,
    override_file_urls: Optional[Dict[str, str]] = None,
    run_core: bool = False,
    skip_setup: bool = False,
    timeout: int = 60,
    image: str = "docker-registry.tools.wmflabs.org/toolforge-bookworm-sssd:latest",
):
    if not name:
        name = uuid.uuid4().hex
    setup_script = _generate_launch_script(
        release_ref, download_bins_url, download_edit_set_url, override_file_urls, run_core, skip_setup
    )

    logger.info(f"Spawning container {name} in {namespace}")
    try:
        _launch_container(
            namespace=namespace,
            name=name,
            image=image,
            setup_script=setup_script,
            run_core=run_core,
            timeout=timeout,
        )

        yield name
    finally:
        stop_container(namespace, name)


def stop_container(ns: str, name: str):
    core_v1 = _get_client()
    try:
        core_v1.delete_namespaced_pod(name=name, namespace=ns)
    except Exception as e:
        # Ignore if the container does not exist - we are trying to remove it
        if isinstance(e, ApiException) and e.status != 404:
            raise e


def execute_in_container(ns: str, name: str, command: str) -> Tuple[bool, str, str]:
    core_v1 = _get_client()
    resp = stream(
        core_v1.connect_get_namespaced_pod_exec,
        name,
        ns,
        command=["/bin/bash", "-c", f"cd /tmp/cbng-core && ({command})"],
        stderr=True,
        stdin=False,
        stdout=True,
        tty=False,
        _preload_content=False,
    )

    stdout, stderr = "", ""
    while resp.is_open():
        resp.update(timeout=1)
        if resp.peek_stdout():
            stdout += resp.read_stdout()
        if resp.peek_stderr():
            stderr += resp.read_stderr()

    if error_details := resp.read_channel(ERROR_CHANNEL):
        if '"status":"Failure"' in error_details:
            logger.debug(f"Command execution failed: {error_details}")
            return False, stdout, stderr

    return True, stdout, stderr


def store_container_file(container_namespace: str, container_id: str, source_path: PosixPath, upload_url: str) -> bool:
    absolute_path = (PosixPath("/tmp/cbng-core") / source_path).absolute()
    logger.info(f"Uploading {absolute_path.as_posix()} to {upload_url}")

    success, stdout, stderr = execute_in_container(
        container_namespace,
        container_id,
        f'test -s "{absolute_path.as_posix()}" && curl -H "Authorization: Bearer {"${CBNG_TRAINER_FILE_API_KEY}"}" --data-binary "@{absolute_path.as_posix()}" "{upload_url}" || true',
    )
    return success
