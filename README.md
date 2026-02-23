# DebateFlow

A benchmark for multi-turn debate judgment in large language models.

## What this is

Current argumentation benchmarks evaluate argument quality in isolation -- a single text scored along rhetorical or logical dimensions. DebateFlow tests whether LLMs can judge *multi-turn debates*: given a four-turn transcript and a scoring rubric, predict the winner and score each side along dimensions that require attending to the full arc of the exchange.

Each debate follows the Karl Popper format: four turns (Affirmative opening, Negative response, Affirmative rebuttal, Negative closing) on a stated resolution. Debates are generated synthetically via LLM-vs-LLM, with one side optionally receiving an injected weakness (weak evidence, argument dropping, logical gaps, or burden-of-proof failure). This gives each debate a known ground-truth failure mode for fine-grained error analysis.

### Evaluation rubric

| Dimension | What it measures |
|---|---|
| **Clash engagement** | Did each side address the opponent's arguments or talk past them? |
| **Burden fulfillment** | Did each side meet its burden of proof? |
| **Rebuttal quality** | Specificity and depth of refutations |
| **Argument extension** | Did arguments develop across turns, or merely repeat the opening? |
| **Strategic adaptation** | Did speakers adjust their approach based on the opponent's actual moves? |

The last two dimensions are central to competitive debate judging but absent from existing argument quality taxonomies.

## Project structure

```
pyproject.toml              Project config and dependencies
resolutions.yaml            12 seed resolutions (policy, values, empirical)
src/debateflow/
    __init__.py              Package version
    __main__.py              python -m debateflow support
    models.py                Pydantic data models
    providers.py             LLM provider factory (Anthropic + OpenAI)
    prompts.py               System prompts and weakness injection templates
    generator.py             4-turn debate generation pipeline
    compile.py               JSONL compilation and statistics
    publish.py               HuggingFace Hub publication
    dataset_card.py          Dataset card template
    cli.py                   Typer CLI entry point
    server.py                Annotation server with on-demand TTS
    voice.py                 ElevenLabs TTS wrapper
    agreement.py             Inter-annotator agreement computation
    static/
        annotate.html        Browser-based annotation tool
output/
    debates/                 Generated debate JSON files
    annotations/             Human annotation JSON files
    audio/                   Cached TTS audio (MP3)
tests/
    test_models.py
    test_prompts.py
```

## Development setup

Requires Python 3.11+ and [uv](https://docs.astral.sh/uv/).

```bash
git clone <repo-url> && cd debateflow
uv sync
```

Copy `.env.example` to `.env` and fill in the keys you need:

```
DF_ANTHROPIC_API_KEY=...    # for debate generation (Anthropic models)
DF_OPENAI_API_KEY=...       # for debate generation (OpenAI models)
DF_ELEVENLABS_API_KEY=...   # for voice synthesis (annotation server)
DF_HF_TOKEN=...             # for publishing to HuggingFace Hub
DF_HF_REPO=...              # e.g. your-username/debateflow
```

Not all keys are needed for every task. Generation requires the LLM provider key(s), the annotation server requires ElevenLabs, and publishing requires HuggingFace.

## Generating debates

```bash
# Generate 10 debates with default models
uv run debateflow generate -n 10

# Use specific models per side
uv run debateflow generate -n 5 \
    --aff-provider anthropic --aff-model claude-sonnet-4-20250514 \
    --neg-provider openai --neg-model gpt-4o

# Filter by topic category or force a weakness type
uv run debateflow generate -n 5 --category values
uv run debateflow generate -n 3 --weakness argument_dropping

# View dataset statistics
uv run debateflow stats

# Compile individual JSONs into a single JSONL
uv run debateflow compile
```

## Annotating debates

The annotation tool runs in the browser. Start the server:

```bash
uv run debateflow serve
```

Then open [http://localhost:5733](http://localhost:5733). The server:

- Serves the annotation UI at `/`
- Loads debates from `output/debates/` (click "Load from Server" on the setup screen)
- Provides on-demand text-to-speech via ElevenLabs -- click Play on any turn to hear it spoken, or Play All for sequential playback
- Caches synthesized audio to `output/audio/` so repeated plays don't hit the API

Enter your annotator ID, load debates, and score each one. Annotations download as JSON files that go into `output/annotations/`.

Voice playback is optional -- annotation works without an ElevenLabs key, you just won't have the Play buttons functional.

### Annotation commands

```bash
# Check annotation progress
uv run debateflow annotate-status

# Compute inter-annotator agreement (needs 2+ annotators on same debates)
uv run debateflow annotate-agreement
```

## Publishing

```bash
# Dry run -- generates JSONL and dataset card locally
uv run debateflow publish --repo your-username/debateflow --dry-run

# Push to HuggingFace Hub
uv run debateflow publish --repo your-username/debateflow --public
```

## Tests

```bash
uv run pytest tests/
```
