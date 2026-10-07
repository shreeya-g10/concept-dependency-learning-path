# Concept Dependency Learning Path

**Agent-validated prerequisite graphs for student-adaptive learning paths.**

Give the system a course's lecture PDFs or slides. It extracts the concepts, works out which concepts depend on which, checks every dependency with an independent AI validation agent, and builds an explainable knowledge graph. Then it gives **each student a different learning path** to their target concept, based on what that student already knows.

> *"I don't understand AVL Trees."*
> A generic system says "revise AVL Trees". This system runs a short adaptive quiz, finds that the student knows binary trees but breaks the BST ordering rule, and recommends **BST ordering rule → AVL Trees**, with the lecture page for each step.

## The problem

Syllabi list topics, but they never say which topic depends on which, or which gap a particular student has. LLMs can propose prerequisite maps, but they hallucinate edges (e.g. *Graphs → AVL Trees*). An unchecked graph sends students down the wrong path.

## What's new

We don't claim prerequisite discovery itself is new. Our contributions are:

1. **Necessity-testing validation agent.** Before an edge *A → B* enters the graph, an LLM plays a student who does **not** know A and tries to answer questions on B, then tries again knowing A. The difference in scores (the *necessity gap*) shows whether A is truly needed, not just whether the edge sounds plausible. It's combined with evidence retrieval, semantic and graph-consistency checks, giving **ACCEPT / REJECT / HUMAN_REVIEW**.
2. **Graph-guided adaptive diagnosis.** The validated graph chooses the most informative next quiz question: a correct answer on BST implies its prerequisites are known. This finds a student's gaps with far fewer questions than testing every concept.
3. **Personalized, explainable paths.** One course graph, a different path per student: the target's prerequisites minus what the student has mastered, in dependency order. Every step cites the lecture and page it comes from.

## How it works

```
Course PDF / PPT
      │
      ▼
 Extraction      chunks + canonical concepts (with source pages)
      │
      ▼
 Discovery       candidate filter → LLM proposes A → B (hard / soft, confidence, evidence)
      │
      ▼
 Validation      evidence · semantic · necessity test · graph checks → ACCEPT / REJECT / REVIEW
      │
      ▼
 Learning path   validated DAG → adaptive quiz → student's knowledge state → personal path
      │
      ▼
 Website         explore the graph, see why each edge was accepted, take the quiz, get your path
```

Each stage is a separate module that exchanges schema-validated JSON files, so every stage can be evaluated and ablated on its own.

## Quick start

Requires Python 3.10+ and [Ollama](https://ollama.com). Everything is free and runs locally.

```bash
git clone https://github.com/shreeya-g10/concept-dependency-learning-path.git
cd concept-dependency-learning-path
python -m venv .venv && source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env                                     # Windows: copy .env.example .env
ollama pull qwen2.5:7b-instruct && ollama pull llama3.1:8b
```

Run it:

```bash
python pipeline.py --input data/raw --target avl_tree   # full pipeline → outputs/
streamlit run website/Home.py                            # the website
pytest -q                                                # tests
```

## Repository structure

```
cdlp/
├── extraction/      PDF/PPT → chunks.jsonl, concepts.json
├── discovery/       concepts → relationships.json, quiz_items.json, sim_students.json
├── validation/      relationships → validated_graph.json   (validation agent)
├── learning_path/   graph + quiz → student_state.json, learning_path.json   (+ api.py)
└── shared/          data contracts (JSON Schema), example data, validated I/O, LLM wrapper
website/             Streamlit multi-page site
pipeline.py          runs all stages end to end and checks every output
data/                course material and hand-labelled gold standard
docs/                research plan, annotation guidelines
```

## Evaluation

| Question | How we measure it |
|---|---|
| Does the validation agent improve edge quality? | Precision / recall / F1 against a hand-labelled gold set and public prerequisite benchmarks; ablations removing each check; baseline = single LLM judge |
| Does graph-guided diagnosis need fewer questions? | Diagnosis accuracy vs. number of questions on simulated students, against "ask every concept" and random order |
| Are personalized paths better? | Path length, coverage of real gaps, order violations, educator ratings |

Results will be added here as experiments complete.

## Tech stack (all free)

Python · Ollama with open models (Qwen 2.5 7B, Llama 3.1 8B) · sentence-transformers · FAISS · NetworkX · PyMuPDF · python-pptx · Streamlit + pyvis · jsonschema · pytest · ruff · GitHub Actions

## Team

Vaidehi · Sneha · Shreeya · Shrestha. Gen AI Lab project.

Working on the code? See [CONTRIBUTING.md](CONTRIBUTING.md) for ownership, workflow and the timeline.
