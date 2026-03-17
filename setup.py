from setuptools import setup, find_packages

setup(
    name="ppc-shared",
    version="1.0.0",
    packages=find_packages(),
    install_requires=[
        "pandas",
        "openpyxl",
    ],
    description="Shared PPC parsing and campaign extraction logic",
)
