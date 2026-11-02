import sys
from setuptools import setup, find_packages

setup(
    name="glmc2",
    version="3.1",
    description="Terminal AI assistant",
    author="Mordheal",
    py_modules=["glmc2"],
    install_requires=[
        "openai",
        "rich",
        "ddgs",
    ],
    entry_points={
        "console_scripts": [
            "glmc2=glmc2:main",
        ],
    },
    python_requires=">=3.7",
)