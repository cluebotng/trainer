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
from pathlib import PosixPath

import click

from cbng_trainer.common.config import Settings, ApiHosts
from cbng_trainer.common.docker import (build_docker_image,
                                        run_container)
from cbng_trainer.comparator import plots
from cbng_trainer.trainer.reviewed import dump_edits

logger = logging.getLogger(__name__)


@click.group()
@click.pass_context
@click.option('--debug', is_flag=True, help='Enable debug logging')
@click.option('--api-host-report', default="cluebotng.toolforge.org",
              help='Hostname of the report API')
@click.option('--api-host-review', default="cluebotng-review.toolforge.org",
              help='Hostname of the review API')
@click.option('--api-host-wikipedia', default="en.wikipedia.org",
              help='Hostname of the wikipedia API')
def cli(ctx, debug, api_host_report, api_host_review, api_host_wikipedia):
    logging.basicConfig(level=(logging.DEBUG if debug else logging.INFO),
                        stream=sys.stderr)
    ctx.obj = Settings(ApiHosts(api_host_report, api_host_review, api_host_wikipedia))


@cli.command()
@click.pass_context
@click.option('--output', help='Target file',
              default='edits.xml', required=True)
@click.option('--edit-set', '-es', help='Edit Sets to include',
              multiple=True, type=int)
@click.option('--random-edits', is_flag=True, help='Download random edits')
@click.option('--random-edits-count', default=200, help='Number of random edits to download')
def download_edits(ctx, output, edit_set, random_edits, random_edits_count):
    loop = asyncio.get_event_loop()
    loop.run_until_complete(dump_edits(ctx.obj,
                                       PosixPath(output),
                                       edit_set or None,
                                       random_edits,
                                       random_edits_count))


@cli.command()
@click.option('--ann-input', help='Edit set for the ANN training',
              required=True, default='train-edits.xml', type=click.Path(True))
@click.option('--bayes-input', help='Edit set for the bayes training',
              required=True, default='bayes-edits.xml', type=click.Path(True))
@click.option('--output', help='Target directory',
              required=True, type=click.Path(True))
@click.option('--release-tag', help='Git release tag',
              required=True, default='v1.0.2')
def build_database(ann_input, bayes_input, output, release_tag):
    output = PosixPath(output)
    core_image = build_docker_image(output, release_tag)
    stdout = run_container(core_image,
                           [(PosixPath(bayes_input).absolute().as_posix(),
                             '/edits.xml'),
                            (output.absolute().as_posix(),
                             '/opt/cbng-core/data/')],
                           ['/opt/cbng-core/cluebotng', '-c', 'conf',
                            '-m', 'bayes_train', '-f', '/edits.xml'])
    logger.info(f'Finished bayes_train: {stdout.decode("utf-8")}')

    stdout = run_container(core_image,
                           [(output.absolute().as_posix(), '/opt/cbng-core/data/')],
                           ['/opt/cbng-core/create_bayes_db', 'data/bayes.db',
                            'data/main_bayes_train.dat'])
    logger.info(f'Finished create_bayes_db (bayes): {stdout.decode("utf-8")}')

    stdout = run_container(core_image,
                           [(output.absolute().as_posix(), '/opt/cbng-core/data/')],
                           ['/opt/cbng-core/create_bayes_db', 'data/two_bayes.db',
                            'data/two_bayes_train.dat'])
    logger.info(f'Finished create_bayes_db (two_bayes): {stdout.decode("utf-8")}')

    stdout = run_container(core_image,
                           [(PosixPath(ann_input).absolute().as_posix(), '/edits.xml'),
                            (output.absolute().as_posix(), '/opt/cbng-core/data/')],
                           ['/opt/cbng-core/cluebotng', '-c', 'conf',
                            '-m', 'ann_train', '-f', '/edits.xml'])
    logger.info(f'Finished ann_train: {stdout.decode("utf-8")}')

    stdout = run_container(core_image,
                           [(output.absolute().as_posix(), '/opt/cbng-core/data/')],
                           ['/opt/cbng-core/create_ann', 'data/main_ann.fann',
                            'data/main_ann_train.dat', '150', '0.037', '100'])
    logger.info(f'Finished create_ann: {stdout.decode("utf-8")}')


@cli.command()
@click.option('--input', help='Edits file', required=True, default='edits.xml', type=click.Path(True))
@click.option('--output', help='Output path', required=False, type=click.Path(True))
@click.option('--release-tag', help='Git release tag', required=True, default='v1.0.2')
def trial_database(input, output, release_tag):
    output = PosixPath(output)
    core_image = build_docker_image(output, release_tag)

    # Create a folder for all trial data
    trial_path = (output / 'trialreport')
    trial_path.mkdir(exist_ok=True)

    # Run the trial edit set
    stdout = run_container(core_image,
                           [(PosixPath(input).absolute().as_posix(), '/edits.xml'),
                            (output.absolute().as_posix(), '/opt/cbng-core/data/'),
                            (trial_path.absolute().as_posix(), '/opt/cbng-core/trialreport/')],
                           ['/opt/cbng-core/cluebotng', '-c', 'conf',
                            '-m', 'trial_run', '-f', '/edits.xml'])
    logger.info(f'Finished trial_run: {stdout.decode("utf-8")}')

    # Plot the trial results
    for name, plot in {'threshold': plots.THREASHOLD,
                 'false_positive_rate': plots.FALSE_POSITIVE}.items():

        # Write the plot file out to process
        plot_file = trial_path / f'{name}.gnuplot'
        with plot_file.open('w') as fh:
            fh.write(plot)

        # Process the plot file
        stdout = run_container(core_image,
                               [(trial_path.absolute().as_posix(), '/opt/cbng-core/trialreport/')],
                               ['gnuplot', f'{name}.gnuplot'],
                               '/opt/cbng-core/trialreport/')
        logger.info(f'Finished {name} plot: {stdout.decode("utf-8")}')


if __name__ == '__main__':
    cli()
