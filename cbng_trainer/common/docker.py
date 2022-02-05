'''
MIT License

Copyright (c) 2021 Damian Zaremba

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
'''

import logging
import subprocess
import uuid
from pathlib import PosixPath

logger = logging.getLogger(__name__)


def stop_container(name: str):
    logger.info(f'Asking docker to kill {name}')
    p = subprocess.Popen([
        'docker',
        'kill',
        name
    ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE)
    stdout, stderr = p.communicate()
    if p.returncode != 0:
        raise RuntimeError(f'Failed to stop container {name}: {stdout} / {stderr}')
    return True


def start_container(image: str, port: int):
    container_name = f'cbng-core-{uuid.uuid4()}'
    logger.info(f'Asking docker to start {container_name} from {image} using {port}')
    p = subprocess.Popen([
        'docker',
        'run',
        '--rm',
        '-d',
        '--name',
        container_name,
        '-p',
        f'127.0.0.1:{port}:3565',
        image,
        "/opt/cbng-core/cluebotng",
        "-l",
        "-m",
        "live_run"
    ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE)
    stdout, stderr = p.communicate()
    if p.returncode != 0:
        raise RuntimeError(f'Failed to start container {image}: {stdout} / {stderr}')
    return container_name


def run_container(image: str, volumes, arguments):
    logger.info(f'Asking docker to run {image} using {volumes} / {arguments}')

    volume_args = []
    for vs, vt in volumes:
        volume_args.extend(['-v', f'{vs}:{vt}'])

    p = subprocess.Popen(['docker', 'run', '--rm'] + volume_args + [image] + arguments,
                         stdout=subprocess.PIPE,
                         stderr=subprocess.PIPE)
    stdout, stderr = p.communicate()
    if p.returncode != 0:
        raise RuntimeError(f'Failed to run container {image}: {stdout} / {stderr}')
    return stdout


def build_docker_image(path: PosixPath, git_tag: str, include_local_binaries=False):
    docker_file = '''FROM debian:9
ARG CORE_TAG
WORKDIR /opt/cbng-core

RUN apt-get update && apt-get install -y wget && apt-get clean

RUN mkdir -p /opt/cbng-core
RUN wget -O /opt/cbng-core/cluebotng \
    https://github.com/cluebotng/core/releases/download/${CORE_TAG}/cluebotng
RUN chmod 755 /opt/cbng-core/cluebotng

RUN wget -O /opt/cbng-core/create_ann \
    https://github.com/cluebotng/core/releases/download/${CORE_TAG}/create_ann
RUN chmod 755 /opt/cbng-core/create_ann

RUN wget -O /opt/cbng-core/create_bayes_db \
    https://github.com/cluebotng/core/releases/download/${CORE_TAG}/create_bayes_db
RUN chmod 755 /opt/cbng-core/create_bayes_db

RUN wget -O /opt/cbng-core/print_bayes_db \
    https://github.com/cluebotng/core/releases/download/${CORE_TAG}/print_bayes_db
RUN chmod 755 /opt/cbng-core/print_bayes_db

RUN wget -O conf.tar.gz \
    https://github.com/cluebotng/core/releases/download/${CORE_TAG}/conf.tar.gz
RUN tar -C /opt/cbng-core -xvf conf.tar.gz && rm -f conf.tar.gz

# Lame hack to avoid issues trying to clear the non-existant tty
RUN sed -i s'/, "train_outputs"//g' /opt/cbng-core/conf/cluebotng.conf

RUN mkdir -p /opt/cbng-core/data
'''
    if include_local_binaries:
        docker_file += '''
# Local database
ADD bayes.db /opt/cbng-core/data/bayes.db
ADD two_bayes.db /opt/cbng-core/data/two_bayes.db
ADD main_ann.fann /opt/cbng-core/data/main_ann.fann
'''
    else:
        docker_file += '''
# Release database
RUN wget -O /opt/cbng-core/data/bayes.db \
    https://github.com/cluebotng/core/releases/download/${CORE_TAG}/bayes.db
RUN wget -O /opt/cbng-core/data/two_bayes.db \
    https://github.com/cluebotng/core/releases/download/${CORE_TAG}/two_bayes.db
RUN wget -O /opt/cbng-core/data/main_ann.fann \
    https://github.com/cluebotng/core/releases/download/${CORE_TAG}/main_ann.fann
'''

    image_tag = f'cbng/core/{uuid.uuid4()}'
    logger.info(f'Asking docker to build {image_tag}')
    with (path / 'Dockerfile').open('w') as fh:
        fh.write(docker_file)

    p = subprocess.Popen([
        'docker',
        'build',
        '-t',
        image_tag,
        '--build-arg',
        f'CORE_TAG={git_tag}',
        '-f',
        'Dockerfile',
        '.'
    ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        cwd=path.as_posix())
    stdout, stderr = p.communicate()
    if p.returncode != 0:
        raise RuntimeError(f'Failed to build docker image: {stdout} / {stderr}')

    (path / 'Dockerfile').unlink(True)
    return image_tag
