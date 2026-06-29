"""FOCL CLI — generate and maintain AI-native .focl codebase representations."""

from __future__ import annotations

import sys
import time
from pathlib import Path

import click
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.table import Table

from . import __version__
from .analyzer import detect
from .generator import generate, update
from .metrics import measure, measure_from_paths
from .providers import DEFAULT_PROVIDER, PROVIDERS, LLMConfig
from .sharder import DEFAULT_SHARD_BUDGET
from .watcher import watch

console = Console()


def _llm_options(f):
    """Attach the shared provider/model/key/base-url options to a command."""
    f = click.option("--base-url", default=None,
                     help="Override the provider's API base URL")(f)
    f = click.option("--api-key", default=None,
                     help="API key (else <PROVIDER>_API_KEY env var)")(f)
    f = click.option("--model", default=None,
                     help="Model id/slug (provider default if unset)")(f)
    f = click.option("--provider", type=click.Choice(PROVIDERS),
                     default=DEFAULT_PROVIDER, show_default=True,
                     help="LLM provider")(f)
    return f


def _build_config(provider: str, model: str | None, api_key: str | None,
                  base_url: str | None) -> LLMConfig:
    return LLMConfig(provider=provider, model=model, api_key=api_key,
                     base_url=base_url)


def _resolve_root(path: str | None) -> Path:
    root = Path(path).resolve() if path else Path.cwd()
    if not root.is_dir():
        console.print(f"[red]Error:[/red] '{root}' is not a directory.")
        sys.exit(1)
    return root


def _focl_path(root: Path, name: str | None) -> Path:
    fname = name or (root.name + ".focl")
    if not fname.endswith(".focl"):
        fname += ".focl"
    return root / fname


def _print_compression_report(info, focl_content: str,
                               elapsed: float, out_name: str,
                               config: LLMConfig,
                               exact: bool) -> None:
    """Shared reporting block used by init and sync."""
    m = measure(info, focl_content, config=config, exact=exact)

    qualifier = "exact" if m.exact else "estimated"
    console.print(f"\n[bold green]Done[/bold green] — {out_name} written in {elapsed:.1f}s")
    console.print(f"  Source tokens:   {m.source_tokens:>10,}  ({qualifier})")
    console.print(f"  FOCL tokens:     {m.focl_tokens:>10,}  ({qualifier})")
    console.print(f"  Token ratio:     {m.token_ratio:>10.1f}x")
    console.print(f"  [bold]Token saving:    {m.token_saving_pct:>10.1f}%[/bold]")
    console.print(
        f"  [dim](Bytes: {m.source_bytes / 1024:.0f} KB → "
        f"{m.focl_bytes / 1024:.0f} KB = {m.byte_saving_pct:.0f}% smaller)[/dim]"
    )


def _generate_and_report(info, out: Path, *, config: LLMConfig,
                         shard_budget: int, exact_tokens: bool,
                         fail_label: str) -> None:
    """Run generation under a progress spinner, write the .focl, print the report.

    Shared by `init` and `sync`, which differ only in the failure label shown.
    """
    with Progress(SpinnerColumn(), TextColumn("[progress.description]{task.description}"),
                  console=console) as progress:
        task = progress.add_task("Starting...", total=None)

        def on_progress(msg: str) -> None:
            progress.update(task, description=msg)

        t0 = time.time()
        try:
            focl_content = generate(
                info,
                config=config,
                shard_budget=shard_budget,
                use_api_counter=exact_tokens,
                progress=on_progress,
            )
        except Exception as e:
            progress.update(task, description=f"[red]{fail_label}[/red]")
            console.print(f"\n[red]Error:[/red] {e}")
            sys.exit(1)
        elapsed = time.time() - t0
        progress.update(task, description="[green]Done[/green]", completed=True)

    out.write_text(focl_content, encoding="utf-8")
    _print_compression_report(info, focl_content, elapsed, out.name,
                              config=config, exact=exact_tokens)


@click.group()
@click.version_option(__version__, prog_name="focl")
def main() -> None:
    """FOCL — AI-native codebase compression."""


