from setuptools import setup, find_packages

setup(
    name='queuectl',
    version='1.0.0',
    packages=find_packages(),
    install_requires=[
        'click>=8.1.0',
        'colorama>=0.4.6',
    ],
    entry_points={
        'console_scripts': [
            'queuectl=queuectl.cli:cli',
        ],
    },
    python_requires='>=3.7',
)
