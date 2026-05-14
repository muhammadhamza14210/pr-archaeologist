"""Command-line entry point for pr-arch."""

import typer
from pr_arch import __version__

app = typer.Typer(
    name="pr-arch",
    help="Build and query a living memory of a repo's decision history.",
    no_args_is_help=True,
)


@app.callback()
def main() -> None:
    pass


@app.command()
def version() -> None:
    """Print the installed pr-arch version."""
    typer.echo(f"pr-arch {__version__}")


if __name__ == "__main__":
    app()