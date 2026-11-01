# 5 Experimental Setup

> Draft. No numbers are reported; every result is a [RESULT: ...] placeholder. Dataset statistics we measured ourselves are also left as placeholders until the final conversion is frozen.

## 5.1 Datasets

**Our courses.**
- **`ds101` (Data Structures):** lecture PDFs and slides, running example *Trees → Binary Trees → Binary Search Trees → AVL Trees*.
- **`ml101` (Machine Learning):** second domain, to show the pipeline generalizes (*Vectors → Matrices → Linear Regression → Gradient Descent → Neural Networks*).

For both we hand-annotate concepts and prerequisite pairs (§5.5). [RESULT/STAT: concepts, labelled pairs, hard / soft / none counts per course]

**Public benchmarks.**
- **AL-CPL** (Liang et al., AAAI 2018 [VERIFY]): four Wikipedia-concept domains (data mining, geometry, physics, precalculus), with expert-corrected positive and negative pairs. Repository pinned at commit `11397ea`. Licence CC BY-NC-SA 4.0, stated in the repository README.
- **University Course dataset** (Liang et al., AAAI 2017 [VERIFY]): computer-science concept pairs, each labelled by three annotators; the authors' majority vote gives the positives. Repository pinned at commit `95a7fa7`. Licence CC BY-NC-SA 4.0.

Every downloaded file is checked against its recorded git blob SHA. Neither raw nor converted benchmark data is redistributed. Both are used for non-commercial research with attribution. [RESULT/STAT: concepts, positive and negative pairs per graph]

**Label mapping.** Neither benchmark distinguishes hard from soft prerequisites, so every positive becomes *hard* and every negative *none*. The University Course annotation file also contains votes with label `4`, which its README does not define (it lists labels 1–3 only). **We drop label-4 votes**: they count for no direction and are left out of the agreement shares. No pair has only label-4 votes. Dropping them cannot change the positive or negative sets, which come from the authors' majority-vote file.

**Excluded: LectureBank** (Li et al., AAAI 2019 [VERIFY]). We do not evaluate on it because its licence is not stated: *its repository and paper state no licence for the prerequisite annotations*, and we did not request permission. A converter exists so the work is reusable if a licence appears, but no LectureBank data is downloaded or used in any experiment.

**The agent on benchmarks.** On AL-CPL and University Course the agent uses only the semantic and graph checks, because benchmarks have no course text for the evidence check or for writing necessity questions. This is the agent we report on the benchmarks (`minus_evidence_necessity`). The full agent and the agent without the evidence check are still run there, but not reported. On `ds101` and `ml101` we report the full agent.

## 5.2 Research questions

- **RQ1 (validation).** Does an independent validation agent improve the precision of LLM-proposed prerequisite edges, and at what cost to recall?
- **RQ2 (diagnosis).** Does graph-guided adaptive diagnosis estimate a student's knowledge state accurately with fewer questions than testing every concept?
- **RQ3 (root cause).** Does LLM root-cause tracing identify the concept behind a wrong answer better than blaming the target or the nearest prerequisite?
- **RQ4 (paths).** Are personalized paths shorter than generic paths while still covering the student's real gaps, without violating the gold prerequisite order?

## 5.3 Settings and baselines

**RQ1.** Each setting is run once per course from a config file (`cdlp/validation/configs/rq1/`). The scoring harness itself makes no LLM call; it scores the files each setting produced.

| Setting | What it is |
|---|---|
| Baseline prompt | One "list all prerequisites" call over the full concept list, no candidate filter |
| Discovery only | Candidate filter + per-pair LLM discovery, no validation |
| Single LLM judge | One validator call per proposed edge (the semantic check alone: ACCEPT if strong or medium) |
| Self-consistency judge | The single judge sampled *k* = 5 times at temperature > 0, majority vote. Its call budget is in the same class as the agent's, which separates *more calls* from *independent checks* |
| Full agent | Evidence + semantic + necessity + graph checks |
| Agent − evidence / − semantic / − necessity / − graph | The agent with one check removed |
| Agent − evidence − necessity | Semantic and graph checks only: the agent reported on the benchmarks (§5.1) |

[TODO: single judge, self-consistency and the minus-check runs are still marked PENDING in the settings file.]

Models: discovery `qwen2.5:7b-instruct`; validator `llama3.1:8b`; both run locally through Ollama. Temperature 0 (except self-consistency), seed 42. Each result records the config, models, prompt versions, temperature, seed, git commit and date.

**RQ2.** Graph-guided adaptive diagnosis vs. *ask every concept* and *random order* with the same question budget as the adaptive run, on simulated students (§5.6).

