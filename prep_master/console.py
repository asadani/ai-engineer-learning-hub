from typing import Dict, List

from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TimeElapsedColumn
from rich.table import Table

from .config import SectionConfig, SECTIONS

console = Console()


class SequentialUI:
    def __init__(self):
        self._progress = Progress(
            SpinnerColumn(),
            TextColumn("[bold blue]{task.description}"),
            TextColumn("[dim]{task.fields[words]} chars"),
            TimeElapsedColumn(),
            console=console,
        )
        self._task_ids: Dict[int, object] = {}

    def __enter__(self):
        self._progress.__enter__()
        return self

    def __exit__(self, *args):
        self._progress.__exit__(*args)

    def start_section(self, section: SectionConfig):
        tid = self._progress.add_task(
            f"Section {section.index}: {section.title}",
            words=0,
        )
        self._task_ids[section.index] = tid

    def update_section(self, section_index: int, char_count: int):
        tid = self._task_ids.get(section_index)
        if tid is not None:
            self._progress.update(tid, words=char_count)

    def complete_section(self, section: SectionConfig, word_count: int):
        tid = self._task_ids.get(section.index)
        if tid is not None:
            self._progress.update(
                tid,
                description=f"[green]✓[/green] Section {section.index}: {section.title}",
                words=f"{word_count:,} words",
            )


class ParallelUI:
    def __init__(self):
        self._progress = Progress(
            SpinnerColumn(),
            TextColumn("[bold blue]{task.description}"),
            TextColumn("[dim]{task.fields[words]}"),
            TimeElapsedColumn(),
            console=console,
        )
        self._task_ids: Dict[int, object] = {}

    def __enter__(self):
        self._progress.__enter__()
        for section in SECTIONS:
            tid = self._progress.add_task(
                f"Section {section.index}: {section.title}",
                words="waiting...",
            )
            self._task_ids[section.index] = tid
        return self

    def __exit__(self, *args):
        self._progress.__exit__(*args)

    def update_section(self, section_index: int, char_count: int):
        tid = self._task_ids.get(section_index)
        if tid is not None:
            self._progress.update(tid, words=f"{char_count:,} chars")

    def complete_section(self, section: SectionConfig, word_count: int):
        tid = self._task_ids.get(section.index)
        if tid is not None:
            self._progress.update(
                tid,
                description=f"[green]✓[/green] Section {section.index}: {section.title}",
                words=f"{word_count:,} words",
            )


def print_summary(output_dir, topic: str, sections: List[SectionConfig], word_counts: Dict[int, int]):
    table = Table(show_header=True, header_style="bold cyan")
    table.add_column("#", style="dim", width=3)
    table.add_column("Section")
    table.add_column("Words", justify="right")
    table.add_column("File")

    for s in sections:
        wc = word_counts.get(s.index, 0)
        status = "[green]✓[/green]" if wc > 0 else "[red]✗[/red]"
        table.add_row(
            f"{s.index}",
            f"{status} {s.title}",
            f"{wc:,}",
            s.filename,
        )

    console.print()
    console.print(table)
    console.print()
    console.print(
        Panel(
            f"[bold green]Output directory:[/bold green] {output_dir}\n"
            f"[bold green]Total words:[/bold green] {sum(word_counts.values()):,}",
            title=f"[bold]prep-master: {topic}[/bold]",
            border_style="green",
        )
    )
