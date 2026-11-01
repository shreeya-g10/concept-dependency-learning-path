# 1 Introduction

> Draft. Every citation is marked [VERIFY] or is a [CITE: ...] placeholder. No results are reported yet; numbers appear as [RESULT: ...].

## 1.1 The problem

A course syllabus lists topics, but it rarely says which topic depends on which. It never says which gap a particular student has. Consider a student who says *"I don't understand AVL trees."* A generic study system answers "revise AVL trees". But AVL trees are binary search trees that keep themselves balanced by rotation. A student who cannot rebalance an AVL tree may have no problem with balancing at all. They may never have understood the BST ordering invariant, or what a binary tree is. The useful answer depends on the dependency structure of the course (*Trees → Binary Trees → Binary Search Trees → AVL Trees*) and on where in that structure *this* student's knowledge stops.

Large language models (LLMs) can propose such prerequisite structures from course material at low cost. They also propose edges that sound plausible but are not prerequisites, for example *Graphs → AVL Trees*: the two concepts are related, but neither is needed to learn the other. An unchecked graph built from such proposals sends students down the wrong path, and a single extra edge can add a whole branch of unnecessary study to every student's path.

This paper asks two linked questions. Can the LLM-proposed prerequisite edges be *checked*, so that only edges a learner really needs enter the course graph? And can one validated course graph give *each student a different* path, based on what that student already knows?

## 1.2 Approach

We build an end-to-end pipeline from raw course material (PDF and slides) to a personalized learning path:

1. **Extraction:** chunks with source page or slide, and canonical concepts (aliases such as "BST" and "Binary Search Tree" merged into one node).
2. **Discovery:** a candidate filter (embedding similarity, co-occurrence in a chunk, course order, name-in-definition) narrows the O(n²) concept pairs. An LLM then proposes prerequisite edges, each with direction, strength (*hard* or *soft*), confidence and cited evidence chunks.
3. **Validation:** an independent agent, using a different model and different prompts from discovery, decides ACCEPT, REJECT or HUMAN_REVIEW for every proposed edge.
4. **Personalization:** the validated directed acyclic graph (DAG) is shared by all students. Each student has a knowledge-state overlay estimated by a short adaptive diagnostic. The student's path is the target's prerequisites minus what they have mastered, in dependency order.

Every pipeline stage writes schema-validated, versioned JSON, so each stage can be evaluated and ablated on its own.

## 1.3 Contributions

We do not claim that prerequisite discovery itself is new (see Section 2). Our contributions are:

1. **A necessity-testing validation agent.** Plausibility is not necessity. Before an edge *A → B* enters the graph, an LLM plays a learner who has never learned *A* and answers questions on *B*. A control run of the same learner forbids an unrelated concept instead. The score difference, the *necessity gap*, measures whether *A* is actually needed, not just whether the edge sounds right. The agent combines this with an evidence check grounded in the course text (verbatim, page-cited quotes), a semantic check of teaching order, and graph-consistency checks (cycles, contradictions, duplicates, transitive redundancy). Core question (RQ1): *does an independent validation agent improve the precision of LLM-proposed prerequisite edges, and at what cost to recall?*
2. **Graph-guided adaptive diagnosis.** The validated graph chooses the next quiz question. A correct answer on a concept is evidence for its ancestors, and a wrong answer puts the concept and its prerequisites in doubt. This estimates a student's knowledge state with fewer questions than testing every concept (RQ2).
3. **Root-cause tracing of wrong answers.** Given a wrong answer, an LLM reads the question, the chosen option and the concept's validated prerequisite chain, and ranks which concept most likely caused the error: the question's own concept or a prerequisite further back (RQ3).
4. **Personalized, explainable paths.** One course graph gives a different path per student. Every step carries the edge's confidence, its evidence (document and page) and a short rationale (RQ4).
5. **Impact-ranked human review.** Edges the agent cannot decide go to HUMAN_REVIEW. They are ranked by how many simulated students' paths would change if the edge were flipped, so reviewers spend their time where it changes the most paths.

## 1.4 Evaluation in brief

We evaluate stage by stage on two courses we annotated ourselves, Data Structures (`ds101`) and Machine Learning (`ml101`), and on two public prerequisite benchmarks, AL-CPL and the University Course dataset (Section 5). Validation is compared against discovery alone, a single LLM judge and a self-consistency judge, with ablations that remove each check. Diagnosis and paths are evaluated on simulated students with known ground-truth knowledge states.

[RESULT: one-sentence headline for RQ1, precision gain and recall cost]
[RESULT: one-sentence headline for RQ2, questions saved at matched accuracy]
[RESULT: one-sentence headline for RQ3, top-1 / top-3 vs baselines]
[RESULT: one-sentence headline for RQ4, path length reduction and order violations]

## 1.5 Paper outline

Section 2 reviews related work. Section 3 describes the validation agent and Section 4 root-cause tracing. Section 5 gives the experimental setup. [Sections 6–7: results and discussion, to be written.] Limitations and AI-assistance disclosure close the paper.
