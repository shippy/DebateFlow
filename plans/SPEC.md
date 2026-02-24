# DebateFlow: A Benchmark for Multi-Turn Debate Judgment in Large Language Models

- **Author:** Šimon Podhajský
- **Status:** Research proposal
- **Target venue:** HuggingFace dataset publication; potential workshop/conference paper

---

## 1. Introduction

I have judged over a hundred competitive debates in the Karl Popper format and trained new judges for the Czech Debate League. The skill that takes longest to teach is tracking what happens *between* arguments: which points were answered, which were dropped, whether a team adapted its strategy to what the opponent actually said, and how burdens of proof shifted across the exchange.

Current argumentation benchmarks do not test this. They evaluate argument quality in isolation — a single text scored along rhetorical or logical dimensions. DebateFlow tests whether LLMs can judge *multi-turn debates*: given a four-turn transcript and a scoring rubric, predict the winner and score each side along dimensions that require attending to the full arc of the exchange.

---

## 2. Related Work

**Argument quality taxonomies.** Wachsmuth et al. (2017a) proposed fifteen quality dimensions (logical, rhetorical, dialectical) for individual arguments. Their follow-up (2017b) found overall quality judgments more reliable than fine-grained dimensional scores. The dialectical category comes closest to debate judgment, but the unit of analysis remains a single text.

**LLMs as argument judges.** Wachsmuth et al. (2024) confirmed that LLMs can approximate human scores on individual argument quality. Whether this extends to multi-turn evaluation is untested.

**Formal argumentation.** Sanayei et al. (2025) evaluated LLMs on the NoDE benchmark using QuAD semantics, finding position bias, length bias, and difficulty with non-linear structures. However, NoDE uses formal attack/support graphs, not natural-language transcripts. Ruiz-Dolz et al. (2023) combined argumentation semantics with graph neural networks, but likewise require structured graph input.

**Pairwise comparison.** Chatbot Arena uses Elo-based preference ranking with no rubric, no burden-of-proof tracking, and no debate-specific evaluation.

**The gap.** No existing benchmark tests LLM judgment of multi-turn natural-language debates — tracking answered and dropped arguments, burden of proof, and strategic adaptation across turns.

---

## 3. Task Definition

**Input.** A four-turn debate transcript on a stated resolution:

| Turn | Speaker | Function |
|------|---------|----------|
| 1 | Affirmative | Opening constructive |
| 2 | Negative | Refutation and counter-argument |
| 3 | Affirmative | Rebuttal, defense, extension |
| 4 | Negative | Closing rebuttal |

Four turns is the minimum where all rubric dimensions — including argument extension and strategic adaptation — can be meaningfully assessed. Cross-examination is excluded; it is a candidate for future extension.

**Output.** Winner prediction (Affirmative/Negative) with justification, plus per-dimension rubric scores.

---

## 4. Evaluation Rubric

The rubric draws partial inspiration from the individual speaker criteria used in Karl Popper format debate (content, strategy, style), adapted for multi-turn assessment rather than per-speaker scoring. Each dimension is grounded in computational argumentation theory where applicable.

| Dimension | Definition | Grounding |
|-----------|------------|-----------|
| **Clash engagement** | Did each side address the opponent's arguments or talk past them? | Dialectical quality (Wachsmuth 2017a), extended to cross-turn tracking |
| **Burden fulfillment** | Did each side meet its burden of proof? (Aff: demonstrate need for change; Neg: defend status quo or show harm) | Extends logical quality; side-asymmetric, no single-argument analogue |
| **Rebuttal quality** | Specificity and depth of refutations — targeting weak premises vs. asserting disagreement | Logical quality (Wachsmuth 2017a), evaluated relative to the argument rebutted |
| **Argument extension** | Did arguments develop across turns, or merely repeat the opening? | Novel; from competitive debate practice |
| **Strategic adaptation** | Did speakers adjust their approach based on the opponent's actual moves? | Novel; from competitive debate practice |

The last two dimensions are contributions of this work — central to debate judging but absent from existing quality taxonomies, which are designed for single arguments.

### Score-Level Anchors

Each dimension is scored on a 3-point scale with concrete behavioral anchors. Calibration principle: Weak = conspicuously absent or failed; OK = happened, nothing to remark on; Strong = you'd specifically call it out as well-done.

| Dimension | Weak (1) | OK (2) | Strong (3) |
|-----------|----------|--------|------------|
| **Clash Engagement** | Talked past the opponent entirely | Addressed the opponent's general thrust | Engaged with multiple specific arguments |
| **Burden Fulfillment** | Side-specific obligations unaddressed | Attempted their burden but left notable gaps | Each element of their burden clearly covered |
| **Rebuttal Quality** | Mere contradiction ("that's wrong") | Challenged conclusions but not underlying reasoning | Identified and attacked a specific weak premise |
| **Argument Extension** | Repeated opening arguments verbatim | Some new framing but no substantive new material | Added new evidence or reasoning that advanced the case |
| **Strategic Adaptation** | Could have been written without hearing the opponent | Some responsiveness but core approach unchanged | Clearly shifted priorities based on how the debate unfolded |

Distinguishing the "opponent engagement" trio: **Clash** = breadth (how many arguments addressed); **Rebuttal** = depth (how well dismantled); **Adaptation** = temporal (did approach change between turns).

