#!/usr/bin/env python3
"""Setup script für Ersatz CLI Installation."""
from setuptools import setup, find_packages

setup(
    name="ersatz",
    version="1.0.0",
    packages=find_packages(),
    install_requires=[
        "fastapi>=0.109.0",
        "uvicorn[standard]>=0.27.0",
        "aiohttp>=3.9.0",
        "pydantic>=2.5.0",
        "requests>=2.31.0",
    ],
    entry_points={
        "console_scripts": [
            "ersatz=cli.ersatz:main",
        ],
    },
    python_requires=">=3.11",
)
