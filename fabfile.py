import os
from fabric.decorators import task
from fabric.operations import local


@task
def build():
    """
    Builds the distribution files
    """
    if not os.path.exists("build"):
        os.mkdir("build")
    local("date >> build/log")
    local("pandoc README.md -f markdown -t rst -s -o README.rst")
    local("python setup.py sdist >> build/log")
    local("python setup.py bdist_wheel >> build/log")


@task
def release():
    """
    Uploads files to PyPi to create a new release.

    Note: Requires that files have been built first
    """
    local("twine upload dist/*")
