import base64
import os
from pathlib import PosixPath
from typing import Optional

import yaml
from fabric import Connection, Config, task

TARGET_USER = os.environ.get("TARGET_USER", "cluebotng-trainer")
TOOL_DIR = PosixPath("/data/project") / TARGET_USER

c = Connection(
    "login.toolforge.org",
    config=Config(overrides={"sudo": {"user": f"tools.{TARGET_USER}", "prefix": "/usr/bin/sudo -ni"}}),
)


def _push_file_to_remote(source: str, target: Optional[str] = None):
    source_path = (PosixPath(__file__).parent / source)
    target_path = PosixPath(TOOL_DIR / (target if target else source))

    with source_path.open("r") as fh:
        file_contents = fh.read()

    print(f'Uploading {source_path.as_posix()} -> {target_path.as_posix()}')
    encoded_contents = base64.b64encode(file_contents.encode("utf-8")).decode("utf-8")
    c.sudo(f"bash -c \"base64 -d <<< '{encoded_contents}' > '{target_path.as_posix()}'\"")


@task()
def deploy_webservice(_ctx):
    """Deploy the webservice."""
    _push_file_to_remote("service.template")

    # Start the webservice (service files out of public_html)
    c.sudo(f"XDG_CONFIG_HOME={TOOL_DIR} toolforge webservice buildservice restart")


@task
def setup_secrets(_ctx):
    # Copy the kubernetes config into envvars
    config = yaml.load(c.sudo(f"cat {TOOL_DIR / '.kube' / 'config'}", hide="stdout").stdout.strip(),
                       Loader=yaml.SafeLoader)

    c.sudo(f"XDG_CONFIG_HOME={TOOL_DIR} toolforge envvars create K8S_SERVER {config['clusters'][0]['cluster']['server']} > /dev/null")
    c.sudo(f"bash -c 'XDG_CONFIG_HOME={TOOL_DIR} toolforge envvars create K8S_CLIENT_CRT < {(TOOL_DIR / '.toolskube' / 'client.crt').as_posix()}' > /dev/null")
    c.sudo(f"bash -c 'XDG_CONFIG_HOME={TOOL_DIR} toolforge envvars create K8S_CLIENT_KEY < {(TOOL_DIR / '.toolskube' / 'client.key').as_posix()}' > /dev/null")
