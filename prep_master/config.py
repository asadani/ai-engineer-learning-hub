from dataclasses import dataclass
from typing import List

DEFAULT_MODEL = "claude-opus-4-5"
FAST_MODEL = "claude-sonnet-4-5"
MAX_TOKENS = 4096
TEMPERATURE = 0.3


@dataclass(frozen=True)
class SectionConfig:
    index: int
    filename: str
    title: str
    focus: str


SECTIONS: List[SectionConfig] = [
    SectionConfig(
        index=1,
        filename="1_High_Level_Overview.md",
        title="High-Level Overview",
        focus=(
            "definition, origin story, core motivation, and 30-second elevator pitch "
            "tailored to a senior engineering audience. Cover what problem this solves, "
            "why it matters in 2025-2026, and the key insight that makes it work."
        ),
    ),
    SectionConfig(
        index=2,
        filename="2_Key_Technical_Concepts.md",
        title="Key Technical Concepts",
        focus=(
            "fundamental algorithms, data structures, protocols, and architectural "
            "primitives that underpin the technology. Include ASCII or markdown diagrams "
            "where they clarify architecture. Cover the 'how it actually works' internals "
            "a principal engineer would be expected to know."
        ),
    ),
    SectionConfig(
        index=3,
        filename="3_Products_Tools.md",
        title="Products & Tools",
        focus=(
            "major commercial products, managed services (especially AWS, GCP, Azure), "
            "and open-source tools in this space. For each: brief positioning, key "
            "differentiators, maturity level, and typical use case. Note which are "
            "production-proven at scale vs. emerging."
        ),
    ),
    SectionConfig(
        index=4,
        filename="4_Tradeoffs_Comparisons.md",
        title="Tradeoffs & Comparisons",
        focus=(
            "head-to-head comparisons with alternatives, CAP theorem implications if "
            "applicable, latency vs throughput vs consistency tradeoffs, operational "
            "complexity, and when NOT to use this technology. Include concrete numbers "
            "where known."
        ),
    ),
    SectionConfig(
        index=5,
        filename="5_Use_Cases.md",
        title="Use Cases & Real-World Applications",
        focus=(
            "real-world production use cases at scale, with architectural sketches and "
            "which companies or domains use it prominently. Include integration patterns "
            "with adjacent systems (e.g., how it fits in a microservices or AI/ML pipeline)."
        ),
    ),
    SectionConfig(
        index=6,
        filename="6_Measurement_Evaluation.md",
        title="Measurement & Evaluation",
        focus=(
            "how to evaluate correctness, performance, and reliability of this technology "
            "in production. Cover relevant benchmarks, evaluation frameworks, standard "
            "test datasets or suites, and how to interpret results. Include known "
            "industry benchmarks and leaderboards if applicable."
        ),
    ),
    SectionConfig(
        index=7,
        filename="7_What_to_Measure_How.md",
        title="What to Measure & How",
        focus=(
            "specific operational metrics, SLOs/SLAs, observability strategies, "
            "dashboards, alerting thresholds, and tooling for day-2 operations. "
            "Cover both infrastructure-level and application-level signals."
        ),
    ),
    SectionConfig(
        index=8,
        filename="8_Interview_Questions.md",
        title="Interview Questions & Scenarios",
        focus=(
            "interview questions spanning senior to principal-level difficulty, "
            "covering both conceptual depth and system-design scenarios. Each question "
            "should have a model answer that demonstrates principal-level thinking."
        ),
    ),
]

SECTION_EXTRA_INSTRUCTIONS: dict[int, str] = {
    4: (
        "Include at least one markdown comparison table with columns covering key "
        "dimensions like: Aspect | This Technology | Alternative 1 | Alternative 2. "
        "Be specific with numbers (p99 latency, throughput, storage overhead, etc.)."
    ),
    7: (
        "Include a concrete Metrics Checklist formatted as a markdown table with columns:\n"
        "| Metric Name | Type (counter/gauge/histogram) | Target SLO | Collection Method |\n"
        "Cover at minimum: latency percentiles, error rates, throughput, resource utilization, "
        "and any domain-specific signals."
    ),
    8: (
        "Structure questions in three tiers:\n\n"
        "## Tier 1: Senior Engineer (L5)\n"
        "## Tier 2: Staff Engineer (L6)\n"
        "## Tier 3: Principal Engineer (L7+)\n\n"
        "Each tier: 6-7 questions. For each question, include a **Model Answer** subsection "
        "(3-5 sentences) that a strong candidate would give, referencing production realities, "
        "edge cases, and tradeoffs — not textbook definitions."
    ),
}