**Open design decisions.** The pilot will determine whether five dimensions or a reduced set (3–4) yields better inter-annotator reliability, and whether a five-point or three-point scale is appropriate.

---

## 5. Data: Synthetic Debate Generation

### Why synthetic

Real competitive debates are oral events; verbatim transcripts are scarce and carry privacy constraints. Synthetic generation solves availability and offers a methodological advantage: **controlled asymmetries**. By instructing one side to exhibit a specific weakness, each debate has a known ground-truth failure mode, enabling fine-grained error analysis (cf. TruthfulQA, BBQ).

### Generation protocol

LLM-vs-LLM turn-by-turn debates where the weaker side receives an asymmetric constraint:

- **Evidence quality:** rely on anecdotal or weak sources
- **Argument dropping:** leave a specific opponent argument unanswered
- **Logical gaps:** introduce a non-sequitur or unsupported leap
- **Burden failure:** fail to establish core burden of proof

If a judge model fails to penalize the side with the injected weakness, the failure mode can be characterized precisely.

### Quality control

Human review for coherence; discard incoherent debates; approximate Aff/Neg win balance; topic diversity across resolution categories (Section 7).

### Scale

Pilot: 50–100 debates. Full dataset size determined by pilot signal strength.

### Limitations

Synthetic debates are unlikely to match the strategic depth of experienced human debaters, and LLM-generated text is stylistically homogeneous. Future work may augment with transcribed real debates — the Czech Debate League (KPDP) maintains some tournament recordings that could serve as a complementary source.

---

## 6. Annotation Protocol

**Pilot.** The author, with experience judging at the Czech national level and accrediting new judges. Single expert annotation is standard for pilot studies and sufficient for establishing baseline signal.

**Scale.** Two to three additional annotators from the competitive debate community. Each debate scored independently by at least two annotators.

**Agreement.** Cohen's kappa (two annotators) or Krippendorff's alpha (three+), reported per dimension. Disagreements resolved by discussion; original independent scores preserved in the released dataset.

---

## 7. Resolution Topics

Three categories to ensure argument diversity:

**Policy** — "This house would ban private car ownership in city centers"; "This house would implement universal basic income"

**Values** — "This house believes cancel culture does more harm than good"; "This house would prioritize economic growth over environmental protection"

**Empirical** — "Social media has been net negative for democracy"; "AI development should be paused until safety is better understood"

The set will be expanded during the pilot based on which topic types produce the most diagnostically useful debates.

---

## 8. Evaluation Framework

**Primary metrics.**
- **Winner prediction accuracy** — agreement with human judge(s), reported as raw accuracy and majority-vote agreement for multi-annotator subsets
- **Rubric dimension correlation** — Spearman/Kendall τ between model and human scores, per dimension

**Secondary metrics.**
- **Per-dimension error analysis** — which rubric dimensions models systematically fail on
- **Failure mode detection rates** — per injected weakness type (evidence, dropping, logic, burden)
- **Baselines** — majority class, response-length heuristic, random

The benchmark is designed to produce a diagnostic profile of LLM debate-judging capabilities rather than a single accuracy number.

---

## 9. Scope and Open Questions

DebateFlow is scoped as a pilot. Several decisions will be finalized empirically:

- **Rubric granularity** — five-point vs. three-point scale, based on inter-annotator agreement
- **Language** — English-only initially; Czech subset is a natural extension given access to Czech debate community resources
- **Cross-examination** — excluded from v1; future work
- **Real debate data** — contingent on KPDP recording availability, transcription quality, and consent

---

## 10. Expected Contributions

1. A benchmark for **multi-turn debate judgment** — a capability no existing dataset targets
2. A rubric grounded in argumentation theory and competitive debate practice, including two novel dimensions (argument extension, strategic adaptation) absent from existing taxonomies
3. A controlled synthetic generation methodology with injected failure modes for fine-grained diagnosis of LLM judgment

---

## References

- Ruiz-Dolz, R., Heras, S., & García-Fornes, A. (2023). Automatic Debate Evaluation with Argumentation Semantics and Natural Language Argument Graph Networks. *Proceedings of EMNLP 2023*, 6030–6040.
- Sanayei, R., Vesic, S., Blanco, E., & Surdeanu, M. (2025). Can LLMs Judge Debates? Evaluating Non-Linear Reasoning via Argumentation Theory Semantics. *Findings of EMNLP 2025*, 21244–21262.
- Wachsmuth, H., Naderi, N., Hou, Y., Bilu, Y., Prabhakaran, V., Alberdingk Thijm, T., Hirst, G., & Stein, B. (2017a). Computational Argumentation Quality Assessment in Natural Language. *Proceedings of EACL 2017*, 176–187.
- Wachsmuth, H., Naderi, N., Habernal, I., Hou, Y., Hirst, G., Gurevych, I., & Stein, B. (2017b). Argumentation Quality Assessment: Theory vs. Practice. *Proceedings of ACL 2017 (Volume 2: Short Papers)*, 250–255.
- Wachsmuth, H., Lapesa, G., Cabrio, E., Lauscher, A., Park, J., Vecchi, E.M., Villata, S., & Ziegenbein, T. (2024). Argument Quality Assessment in the Age of Instruction-Following Large Language Models. *Proceedings of LREC-COLING 2024*, 1519–1538.

---

*Last updated: 2026-02-17*
