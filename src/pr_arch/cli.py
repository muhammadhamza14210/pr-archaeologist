import typer
from rich.console import Console
from pr_arch import __version__
from pr_arch.config import load_settings
from pr_arch.db.connection import connect, vec_version
from pr_arch.index.schema import migrate

app = typer.Typer(
    name="pr-arch",
    help="Build and query a living memory of a repo's decision history.",
    no_args_is_help=True,
)
console = Console()

@app.callback()
def main() -> None:
    pass


@app.command()
def version() -> None:
    """Print the installed pr-arch version."""
    typer.echo(f"pr-arch {__version__}")

@app.command()
def doctor() -> None:
    """Check that configuration and the database layer are working."""
    settings = load_settings()

    console.print("[bold]pr-arch doctor[/bold]")
    console.print(f"  data dir:   {settings.data_dir}")
    console.print(f"  db path:    {settings.db_path}")

    # Report which secrets are present, without printing them.
    secrets = {
        "GITHUB_TOKEN": settings.github_token,
        "OPENAI_API_KEY": settings.openai_api_key,
        "ANTHROPIC_API_KEY": settings.anthropic_api_key,
    }
    for name, value in secrets.items():
        status = "[green]set[/green]" if value else "[yellow]not set[/yellow]"
        console.print(f"  {name}: {status}")

    # Open the DB and confirm sqlite-vec loaded.
    try:
        conn = connect(settings.db_path)
        v = vec_version(conn)
        conn.close()
        console.print(f"  sqlite-vec: [green]loaded (v{v})[/green]")
    except Exception as e: 
        console.print(f"  sqlite-vec: [red]FAILED[/red] — {e}")
        raise typer.Exit(code=1)

    console.print("[green]All checks passed.[/green]")


@app.command()
def init() -> None:
    """Create or upgrade the memory database schema."""
    settings = load_settings()
    conn = connect(settings.db_path)
    try:
        applied = migrate(conn)
    finally:
        conn.close()

    if applied:
        console.print(f"[green]Applied {applied} migration(s).[/green]")
    else:
        console.print("[green]Schema already up to date.[/green]")
    console.print(f"  db: {settings.db_path}")

if __name__ == "__main__":
    app()