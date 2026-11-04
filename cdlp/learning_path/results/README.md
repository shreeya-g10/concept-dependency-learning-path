# Learning-path results

`rq2_rq4_results.json`: `python -m cdlp.learning_path.evaluate`. 500 simulated students per condition, seed 42, example graph (target `avl_tree`, 5 concepts on its path), mastery threshold 0.8 (strict). No LLM.

## RQ2: why ask-all used to score below adaptive (investigated 2026-11-02)

Before the fix: adaptive 0.85 accuracy with 4.86 questions, ask-all **0.62** with 5. Asking every concept cannot honestly be less accurate than asking a subset with the same estimator, so the comparison was checked step by step:

| Check | Finding |
|---|---|
| Same estimator? | Yes, both call `api.update_mastery`. |
| Same scoring? | In practice yes (both ended up scoring the same 5 concepts), but only by chance: accuracy was computed over whichever concepts a strategy had estimated. Now every strategy is scored on the target's prerequisite path, with an unestimated concept at the prior 0.5. |
| **Estimator bug** | **Cause.** A wrong answer reset every "mastered" ancestor to 0.5, even ones the student had *just answered correctly*; a correct answer lifted ancestors to 0.85 even if answered wrong. Ask-all asks prerequisites first, so a single wrong answer on BST erased its own correct answers on trees, binary trees and recursion. Adaptive asks the middle of the chain first and lost less. Fix: the latest direct answer per concept always wins over propagation (`__observed__` in the mastery dict). |
| Shared random stream | The three strategies drew answers from one RNG in sequence, so a strategy's noise depended on the others. Now each strategy has its own stream per student. |
| Built-in advantage? | Partly. The main students are closed under the graph (know B ⇒ know its prerequisites; 14% violate it only through slip/guess noise in the true mastery), which is exactly what adaptive's propagation assumes. Hence a second condition: **students who ignore the graph** (each concept mastered independently, p = 0.5; 78% violate closure). |

Noise ceiling: answering each of the 5 concepts once with the answer model (slip 0.10, guess 0.15) and reading the answer directly gives 0.876, so ask-all is now at the ceiling.

## Results after the fix

| Students | Strategy | Questions | Accuracy |
|---|---|---|---|
| follow the graph | adaptive | 4.28 | 0.866 |
| | ask every concept | 5.00 | 0.870 |
| | random (matched budget) | 4.28 | 0.824 |
| ignore the graph | adaptive | 3.64 | 0.775 |
| | ask every concept | 5.00 | 0.874 |
| | random (matched budget) | 3.64 | 0.759 |

Reading: when knowledge follows the graph, adaptive diagnosis saves 14% of the questions at practically the same accuracy (−0.4 points) and beats random questions at the same budget. When it does not, adaptive asks fewer questions (−27%) but loses 10 points of accuracy, i.e. its saving comes from the graph assumption. Both conditions should be reported. The example graph has only 5 concepts; rerun on the real course graphs.

## A second question after a right answer (tried 2026-11-03, not kept)

One lucky guess marks a topic as known, and with it every topic before it. So we tried asking a second question on a topic after a right answer, when one exists and the limit allows. `rq2_second_question.json`: 500 simulated students per condition, seed 42, example graph (5 concepts on the path), the limit of 10 never binds here, no LLM.

The rule was written before the first run. Keep it only if, with a second question available: (1) accuracy rises in both conditions with the 95% paired bootstrap interval above 0, (2) topics wrongly marked as known fall in both conditions, and (3) with students who follow the graph, it still asks fewer questions than asking every concept once. Otherwise the saving that adaptive diagnosis exists for is gone.

| Students | Quiz items | Strategy | Questions | Accuracy | Wrongly known | Gaps on the plan | Plan length |
|---|---|---|---|---|---|---|---|
| follow the graph | example (one per concept) | without | 4.28 | 0.866 | 0.189 | 0.811 | 2.35 |
| | | with | 4.28 | 0.866 | 0.189 | 0.811 | 2.35 |
| | one placeholder added per concept | without | 4.28 | 0.866 | 0.189 | 0.811 | 2.35 |
| | | **with** | **6.68** | **0.908** | **0.060** | **0.940** | **2.91** |
| ignore the graph | example (one per concept) | without | 3.64 | 0.775 | 0.407 | 0.593 | 1.77 |
| | | with | 3.64 | 0.775 | 0.407 | 0.593 | 1.77 |
| | one placeholder added per concept | without | 3.64 | 0.775 | 0.407 | 0.593 | 1.77 |
| | | **with** | **6.05** | **0.810** | **0.273** | **0.727** | **2.31** |

Accuracy rise with a second question: +0.043 (95% interval 0.030 to 0.056) when students follow the graph, +0.035 (0.021 to 0.049) when they ignore it. Other answer seeds (43 to 46) give +0.019 to +0.052 and +0.034 to +0.051. For comparison, asking every concept once: 5.00 questions, accuracy 0.870 and 0.874.

Verdict: (1) and (2) pass, **(3) fails: 6.68 questions against 5.00**. Not kept, and the website does not use it.