**RQ3.** LLM tracing vs. *blame the target* and *blame the nearest prerequisite* (Section 4.4).

**RQ4.** Personalized path vs. the *generic path* (all ancestors of the target in topological order, regardless of the student).

## 5.4 Metrics

- **RQ1:** precision, recall and F1 of predicted edges against gold, per course and micro-averaged over the AL-CPL domains. For validated settings only ACCEPT edges count as predictions. We also report the **HUMAN_REVIEW rate** and **LLM calls per proposed edge**. An edge proposed in both directions predicts both pairs.
- **RQ2:** diagnosis accuracy (estimated known/unknown vs. ground truth per concept) against the number of questions asked.
- **RQ3:** top-1 and top-3 accuracy over wrong answers, against the labelled expected concept; the LLM fallback count.
- **RQ4:** path length; gap coverage (share of the student's truly unmastered ancestors that the path includes); order violations against the gold graph; educator ratings, if collected.
- **Concept extraction (supporting):** precision, recall and F1 against the hand-annotated concept list.

## 5.5 Gold annotation and agreement (κ protocol)

Annotators label ordered pairs *A → B* as *hard* (B cannot be understood without A), *soft* (A clearly helps but is not required) or *none*, following written guidelines (`docs/annotation_guidelines.md`). Each annotator writes only to their own file. Gold is frozen before any prompt is tuned.

Agreement is Cohen's κ on the pairs both annotators labelled, computed **on the labels as committed, before any adjudication**. We report two numbers:
1. **Raw κ** on the committed labels.
2. **κ after a mechanical shortcut rule**, applied identically to both annotators' files: a pair labelled hard or soft becomes *none* if the same annotator's own hard/soft pairs already form a path from A to B through another concept. The guidelines ask for direct dependencies only, so this rule removes shortcut labels without anyone's judgment.

[RESULT: raw κ overall and per course] [RESULT: κ after the shortcut rule, overall and per course] [RESULT: number of labels changed by the rule, per annotator]. We state the rule in full so readers can judge the second number. Adjudication to a single gold file follows, after κ is computed.

**Leakage between annotation and evaluation.** The shared example edges used during prompt development overlap with gold pairs. Thresholds and prompts are tuned only on a dev split, which is excluded from all reported scores (`exclude_pairs`). [TODO: list the dev split.]

## 5.6 Scoring convention: direct edges vs. transitive closure

Our own gold is **direct-edge only**: a shortcut pair such as *Trees → AVL Trees* is *none* when an intermediate concept exists. Our graph is also a transitive reduction. On our courses we therefore score predicted edges **directly**, and a predicted pair that gold does not label counts as a false positive.

Some benchmarks label shortcut pairs as positives. A correct direct-edge graph would then "miss" every shortcut positive. For those we score the **transitive closure of our predicted edges** against the benchmark labels, and score only the pairs the benchmark labels. The choice is made per dataset from the data, before any system is run:

- **AL-CPL:** its README states that positives were added via transitivity, so we use **closure**.
- **University Course:** the dataset does not say. We counted the positives that are already implied by a path of other positives [RESULT/STAT: shortcut count]. Because this count is large, we use **closure**. The University Course positives also contain one directed cycle; the convention does not depend on it.

Every reported number states which convention it uses.

## 5.7 Simulated students

Simulated students have a known ground-truth mastery for every concept that respects the validated graph: a student who knows a concept knows its prerequisites. Each student is sampled from a learning "frontier" in topological order. Concepts before the frontier and their ancestors are known, and concepts beyond it are unknown. Answers are noisy, with slip and guess probabilities (BKT-style). Throughout the paper **a concept counts as mastered when its mastery is above 0.8**: in personalized paths, in the review-queue impact computation and in the RQ2/RQ4 evaluation. [STAT: number of students, slip and guess as used in the final runs] Seeds are fixed.

## 5.8 RQ3 protocol (no mastery)

All three RQ3 methods trace every wrong answer **with mastery unknown**, so the comparison measures what each method gets from the question, the chosen option and the graph, and not from a separately estimated knowledge state. The prompt was developed on a dev set only. The dev set and the test set share no item ids, and the test set was labelled by the author who did not write the prompt. Details are in Section 4.5.

## 5.9 Reproducibility

Every stage writes schema-validated, versioned JSON. Every LLM call goes through one wrapper that caches responses and logs model id, prompt version, temperature and seed. Prompts are versioned files. Experiments read configs from files and write results, together with the config that produced them, to the module's `results/` folder. Only free, local tools are used (Ollama with open-weight models, sentence-transformers, NetworkX). Hardware: [STAT: machine and GPU used].
