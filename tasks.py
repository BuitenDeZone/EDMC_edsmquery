"""Configures all tasks to run with invoke."""

import glob
import os
import sys
from subprocess import check_output

from invoke import task
from version import VERSION


@task(
    aliases=["flake8", "pep8"],
    help={
        'filename': 'File(s) to lint. Supports globbing.',
        'envdir': 'Specify the python virtual env dir to ignore. Defaults to "venv".',
        'noglob': 'Disable globbing of filenames. Can give issues in virtual environments',
    },
)
def lint(ctx, filename=None, envdir=['env', 'venv'], noglob=False):
    """Run flake8 python linter.

    :param ctx: Invoke context
    :param filename: A filename to check.
    :param envdir: python environment dirs. We exclude these
    :param noglob: Disable globbing in the filename.
    """

    excludes = ['.git', 'env', 'venv']
    if isinstance(envdir, str):
        excludes.append(str)
    else:
        for x in envdir:
            excludes.append(x)

    command = 'flake8 --jobs=1 --exclude ' + ','.join(excludes)

    if filename is not None:
        if noglob:
            templates = [filename]
        else:
            templates = [x for x in glob.glob(filename)]
            if len(templates) == 0:
                print("File `{0}` not found".format(filename))
                exit(1)

        command += ' ' + " ".join(templates)

    print("Running command: '" + command + "'")
    os.system(command)


@task(
    help={
        'out': 'Where to store the file',
        'current': 'Package the current state',
    },
)
def release(ctx, out='out', name=None, current=False):
    """Perform release task.

    Creates a zip with required files and prefix Materializer. Github auto packing includes the version
    number in the prefix.
    """
    if name is None:
        name = os.path.basename(os.path.dirname(os.path.realpath(__file__)))

    tag = VERSION
    file_version = VERSION

    if current:
        reflog = check_output(['git', 'symbolic-ref', '--short', 'HEAD']).strip()
        sha = check_output(['git', 'rev-parse', '--short', 'HEAD']).strip()
        # print "Reflog: {reflog}".format(reflog=reflog)
        # print "Sha: {sha}".format(sha=sha)
        tag = 'HEAD'
        file_version = "{branchref}~{sha}".format(branchref=reflog.replace('/', '_'), sha=sha)

    outfile = '{out}{sep}{name}-{file_version}.zip'.format(
        out=out,
        name=name,
        sep=os.path.sep,
        file_version=file_version
    )
    command = ['git', 'archive', '-v', tag,
               '--prefix', '{name}{sep}'.format(name=name, sep=os.path.sep),
               '--format', 'zip',
               '--output', outfile]

    # print("Running command: ['" + "', '".join(command) + "']")
    if not os.path.isdir(out):
        os.mkdir('out')

    print "Packaging ..."
    ctx.run(' '.join(command), err_stream=sys.stdout)
    print "Output: {outfile}".format(outfile=outfile)
