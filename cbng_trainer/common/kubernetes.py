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

import urllib3
from kubernetes import config
from kubernetes.client.api import core_v1_api

logger = logging.getLogger(__name__)


def _get_client():
    urllib3.disable_warnings()
    config.load_kube_config()
    return core_v1_api.CoreV1Api()


def get_pod_name_for_job(pod_namespace: str, job_name: str) -> str:
    core_v1 = _get_client()
    pods = core_v1.list_namespaced_pod(pod_namespace, label_selector=f"job-name={job_name}")
    if len(pods.items) != 1:
        raise RuntimeError(f"Failed to find pod for job {job_name}: {pods.items}")
    return pods.items[0].metadata.name


def is_container_running(pod_namespace: str, pod_name: str):
    core_v1 = _get_client()
    resp = core_v1.read_namespaced_pod(name=pod_name, namespace=pod_namespace)
    return resp.status.phase == "Running"
