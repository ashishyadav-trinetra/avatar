"""
Minimal setup.py so pip install works when the avatar_spec directory
is copied flat into a Docker container (e.g. /tmp/avatar_spec/).
"""
from setuptools import setup, find_packages
import os

# When pip installs from /tmp/avatar_spec, the package IS the current dir
# We need to tell setuptools this dir is the 'avatar_spec' package
setup(
    name="avatar-spec",
    version="1.0.0",
    packages=["avatar_spec"],
    package_dir={"avatar_spec": "."},
    install_requires=["numpy>=1.24"],
    python_requires=">=3.10",
)