How to read this:
- The example quiz has one item per concept, so as shipped the strategy has nothing to ask and matches plain adaptive exactly. The rows with a placeholder ask "what if a second item existed". The placeholder item has no text: the simulated answer depends only on the concept.
- The simulated answers are independent given the concept. A real student who guesses one question may well get a similar one right too, so the gain here is probably an upper limit.
- This is the example graph, with 5 concepts. Rerun on real course graphs before citing it in the paper. The real ds101 quiz has 2 to 3 items per concept, so the strategy could run there.
- To reproduce: the code is in commit ae6327cb7 (`python -m cdlp.learning_path.evaluate`), and was removed in the next commit because it was not kept.

## Level ladder (2026-11-04)

`ladder_comparison.json`: `python -m cdlp.learning_path.evaluate --ladder`, config `configs/ladder_eval.json`. 500 simulated students per condition, seed 42, example graph (target `avl_tree`, 5 topics), placeholder quiz items, no LLM. `rq2_rq4_results.json` is not touched.

**Simulated difficulty is not real difficulty.** Every level's answer chance and the self-report chances are chosen in the config, not measured. The file's `assumptions` list states each one. Do not cite these numbers as evidence about real students or real questions.

| Students | Strategy | Questions | Self-report taps | Accuracy | Wrongly known | Gap coverage | Path length |
|---|---|---|---|---|---|---|---|
| follow the graph | adaptive (existing quiz, old answer model) | 4.28 | 0 | 0.866 | 0.189 | 0.811 | 2.35 |
| | adaptive_levelled (ladder items and answer model) | 3.96 | 0 | 0.814 | 0.315 | 0.685 | 1.91 |
| | ladder_linear | 6.27 | 3.37 | 0.825 | 0.005 | 0.995 | 3.53 |
| | ladder_middle | 5.36 | 2.95 | 0.859 | 0.032 | 0.968 | 3.28 |
| ignore the graph | adaptive (existing quiz, old answer model) | 3.64 | 0 | 0.775 | 0.407 | 0.593 | 1.77 |
| | adaptive_levelled (ladder items and answer model) | 3.32 | 0 | 0.728 | 0.538 | 0.462 | 1.31 |
| | ladder_linear | 4.92 | 2.77 | 0.689 | 0.002 | 0.998 | 4.06 |
| | ladder_middle | 5.11 | 2.87 | 0.712 | 0.197 | 0.803 | 3.15 |

Rules behind these numbers: only a real hard question earns Know it, and after an easy wrong answer (shown as "Start from the basics") `ladder_linear` skips only the topics that depend on that topic. On a straight chain this behaves as stopping at the first gap did.

How to read this:
- `adaptive` is the same run as `rq2_rq4_results.json` (a test pins this). `adaptive_levelled` is the fair comparison, because it shares the ladders' items and answer model. It asks easy items first, which is why it calls more gaps known than `adaptive`.
- The ladders trade length for safety. They almost never call a gap known, but they ask more questions and leave more on the plan. Against `adaptive_levelled`, `ladder_linear` accuracy does not clearly rise when students follow the graph (+0.011, 95% interval -0.015 to +0.038) and falls when they do not (-0.038, -0.061 to -0.016).
- Asking unrelated topics after a gap costs about 0.25 and 0.72 more questions than stopping did, and raises `ladder_linear` accuracy by 0.007 and 0.033. Topics that depend on a gap are still not checked, for 73% and 86% of students here, so known topics stay on the plan (0.86 and 1.55 per student). The example graph has only one unrelated pair (Recursion and Trees), so this says little about wider real graphs.
- `ladder_middle` scores better than `ladder_linear` on accuracy, and asks fewer questions when students follow the graph, but it infers known topics, so it calls more gaps known. When students ignore the graph that inference is often wrong (0.197).
- **`no_hard_items` is the main risk.** Only a real hard question earns Know it, so with no hard questions nobody can reach it: every plan holds all 5 topics, accuracy falls to 0.536 and 0.504, and nothing is called known wrongly. A stand-in for hard is still asked and recorded, but cannot change the result: 1.70 and 1.12 such questions per student for `ladder_linear`. Real hard questions may be dropped often, because the checks are not loosened for them, so the real drop rate matters.
- `flat_levels` and `unreliable_self_report` show the same pattern, so it does not rest on the chosen level chances alone. Other answer seeds (42 to 46) move accuracy by at most 0.02.

## quiz_check replays on the ds101 review drafts (2026-11-03)

`quiz_check_v2_replay_ds101` and `quiz_check_v3_replay_ds101` (`.json` with every reply, `.md` to read) run the 32 real `quiz_v2` drafts of the review run through each version of the checks, with `llama3.1:8b` as the second model (`python -m cdlp.learning_path.replay_quiz_check`).

- **A working test only.** These questions shaped the checks, so no accuracy figure may come from them.
- **The v3 threshold (`configs/quiz_check_v3.json`) was set from its stated reasoning before the v3 replay, and was not changed after it.**
- v2 ran on the 259-concept list and v3 on the 85 filtered concepts. On the 259 list, v3's subject check would also drop the AVL key property question (`search operations`, an alias of `find_operation`).
- Known wrong drops under v3: `time complexity` is an alias of `running_time_analysis`, so a question using those words is dropped when the chunk says only "O(n + m) time".
