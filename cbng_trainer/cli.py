#!/usr/bin/env python3
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

import asyncio
import logging
import sys
import tempfile
from pathlib import PosixPath

import click

from cbng_trainer.common.docker import (build_docker_image,
                                        start_container,
                                        stop_container,
                                        run_container)
from cbng_trainer.comparator.comparator import compare_samples
from cbng_trainer.comparator.results import generate_summary
from cbng_trainer.trainer.reviewed import dump_reviewed_edits

logger = logging.getLogger(__name__)


@click.group()
@click.option('--debug', is_flag=True, help='Enable debug logging')
def cli(debug):
    logging.basicConfig(level=(logging.DEBUG if debug else logging.INFO),
                        stream=sys.stderr)


@cli.command()
@click.option('--output', help='Target file',
              default='edits.xml', required=True)
def download_edits(output):
    loop = asyncio.get_event_loop()
    loop.run_until_complete(dump_reviewed_edits(PosixPath(output)))


@cli.command()
@click.option('--input', help='Edits file', required=True,
              default='edits.xml', type=click.Path(True))
@click.option('--output', help='Target directory',
              required=True, type=click.Path(True))
@click.option('--release-tag', help='Git release tag',
              required=True, default='v1.0.2')
def build_database(input, output, release_tag):
    output = PosixPath(output)
    core_image = build_docker_image(output, release_tag)
    stdout = run_container(core_image,
                           [(PosixPath(input).absolute().as_posix(),
                             '/edits.xml'),
                            (PosixPath(output).absolute().as_posix(),
                             '/opt/cbng-core/data/')],
                           ['/opt/cbng-core/cluebotng', '-c', 'conf',
                            '-m', 'bayes_train', '-f', '/edits.xml'])
    logger.info(f'Finished bayes_train: {stdout.decode("utf-8")}')

    stdout = run_container(core_image,
                           [(PosixPath(input).absolute().as_posix(), '/edits.xml'),
                            (PosixPath(output).absolute().as_posix(), '/opt/cbng-core/data/')],
                           ['/opt/cbng-core/create_bayes_db', 'data/bayes.db',
                            'data/main_bayes_train.dat'])
    logger.info(f'Finished create_bayes_db bayes.db: {stdout.decode("utf-8")}')

    stdout = run_container(core_image,
                           [(PosixPath(input).absolute().as_posix(), '/edits.xml'),
                            (PosixPath(output).absolute().as_posix(), '/opt/cbng-core/data/')],
                           ['/opt/cbng-core/create_bayes_db', 'data/two_bayes.db',
                            'data/two_bayes_train.dat'])
    logger.info(f'Finished create_bayes_db two_bayes.db: {stdout.decode("utf-8")}')

    stdout = run_container(core_image,
                           [(PosixPath(input).absolute().as_posix(), '/edits.xml'),
                            (PosixPath(output).absolute().as_posix(), '/opt/cbng-core/data/')],
                           ['/opt/cbng-core/cluebotng', '-c', 'conf',
                            '-m', 'ann_train', '-f', '/edits.xml'])
    logger.info(f'Finished ann_train: {stdout.decode("utf-8")}')

    stdout = run_container(core_image,
                           [(PosixPath(input).absolute().as_posix(), '/edits.xml'),
                            (PosixPath(output).absolute().as_posix(), '/opt/cbng-core/data/')],
                           ['/opt/cbng-core/create_ann', 'data/main_ann.fann',
                            'data/main_ann_train.dat', '150', '0.25', '162'])
    logger.info(f'Finished create_ann main_ann.fann: {stdout.decode("utf-8")}')


@cli.command()
@click.option('--target', help='Target binaries path', required=True, type=click.Path(True))
@click.option('--output', help='Output path', required=False, type=click.Path(True))
@click.option('--release-tag', help='Git release tag', required=True, default='v1.0.2')
def compare_database(target, output, release_tag):
    with tempfile.TemporaryDirectory() as tmp_dir:
        base_image = build_docker_image(PosixPath(tmp_dir), release_tag)
    target_image = build_docker_image(PosixPath(target), release_tag, True)

    base_container = start_container(base_image, 3501)
    target_container = start_container(target_image, 3502)

    try:
        loop = asyncio.get_event_loop()
        results = loop.run_until_complete(compare_samples(3501, 3502))
    except Exception as e:
        raise e
    else:
        if output:
            target = PosixPath(output) / 'comparator.md'
            click.echo(f'Dumping results to {target}')
            with target.open('w') as fh:
                fh.write(generate_summary(results))
        else:
            click.echo('Dumping results to stdout....')
            for result in results:
                print(result)

    finally:
        stop_container(base_container)
        stop_container(target_container)


if __name__ == '__main__':
    cli()
