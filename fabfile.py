from fabric.decorators import task
from fabric.operations import local


@task
def build():
    """
    Builds the distribution files
    """
    local("date >> build.log")
    local("pandoc README.md -f markdown -t rst -s -o README.rst")
    local("python setup.py sdist >> build.log")
    local("python setup.py bdist_wheel >> build.log")
