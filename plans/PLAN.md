# DebateFlow: Synthetic Debate Generation Pipeline — Implementation Plan

## Context

The DebateFlow benchmark spec (`plans/SPEC.md`) defines a benchmark for evaluating LLM debate judgment. Before any evaluation can happen, we need debates to judge. This plan covers the first infrastructure piece: a synthetic debate generator that produces 4-turn transcripts with controlled asymmetries and control debates.

---

## Project Structure

```
debateflow/
├── pyproject.toml
├── .env.example              # API key template
├── resolutions.yaml          # Seed resolutions
├── plans/                    # Specs and planning docs
│   ├── PLAN.md
│   ├── SPEC.md
│   ├── VOICE-SPEC.md
│   └── TELEGRAM-JUDGING-SPEC.md
├── src/debateflow/
│   ├── models.py             # Pydantic data models
│   ├── providers.py          # LLM provider factory (Anthropic + OpenAI)
│   ├── prompts.py            # System prompts + constraint injection templates
│   ├── generator.py          # Core 4-turn generation pipeline
│   ├── compile.py            # JSONL compilation + stats
│   ├── publish.py            # HuggingFace Hub publication
│   ├── dataset_card.py       # Dataset card template generation
│   ├── cli.py                # Typer CLI entry point
│   ├── voice.py              # ElevenLabs TTS voice synthesis
│   ├── telegram_judging.py   # Telegram judging session management
│   ├── server.py             # Web annotation server
│   └── static/               # Web UI (annotate + review)
├── output/                   # Generated debates (gitignored)
│   └── debates/              # Individual JSON files
└── tests/
    ├── test_models.py
    └── test_prompts.py
```

---

## Data Models (`models.py`)

```python
class DebateCategory(str, Enum):     # policy | values | empirical
class WeaknessType(str, Enum):       # weak_evidence | argument_dropping | logical_gaps | burden_of_proof
class Side(str, Enum):               # aff | neg

class Turn(BaseModel):
    speaker: Side
    role: str          # opening | response | rebuttal | closing
    text: str

class ModelConfig(BaseModel):
    provider: str      # "anthropic" | "openai"
    model_name: str    # e.g. "claude-sonnet-4-20250514"
    temperature: float = 0.7

class ConstraintInfo(BaseModel):
    type: WeaknessType | None = None   # None = control debate
    target_side: Side | None = None

class DebateMetadata(BaseModel):
    debate_id: str                     # truncated UUID (8 chars)
    resolution: str
    category: DebateCategory
    aff_model: ModelConfig
    neg_model: ModelConfig
    constraint: ConstraintInfo
    is_control: bool
    generated_at: datetime
    generator_version: str = "0.1.0"

class Debate(BaseModel):
    metadata: DebateMetadata
    turns: list[Turn]                  # exactly 4
```

Each debate is self-contained JSON with full reproducibility metadata.

---

## Generation Pipeline (`generator.py`)

### Turn sequence

| Turn | Speaker | Role | Constraint applies? |
|------|---------|------|---------------------|
| 0 | Aff | opening | If Aff is constrained |
| 1 | Neg | response | If Neg is constrained |
| 2 | Aff | rebuttal | If Aff is constrained |
| 3 | Neg | closing | If Neg is constrained |

Exception: `argument_dropping` only applies to response/closing turns (need opponent arguments to drop).

### How a single debate is generated

1. Pick resolution, constraint type, target side (or mark as control)
2. For each of the 4 turns:
   - Build system prompt for that side (base + optional weakness overlay)
   - Build user prompt with resolution + all previous speeches as context
   - Call the appropriate LLM (Aff model or Neg model)
   - Append speech text to transcript
3. Assemble `Debate` object, write as individual JSON to `output/debates/`

Turns are sequential within a debate (each depends on prior turns). Batch generation is also sequential to avoid rate-limit complexity at pilot scale.

### Provider abstraction (`providers.py`)

Factory that creates pydantic-ai `Agent` instances from `ModelConfig`. Supports both `AnthropicModel` and `OpenAIModel` via pydantic-ai's provider abstraction. API keys from environment variables.

---

## Prompt Design (`prompts.py`)

### Base system prompts

Each side gets a brief system prompt: argue for/against the resolution, no meta-commentary, 200–400 words per turn.

### Turn instructions

Per-role instructions appended to user prompt:
- **opening**: Present strongest arguments, establish framework
- **response**: Engage opponent's opening, refute and counter-argue
- **rebuttal**: Defend arguments, expose opponent weaknesses
- **closing**: Summarize, weigh key arguments

### Weakness injection (4 templates)

Appended to system prompt on constrained side's turns:

- **weak_evidence**: Rely on anecdotes, vague authorities, hedging. Structure coherent but evidence weak.
- **argument_dropping**: Ignore 1–2 of opponent's key arguments. Don't acknowledge the gap.
- **logical_gaps**: Include 1–2 fallacies (hasty generalization, false dichotomy, non-sequitur). Surface rhetoric confident.
- **burden_of_proof**: Assert without support, demand opponent disprove. "Unless they can show otherwise..."

These are the quality-critical prompts. Calibrated for "noticeable by an attentive judge" — not comically bad.

---

## CLI (`cli.py`)

Three commands via Typer:

```bash
# Generate debates
uv run python cli.py generate -n 10 \
    --aff-provider anthropic --aff-model claude-sonnet-4-20250514 \
    --neg-provider openai --neg-model gpt-4o \
    --control-ratio 0.2

# Generate with specific resolution or category
uv run python cli.py generate -n 5 --category values
uv run python cli.py generate -n 1 -r "This house would ban private cars in city centers"

# Compile to JSONL
uv run python cli.py compile

# Show dataset stats (weakness distribution, category balance, side balance)
uv run python cli.py stats
```

