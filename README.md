# prep-master

Generate structured technical interview notes for any topic, tailored for principal-level engineers.

## Install

```bash
cp .env.example .env
# add your ANTHROPIC_API_KEY to .env

pip install -e .
```

## Usage

```bash
# Sequential (default) — safer for rate limits
prep-master "Retrieval-Augmented Generation"

# Parallel — ~3x faster
prep-master "Kafka" --parallel

# Fast model (sonnet vs opus)
prep-master "Kubernetes Operators" --parallel --fast

# Custom output dir and token budget
prep-master "DynamoDB" --output-dir ~/notes --max-tokens 6000
```

## Output

Each run creates a directory under `./output/<topic-slug>/` containing 9 files:

```
output/retrieval-augmented-generation/
├── README.md                      # index with word counts
├── 1_High_Level_Overview.md
├── 2_Key_Technical_Concepts.md
├── 3_Products_Tools.md
├── 4_Tradeoffs_Comparisons.md
├── 5_Use_Cases.md
├── 6_Measurement_Evaluation.md
├── 7_What_to_Measure_How.md
└── 8_Interview_Questions.md
```

## Options

| Flag | Default | Description |
|------|---------|-------------|
| `--model` / `-m` | `claude-opus-4-5` | Anthropic model |
| `--output-dir` / `-o` | `./output` | Base output directory |
| `--parallel` / `-p` | off | Generate sections in parallel |
| `--max-concurrent` | 3 | Parallel API call limit |
| `--max-tokens` | 4096 | Tokens per section |
| `--fast` | off | Use sonnet instead of opus |
| `--api-key` | `$ANTHROPIC_API_KEY` | Anthropic API key |

## Site & License

Live site: **https://asadani.github.io/ai-engineer-learning-hub/** (HTML + downloadable combined PDF).

Content © 2026 Anuj Sadani <anuj.k.sadani@gmail.com> — https://asadani.github.io/ — licensed **[CC BY 4.0](https://creativecommons.org/licenses/by/4.0/)** (free to share and adapt with attribution). See [LICENSE](LICENSE).

Build: `pip install -r requirements-docs.txt && python scripts/build_docs.py && mkdocs serve`. The combined PDF is produced in CI via `mkdocs.pdf.yml`.
