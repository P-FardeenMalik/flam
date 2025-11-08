"""Allow running queuectl as a module: python -m queuectl"""

from .cli import cli

if __name__ == '__main__':
    cli()
