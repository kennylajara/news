#!/usr/bin/env python3
"""
CLI for news portal.
"""

import click
from importlib.metadata import version
from commands import article, domain, entity, flash


@click.group()
@click.version_option(version=version("news"))
def cli():
    """News Portal CLI - Extract, process and publish news summaries."""
    pass


# Register command groups
cli.add_command(article.article)
cli.add_command(domain.domain)
cli.add_command(entity.entity)
cli.add_command(flash.flash)


if __name__ == "__main__":
    cli()
