import asyncio
from pathlib import Path

import click
import nest_asyncio
from dotenv import load_dotenv

from .config import DEFAULT_MODEL, FAST_MODEL, MAX_TOKENS, SECTIONS
from .console import SequentialUI, ParallelUI, print_summary, console
from .generator import Generator, AsyncGenerator
from .writer import ensure_output_dir, write_section, write_readme

load_dotenv()


def _run_sequential(topic: str, gen: Generator, output_dir: Path):
    word_counts = {}
    with SequentialUI() as ui:
        for section in SECTIONS:
            ui.start_section(section)
            try:
                content = gen.generate_section(
                    topic,
                    section,
                    on_progress=lambda chars, idx=section.index: ui.update_section(idx, chars),
                )
                write_section(output_dir, section, content)
                wc = len(content.split())
                word_counts[section.index] = wc
                ui.complete_section(section, wc)
            except Exception as e:
                stub = f"# {section.title}\n\n> Generation failed: {e}\n"
                write_section(output_dir, section, stub)
                word_counts[section.index] = 0
                console.print(f"[red]Section {section.index} failed: {e}[/red]")
    return word_counts


async def _run_parallel(topic: str, gen: AsyncGenerator, output_dir: Path):
    word_counts = {}
    with ParallelUI() as ui:
        results = await gen.generate_all(
            topic,
            on_progress=lambda idx, chars: ui.update_section(idx, chars),
        )
        for result in results:
            if isinstance(result, Exception):
                console.print(f"[red]A section failed: {result}[/red]")
                continue
            section, content = result
            write_section(output_dir, section, content)
            wc = len(content.split())
            word_counts[section.index] = wc
            ui.complete_section(section, wc)
    return word_counts


@click.command()
@click.argument("topic")
@click.option(
    "--model", "-m",
    default=DEFAULT_MODEL,
    show_default=True,
    help="Anthropic model to use.",
)
@click.option(
    "--output-dir", "-o",
    default="./output",
    show_default=True,
    type=click.Path(file_okay=False),
    help="Base directory for output files.",
)
@click.option(
    "--parallel", "-p",
    is_flag=True,
    default=False,
    help="Generate all 8 sections in parallel (~3x faster, higher API concurrency).",
)
@click.option(
    "--max-concurrent",
    default=3,
    show_default=True,
    help="Max parallel API calls when --parallel is used.",
)
@click.option(
    "--max-tokens",
    default=MAX_TOKENS,
    show_default=True,
    help="Max tokens per section response.",
)
@click.option(
    "--fast",
    is_flag=True,
    default=False,
    help=f"Use {FAST_MODEL} instead of opus (faster, cheaper, slightly less depth).",
)
@click.option(
    "--api-key",
    envvar="ANTHROPIC_API_KEY",
    required=True,
    help="Anthropic API key. Reads ANTHROPIC_API_KEY env var automatically.",
)
def main(topic, model, output_dir, parallel, max_concurrent, max_tokens, fast, api_key):
    """Generate structured technical interview notes for TOPIC.

    Examples:

    \b
      prep-master "Retrieval-Augmented Generation"
      prep-master "Kafka" --parallel --fast
      prep-master "Kubernetes Operators" --output-dir ~/interview-notes --max-tokens 6000
    """
    if fast:
        model = FAST_MODEL

    output_path = ensure_output_dir(Path(output_dir), topic)
    console.print(f"\n[bold]prep-master[/bold] — topic: [cyan]{topic}[/cyan]")
    console.print(f"Model: [dim]{model}[/dim] | Output: [dim]{output_path}[/dim]")
    console.print(f"Mode: [dim]{'parallel' if parallel else 'sequential'}[/dim]\n")

    if parallel:
        nest_asyncio.apply()
        gen = AsyncGenerator(
            api_key=api_key,
            model=model,
            max_tokens=max_tokens,
            max_concurrent=max_concurrent,
        )
        word_counts = asyncio.run(_run_parallel(topic, gen, output_path))
    else:
        gen = Generator(api_key=api_key, model=model, max_tokens=max_tokens)
        word_counts = _run_sequential(topic, gen, output_path)

    write_readme(output_path, topic, model, SECTIONS, word_counts)
    print_summary(output_path, topic, SECTIONS, word_counts)
