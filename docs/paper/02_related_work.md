# 2 Related Work

> Draft. **Every citation needs verification before submission.** Citations with full details come from the project's own READMEs or plan and are still marked [VERIFY]. Where we did not have a reliable title, author list, year or venue, we use a [CITE: ...] placeholder instead of guessing.

## 2.1 Concept prerequisite discovery

Learning prerequisite relations between concepts has been studied with feature-based classifiers over Wikipedia links and text, with course-dependency signals, and with active learning. [CITE: prerequisite learning survey]

- Liang et al. recover concept prerequisites from university course dependencies and release the University Course dataset (Liang, Ye, Wu, Pursel, Giles, *Recovering Concept Prerequisite Relations from University Course Dependencies*, AAAI 2017) [VERIFY].
- Liang et al. study active learning for concept prerequisite learning and release AL-CPL (Liang, Ye, Wang, Pursel, Giles, *Investigating Active Learning for Concept Prerequisite Learning*, AAAI 2018, EAAI track) [VERIFY]. AL-CPL builds on an earlier Wikipedia concept-map dataset by Wang et al. (CIKM 2016) [VERIFY: title and authors].
- Li et al. introduce LectureBank for NLP education and prerequisite chain learning (Li, Fabbri, Tung, Radev, *What Should I Learn First: Introducing LectureBank for NLP Education and Prerequisite Chain Learning*, AAAI 2019) [VERIFY]. We do not evaluate on it (Section 5.1).
- Graph neural and representation-learning approaches to prerequisite prediction: [CITE: GNN-based prerequisite prediction].
- Recent LLM-based prerequisite work, listed in our project plan as PCPL (2024), ACE (2024), LCPRE (2024) and GKROM (2025), plus prerequisite-based course recommendation (2024) [VERIFY: full titles, authors and venues for each; we only have the short names]. Several of these use LLMs to propose or score prerequisite pairs.

**How we differ.** We treat discovery as an input. Our focus is what happens *after* an LLM proposes an edge: an independent check of whether the prerequisite is really needed (necessity), whether the course text supports it (evidence), and whether it is consistent with the graph. We also follow the graph down to individual students.

## 2.2 Educational knowledge graphs and learning-path recommendation

Educational knowledge graphs organize course concepts and their relations to support navigation, recommendation and sequencing. [CITE: educational knowledge graph construction survey] Learning-path recommendation orders content for a learner, often using prerequisite structure as a constraint. [CITE: learning path recommendation survey] [CITE: prerequisite-aware course recommendation]

Most such systems produce one path per course or per target. Our paths are specific to each student: concepts the student has already mastered are pruned, and soft prerequisites can be skipped depending on the student's background. Each edge on the path stays explainable (confidence, page-cited evidence, rationale).

## 2.3 Knowledge Space Theory, Bayesian and Deep Knowledge Tracing

**Knowledge Space Theory (KST)** models the feasible knowledge states of a domain as a family of sets closed under a prerequisite (surmise) relation. An adaptive assessment then needs only a few questions to place a learner in a state. The theory is due to Doignon and Falmagne [VERIFY: Doignon & Falmagne, 1985 paper and/or *Knowledge Spaces* book, 1999] and underlies the ALEKS system [VERIFY: ALEKS reference]. Our diagnostic uses the same idea: a correct answer on a concept is evidence for its ancestors. Unlike KST, our prerequisite relation is proposed by an LLM and checked automatically, not elicited from experts.

**Bayesian Knowledge Tracing (BKT)** models mastery of each skill as a hidden binary variable updated after every answer, with slip and guess parameters (Corbett & Anderson, 1994/1995) [VERIFY]. Our simulated students use slip and guess noise in the same spirit.

**Deep Knowledge Tracing (DKT)** replaces the per-skill model with a recurrent network over the interaction sequence (Piech et al., NeurIPS 2015) [VERIFY]. DKT needs large interaction logs, which a new course does not have. Our approach starts from course material alone.

## 2.4 LLM-as-a-judge and verification of LLM outputs

Using an LLM to grade the outputs of another LLM has become common. [CITE: LLM-as-a-judge benchmark paper] Known issues include position and verbosity bias, self-preference when the judge and the generator are the same model, and correlated errors. [CITE: LLM judge bias study] Self-consistency, sampling several answers and taking a majority vote, is a standard way to improve reliability. [CITE: self-consistency] Multi-agent debate and verification pipelines check a generated claim against retrieved evidence. [CITE: retrieval-grounded fact verification with LLMs] [CITE: multi-agent debate]

LLMs simulating learners or students have also been explored. [CITE: LLM simulated students]

**How we differ.** Our validator uses a different model and different prompts from the proposer, to reduce correlated errors. It does not ask a single judge "is A a prerequisite of B?". Instead, it combines checks that fail independently: grounded evidence with verbatim, page-cited quotes; a semantic grade from concept descriptions only; a counterfactual simulated-learner test (necessity); and structural graph checks. Our baselines include a single LLM judge and a self-consistency judge with a comparable call budget. This separates the effect of *more LLM calls* from the effect of *independent checks*.