@main.command()
@click.argument("path", default=".", required=False)
@click.option("--output", "-o", default=None, help="Output .focl filename (default: <project>.focl)")
@_llm_options
@click.option("--force", is_flag=True, help="Overwrite existing .focl file")
@click.option("--shard-budget", default=DEFAULT_SHARD_BUDGET, show_default=True,
              type=int, help="Max estimated tokens per shard for large codebases")
@click.option("--exact-tokens", is_flag=True,
              help="Use the provider's exact token counter (Anthropic only; slower)")
def init(path: str, output: str | None, provider: str, model: str | None,
         api_key: str | None, base_url: str | None, force: bool,
         shard_budget: int, exact_tokens: bool) -> None:
    """Analyse a codebase and generate a .focl file."""
    root = _resolve_root(path)
    out = _focl_path(root, output)
    config = _build_config(provider, model, api_key, base_url)

    if out.exists() and not force:
        console.print(f"[yellow]{out.name}[/yellow] already exists. Use --force to overwrite.")
        sys.exit(0)

    console.print(f"[bold]FOCL[/bold] analysing [cyan]{root}[/cyan]")
    info = detect(root)
    console.print(
        f"  Language: [green]{info.language}[/green]"
        + (f" / {info.framework}" if info.framework else "")
    )
    console.print(f"  Model:    [green]{config.provider}[/green] / {config.model}")
    console.print(f"  Files:    {len(info.files)}")
    console.print(f"  Size:     {info.total_bytes / 1024:.0f} KB")
    if info.skipped_files:
        console.print(
            f"  [yellow]Skipped:[/yellow]  {len(info.skipped_files)} file(s) "
            f"too large to process:"
        )
        for skipped_path, reason in info.skipped_files[:5]:
            try:
                rel = skipped_path.relative_to(root)
            except ValueError:
                rel = skipped_path
            console.print(f"    • {rel} — {reason}")

    _generate_and_report(info, out, config=config, shard_budget=shard_budget,
                         exact_tokens=exact_tokens, fail_label="Generation failed")


@main.command()
@click.argument("path", default=".", required=False)
@click.option("--focl-file", "-f", default=None, help="Path to existing .focl file")
@_llm_options
@click.option("--shard-budget", default=DEFAULT_SHARD_BUDGET, show_default=True,
              type=int, help="Max estimated tokens per shard for large codebases")
@click.option("--exact-tokens", is_flag=True,
              help="Use the provider's exact token counter (Anthropic only)")
def sync(path: str, focl_file: str | None, provider: str, model: str | None,
         api_key: str | None, base_url: str | None,
         shard_budget: int, exact_tokens: bool) -> None:
    """Regenerate the .focl file from scratch (full re-analysis)."""
    root = _resolve_root(path)
    out = Path(focl_file).resolve() if focl_file else _focl_path(root, None)
    config = _build_config(provider, model, api_key, base_url)

    console.print(f"[bold]FOCL[/bold] syncing [cyan]{root}[/cyan]")
    console.print(f"  Model:  [green]{config.provider}[/green] / {config.model}")
    info = detect(root)

    _generate_and_report(info, out, config=config, shard_budget=shard_budget,
                         exact_tokens=exact_tokens, fail_label="Sync failed")


@main.command()
@click.argument("path", default=".", required=False)
@click.option("--focl-file", "-f", default=None, help="Path to .focl file to keep updated")
@_llm_options
@click.option("--debounce", default=3.0, show_default=True,
              help="Seconds to wait after last change before updating")
def watch_cmd(path: str, focl_file: str | None, provider: str, model: str | None,
              api_key: str | None, base_url: str | None, debounce: float) -> None:
    """Watch for source changes and automatically patch the .focl file."""
    root = _resolve_root(path)
    out = Path(focl_file).resolve() if focl_file else _focl_path(root, None)
    config = _build_config(provider, model, api_key, base_url)

    if not out.exists():
        console.print(f"[red]Error:[/red] {out.name} not found. Run 'focl init' first.")
        sys.exit(1)

    console.print(f"[bold]FOCL[/bold] watching [cyan]{root}[/cyan]")
    console.print(f"  .focl:  {out.name}")
    console.print("  Press Ctrl+C to stop.\n")

    def on_change(changed: list[Path]) -> None:
        names = ", ".join(p.name for p in changed[:3])
        if len(changed) > 3:
            names += f" (+{len(changed) - 3} more)"
        console.print(f"[yellow]Changed:[/yellow] {names} — updating .focl...")
        try:
            t0 = time.time()
            updated = update(out, changed, root, config=config)
            out.write_text(updated, encoding="utf-8")
            elapsed = time.time() - t0
            console.print(f"[green]Updated[/green] {out.name} in {elapsed:.1f}s")
        except Exception as e:
            console.print(f"[red]Update failed:[/red] {e}")

    watch(root, on_change, debounce=debounce)


