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


@task
def setup_secrets(_ctx):
    # Copy the kubernetes config into envvars
    config = yaml.load(c.sudo(f"cat {TOOL_DIR / '.kube' / 'config'}", hide="stdout").stdout.strip(),
                       Loader=yaml.SafeLoader)

    c.sudo(f"XDG_CONFIG_HOME={TOOL_DIR} toolforge envvars create K8S_SERVER {config['clusters'][0]['cluster']['server']} > /dev/null")
    c.sudo(f"bash -c 'XDG_CONFIG_HOME={TOOL_DIR} toolforge envvars create K8S_CLIENT_CRT < {(TOOL_DIR / '.toolskube' / 'client.crt').as_posix()}' > /dev/null")
    c.sudo(f"bash -c 'XDG_CONFIG_HOME={TOOL_DIR} toolforge envvars create K8S_CLIENT_KEY < {(TOOL_DIR / '.toolskube' / 'client.key').as_posix()}' > /dev/null")
