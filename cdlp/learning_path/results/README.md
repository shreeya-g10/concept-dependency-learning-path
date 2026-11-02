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