Model defaults loaded from `resolutions.yaml` so bare `generate -n 10` works out of the box.

---

## Configuration (`resolutions.yaml`)

12 seed resolutions (4 per category). Default model configs for both sides. Example:

```yaml
resolutions:
  - text: "This house would ban private car ownership in city centers"
    category: policy
  # ... 11 more

defaults:
  aff:
    provider: anthropic
    model_name: claude-sonnet-4-20250514
    temperature: 0.7
  neg:
    provider: anthropic
    model_name: claude-sonnet-4-20250514
    temperature: 0.7
```

---

## JSONL Compilation (`compile.py`)

- `compile_to_jsonl()`: Read all `output/debates/*.json`, validate with pydantic, write one line per debate to `output/debateflow.jsonl`
- `show_stats()`: Print counts by weakness type, category, constrained side, control vs. constrained

---

## Dependencies (`pyproject.toml`)

```
pydantic>=2.0.0
pydantic-ai>=1.39.0
typer>=0.12.0
rich>=13.0.0
pyyaml>=6.0
python-dotenv>=1.0.0
datasets>=3.0.0
huggingface_hub>=0.25.0
```

---

## HuggingFace Publication (`publish.py`)

### What gets published

A HuggingFace dataset repo containing:
- `data/debateflow.jsonl` — the compiled dataset (one debate per line)
- `README.md` — dataset card with YAML metadata header

### Dataset card metadata

```yaml
---
language:
  - en
license: cc-by-4.0
task_categories:
  - text-classification
tags:
  - debate
  - argumentation
  - benchmark
  - llm-as-judge
pretty_name: "DebateFlow"
size_categories:
  - n<1K          # update when final count known
---
```

### Dataset card sections

The `README.md` follows HuggingFace's standard template:

1. **Dataset Description** — what DebateFlow is, citation info
2. **Dataset Structure** — schema description (fields, types, enums), example instance
3. **Dataset Creation** — synthetic generation methodology, resolution categories, constraint types
4. **Considerations for Using the Data** — synthetic data limitations, stylistic homogeneity, English-only
5. **Additional Information** — license, author, link to SPEC.md and paper (if any)

### CLI command

```bash
# Compile JSONL, generate dataset card, push to HuggingFace Hub
uv run python cli.py publish --repo spodhajsky/debateflow

# Dry run — generate card + JSONL locally without pushing
uv run python cli.py publish --repo spodhajsky/debateflow --dry-run
```

### Implementation (`publish.py`)

```python
def publish(repo_id: str, input_dir: Path, dry_run: bool = False):
    # 1. Compile debates to JSONL (reuses compile.py)
    # 2. Load JSONL as HuggingFace Dataset
    dataset = Dataset.from_json(str(jsonl_path))
    # 3. Generate dataset card from template + computed stats
    # 4. Push to Hub (unless dry_run)
    dataset.push_to_hub(repo_id, private=False)
```

Requires `datasets` and `huggingface_hub` libraries. Auth via `huggingface-cli login` (token cached locally).

### Dependencies to add

```
datasets>=3.0.0
huggingface_hub>=0.25.0
```

---

## Future: EvalEval Conformance (Phase 2, not built now)

When the evaluation harness is built (running LLMs as judges on generated debates), the output should conform to the [EvalEval "Every Eval Ever" schema](https://evalevalai.com/projects/every-eval-ever/):

- **Aggregate JSON**: Run-level metadata (which judge model, benchmark version, overall scores per dimension)
- **Instance-level JSONL**: Per-debate judge output (winner prediction, rubric scores, reasoning trace)

The debate generation format designed above is compatible — individual debates can be referenced as `source_data` in the EvalEval aggregate schema. No changes needed to the generation pipeline; this is purely an evaluation-harness concern.

---

## Implementation Order

### Step 1: Project scaffold
- `pyproject.toml`, `uv sync`, `.env.example`, `.gitignore`
- `models.py` with all pydantic schemas
- `tests/test_models.py` — serialization roundtrip

### Step 2: Prompts
- `prompts.py` — base prompts, turn instructions, 4 weakness templates
- `resolutions.yaml` — 12 seed resolutions
- `tests/test_prompts.py` — verify prompt construction per weakness type

### Step 3: Generation pipeline
- `providers.py` — Anthropic + OpenAI factory
- `generator.py` — single debate + batch generation
- Manual test: generate 1 debate, inspect JSON

### Step 4: CLI + compilation
- `cli.py` — generate / compile / stats commands
- `compile.py` — JSONL compilation + stats display

### Step 5: HuggingFace publication
- `dataset_card.py` — template generation from computed stats
- `publish.py` — compile + push_to_hub wrapper
- Add `publish` command to CLI
- Test with `--dry-run` to verify card + JSONL without pushing

### Step 6: Validation
- Generate 5 debates with mixed constraints
- Run `compile` and `stats`
- Manually review 2–3 debates for constraint quality (is the weakness detectable but not cartoonish?)
- `publish --dry-run` to verify dataset card renders correctly

---

## Verification

After implementation:
1. `uv run python cli.py generate -n 1` — produces a single debate JSON in `output/debates/`
2. `uv run python cli.py generate -n 5 --control-ratio 0.2` — produces ~4 constrained + ~1 control
3. `uv run python cli.py stats` — shows balanced distribution
4. `uv run python cli.py compile` — produces `output/debateflow.jsonl`
5. Manual read of 2–3 generated debates to assess constraint naturalness
6. `uv run python cli.py publish --repo test/debateflow --dry-run` — generates dataset card + JSONL locally
7. `uv run pytest tests/` — models and prompts pass