main.add_command(watch_cmd, name="watch")


@main.command()
@click.argument("path", default=".", required=False)
@click.option("--focl-file", "-f", default=None, help="Path to .focl file")
@_llm_options
@click.option("--exact-tokens", is_flag=True,
              help="Use the provider's exact token counter (Anthropic only; slower)")
def stats(path: str, focl_file: str | None, provider: str, model: str | None,
          api_key: str | None, base_url: str | None,
          exact_tokens: bool) -> None:
    """Show compression statistics for the project."""
    root = _resolve_root(path)
    out = Path(focl_file).resolve() if focl_file else _focl_path(root, None)
    config = _build_config(provider, model, api_key, base_url)

    info = detect(root)

    table = Table(title="FOCL Stats", show_header=True, header_style="bold cyan")
    table.add_column("Metric", style="bold")
    table.add_column("Value", justify="right")

    table.add_row("Project", root.name)
    table.add_row("Language", f"{info.language}" + (f" / {info.framework}" if info.framework else ""))
    table.add_row("Source files", str(len(info.files)))
    table.add_row("Source size", f"{info.total_bytes / 1024:.0f} KB")

    if out.exists():
        m = measure_from_paths(info, out, config=config, exact=exact_tokens)
        qualifier = "exact" if m.exact else "estimated"
        table.add_row("FOCL size", f"{m.focl_bytes / 1024:.0f} KB")
        table.add_row(f"Source tokens ({qualifier})", f"{m.source_tokens:,}")
        table.add_row(f"FOCL tokens ({qualifier})", f"{m.focl_tokens:,}")
        table.add_row("Token ratio", f"{m.token_ratio:.1f}x")
        table.add_row("Token saving", f"{m.token_saving_pct:.1f}%")
    else:
        table.add_row("FOCL file", "[red]not found — run focl init[/red]")

    console.print(table)


@main.command()
@click.argument("path", default=".", required=False)
@click.option("--shard-budget", default=DEFAULT_SHARD_BUDGET, show_default=True,
              type=int, help="Max estimated tokens per shard")
def plan(path: str, shard_budget: int) -> None:
    """Preview how the codebase would be sharded without calling the API."""
    from .sharder import shard_project

    root = _resolve_root(path)
    info = detect(root)
    console.print(f"[bold]FOCL plan[/bold] for [cyan]{root}[/cyan]")
    console.print(
        f"  Language: [green]{info.language}[/green]"
        + (f" / {info.framework}" if info.framework else "")
    )
    console.print(f"  Files:    {len(info.files)}")

    result = shard_project(info, budget=shard_budget, use_api_counter=False)

    table = Table(title=f"Sharding plan ({len(result.shards)} shards)",
                  show_header=True, header_style="bold cyan")
    table.add_column("#", justify="right")
    table.add_column("Label")
    table.add_column("Files", justify="right")
    table.add_column("Est. tokens", justify="right")

    for shard in result.shards:
        table.add_row(
            str(shard.index),
            shard.label,
            str(shard.file_count),
            f"{shard.token_estimate:,}",
        )

    console.print(table)
    console.print(f"[bold]Total:[/bold] ~{result.total_tokens:,} estimated input tokens")

    if result.oversize_files:
        console.print(f"\n[yellow]Warning:[/yellow] {len(result.oversize_files)} file(s) exceed budget on their own:")
        for f in result.oversize_files[:5]:
            try:
                size_kb = f.stat().st_size / 1024
                console.print(f"  • {f.relative_to(root)} ({size_kb:.0f} KB)")
            except OSError:
                console.print(f"  • {f.relative_to(root)}")


main.add_command(plan)
