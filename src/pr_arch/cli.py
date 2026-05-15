import typer
from rich.console import Console
from pr_arch import __version__
from pr_arch.config import load_settings
from pr_arch.db.connection import connect, vec_version
from pr_arch.index.schema import migrate
from pr_arch.agent.loop import answer_question
from pr_arch.llm.anthropic import AnthropicClient
from pr_arch.ingest.runner import ingest_repo

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

@app.command()
def ask(question: str) -> None:
    """Ask a question about the repository's decision history."""
    settings = load_settings()
    if not settings.anthropic_api_key:
        console.print("[red]ANTHROPIC_API_KEY is not set. Add it to .env.[/red]")
        raise typer.Exit(code=1)

    llm = AnthropicClient(settings.anthropic_api_key)
    conn = connect(settings.db_path)
    try:
        console.print("[dim]thinking…[/dim]")
        result = answer_question(llm, conn, question, console)
    finally:
        conn.close()

    console.print()
    console.print(result)

@app.command()
def index(repo: str) -> None:
    """Fetch PRs from a GitHub repo and store them locally.

    REPO is "owner/name" (e.g. astral-sh/ruff).
    """
    settings = load_settings()
    if not settings.github_token:
        console.print(
            "[yellow]GITHUB_TOKEN is not set. Unauthenticated requests are "
            "rate-limited to 60/hour and will likely fail on any real repo.[/yellow]"
        )

    conn = connect(settings.db_path)
    try:
        console.print(f"[bold]indexing[/bold] {repo}")
        counts = ingest_repo(conn, settings.raw_dir, repo, settings.github_token, console)
    finally:
        conn.close()

    console.print(
        f"[green]done.[/green] fetched {counts['fetched']}, "
        f"new {counts['inserted']}"
    )


if __name__ == "__main__":
    app()