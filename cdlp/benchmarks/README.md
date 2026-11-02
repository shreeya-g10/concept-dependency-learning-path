# Benchmarks · maintainer: Shreeya

Public prerequisite datasets, converted into our formats so discovery and validation can be scored beyond our own course.

**Question you answer:** *Do our results hold on data we didn't annotate ourselves?*

**Evaluation benchmarks: AL-CPL and University Course.** LectureBank has a loader and tests, but it is **not used in evaluation: licence not stated** (decided 2026-11-02; see "Notes for the paper").

**Files:** `cdlp/benchmarks/`

| | File | Notes |
|---|---|---|
| Input | the downloaded dataset folder (`--raw`, default `data/benchmarks/<dataset>/`) | Never commit raw data: `data/benchmarks/` is gitignored |
| Output | `<out-dir>/<course_id>/concepts.json` | Same contract as extraction |
| Output | `<out-dir>/<course_id>/gold_edges.csv` | Same columns as `data/gold/gold_edges.csv` (`source,target,label,agreement,note`), `label` ∈ `hard` · `soft` · `none` |

```bash
python -m cdlp.benchmarks --dataset al_cpl             # -> outputs/benchmarks/al_cpl_<domain>/ (4 domains)
python -m cdlp.benchmarks --dataset university_course  # -> outputs/benchmarks/university_course/
# lecturebank also converts, but is not used in evaluation (licence not stated)
```

Each run prints a sanity line per graph (concepts, pairs, positives, negatives, slug collisions). `outputs/` is gitignored too.

## Sources, versions and licences (checked 2026-11-01 against the official repositories)

Every version is pinned to a commit. Each file's **git blob SHA** is listed so a download can be verified with `git hash-object <file>`. The repositories have no releases or tags.

### AL-CPL: `al_cpl`
- **Paper:** Liang, Ye, Wang, Pursel, Giles. *Investigating Active Learning for Concept Prerequisite Learning.* AAAI 2018 (EAAI track). <https://ojs.aaai.org/index.php/AAAI/article/view/11396>
- **Repository:** <https://github.com/harrylclc/AL-CPL-dataset>, commit `11397eaa3ea01c5e06fefcfc1c02a84f21164081` (2018-05-21)
- **Licence:** CC BY-NC-SA 4.0, stated in the repository README (there is no LICENSE file).
- **Built on:** Wang et al. 2016 (CIKM) Wiki concept-map dataset. **That upstream dataset's licence was not checked.**
- **Size (README):** data mining 120 concepts / 826 pairs / 292 prerequisites; geometry 89 / 1681 / 524; physics 153 / 1962 / 487; precalculus 224 / 2060 / 699.

| File (`data/`) | Bytes | Blob SHA |
|---|---|---|
| `data_mining.pairs` | 35,075 | `805dea8f6b48226bec5be32888a178208644a138` |
| `data_mining.preqs` | 12,555 | `bd85c4a7d16591c051eef3acc7f609a154e874d4` |
| `geometry.pairs` | 49,222 | `dede94b8be645b3b47cc034b22a73d4bf022ecfb` |
| `geometry.preqs` | 15,453 | `38083182e5d9ed0c002a012ebe035672b5b9774e` |
| `physics.pairs` | 57,748 | `b93e047eac939e16505294548493bc276cbf0632` |
| `physics.preqs` | 14,981 | `9cdf63da48f83e169ae37f3f5094dd674d879053` |
| `precalculus.pairs` | 66,503 | `664d47c9c9a2f13d6fff7c478b3ceb2c10050d82` |
| `precalculus.preqs` | 22,161 | `9bdbf89c8a20e58b3dd9e89462ff18107181d396` |

### University Course dataset: `university_course`
- **Paper:** Liang, Ye, Wu, Pursel, Giles. *Recovering Concept Prerequisite Relations from University Course Dependencies.* AAAI 2017, pp. 4786–4791. <https://ojs.aaai.org/index.php/AAAI/article/view/10550>
- **Repository:** <https://github.com/harrylclc/eaai17-cpr-recover>, "Release 1, 2017-01-10" (README), commit `95a7fa7311abc6fb0b8ef49d74d393f56b1bc05f`
- **Licence:** CC BY-NC-SA 4.0, stated in the repository README (there is no LICENSE file).

| File | Bytes | Blob SHA |
|---|---|---|
| `cs_annotations.tsv` | 185,586 | `20c0093a5f1d6346c096dbd3f71cf8abf522eb94` |
| `cs_preqs.csv` | 37,237 | `6a8ce08dc1e0e39a56154b58ab8d629e7be6b006` |

(`cs_courses.csv` and `cs_edges.csv`, the course-level data, are not needed by the loader.)

### LectureBank (1.0 prerequisite annotation): `lecturebank`. **Not used in evaluation: licence not stated**

The loader (`lecturebank.py`) and its tests stay so the work is reusable if a licence appears. The dataset is in no experiment plan or config, is not downloaded for this project, and none of its data or derived files may be committed.
- **Paper:** Li, Fabbri, Tung, Radev. *What Should I Learn First: Introducing LectureBank for NLP Education and Prerequisite Chain Learning.* AAAI 2019, 33(01):6674–6681. arXiv 1811.12181.
- **Repository:** <https://github.com/Yale-LILY/LectureBank>, folder `LB-Paper/`, commit `b237565ded5b112295fd5bc39035f53b0dd4286b` (2023-11-06). The repo also holds later lecture-file batches (LectureBank 2/3, CD). Those carry no prerequisite annotation in the README, so they are not used.
- **Licence: not stated.** Neither the repository README, the `LB-Paper/` README nor the paper states a licence, and the repository has no LICENSE file. The paper says only links to lectures are released "for copyright reasons". We did not request permission, so we do not use it.
- **Size (paper):** 208 topics, 921 positive and 41,829 negative pairs. Two annotators; positives are the intersection of their labels; Cohen's κ = 0.7.

| File (`LB-Paper/`) | Bytes | Blob SHA |
|---|---|---|
| `208topics.csv` | 14,387 | `3c1c6e41068732de2c793cf2e872bca83db452a1` |
| `prerequisite_annotation.csv` | 384,322 | `de806920310707fa8e87c1eb0247c3a26dea40a6` |

### What CC BY-NC-SA 4.0 means for us
Research use is fine, with attribution (cite the papers above). Anything we derive and share, such as converted gold files, must stay non-commercial and carry the same licence. We share neither: raw and converted files stay out of git.

## Download steps

Run from the repository root. Each step fetches only the files the loaders need, at the pinned commit. LectureBank is deliberately not downloaded (not used in evaluation).

```bash
# AL-CPL
mkdir -p data/benchmarks/al_cpl/data
for d in data_mining geometry physics precalculus; do for e in pairs preqs; do
  curl -fsSL -o "data/benchmarks/al_cpl/data/$d.$e" \
    "https://raw.githubusercontent.com/harrylclc/AL-CPL-dataset/11397eaa3ea01c5e06fefcfc1c02a84f21164081/data/$d.$e"
done; done

# University Course
mkdir -p data/benchmarks/university_course
for f in cs_annotations.tsv cs_preqs.csv; do
  curl -fsSL -o "data/benchmarks/university_course/$f" \
    "https://raw.githubusercontent.com/harrylclc/eaai17-cpr-recover/95a7fa7311abc6fb0b8ef49d74d393f56b1bc05f/$f"
done

# Verify: every SHA must match the tables above
git hash-object data/benchmarks/al_cpl/data/* data/benchmarks/university_course/*
```

## How labels are mapped

None of the three datasets distinguishes hard from soft prerequisites, so **every positive becomes `hard`** and every negative becomes `none`. Our `source` is always the prerequisite.

| Dataset | Raw line | Gold row | `agreement` |
|---|---|---|---|
| AL-CPL | `A,B` in `.preqs` (B is a prerequisite of A, README) | `B → A, hard` | empty (one expert-corrected label per pair) |
| AL-CPL | `A,B` in `.pairs` only | `B → A, none` | empty |
| University Course | `A,B` in `cs_preqs.csv` (majority vote; B is a prerequisite of A) | `B → A, hard` | votes for that direction / annotators of the pair, e.g. `2/3` |
| University Course | annotated pair not in `cs_preqs.csv` | `B → A, none` | "no relation" (label 3) votes / annotators |
| University Course | label `4` vote (undefined in the dataset README) | dropped | not counted in either share |
| LectureBank | `S,T,1` | `S → T, hard` | `2/2` (both annotators) |
| LectureBank | `S,T,0` | `S → T, none` | empty: 0 also covers pairs where one annotator said yes |

**Concepts:** Wikipedia titles become slugs (`Boosting_(machine_learning)` → `boosting_machine_learning`). The title with spaces becomes `name`, and the raw title is kept as an alias. Colliding slugs get `_2`, `_3` and are counted in the sanity line. Benchmarks have no pages, so `sources` points at the dataset file and **`page` holds the 1-based line number** where the concept first appears. For LectureBank, the Wikipedia URL becomes `description`.

### Scoring convention per dataset (decided 2026-11-01)

Our own gold (`data/gold/`) stays **direct-edge only**: a shortcut pair is `none`. A benchmark whose positives include transitive (shortcut) pairs is scored differently: we take the **transitive closure of our predicted edges** (`common.transitive_closure`) and compare it with the benchmark's labels. Otherwise every shortcut positive would count as a miss for a correct direct-edge graph.

| Dataset | Positives include transitive pairs? | How we score |
|---|---|---|
| AL-CPL | **Yes.** The README says positive pairs were added via transitivity. | Closure of our predictions vs. AL-CPL labels |
| University Course | **Yes, on the data** (not stated in the README or paper): 555 of 1007 positives are implied by other positives (first conversion, 2026-11-02). | **Closure** of our predictions vs. University Course labels (`scoring: closure` in `cdlp/validation/configs/rq1/university_course.json`) |
| LectureBank | n/a | **Not used in evaluation: licence not stated** |

The converter's sanity line reports `positives implied by other positives` for every graph: positive pairs that a path of other positives already implies. For AL-CPL this should be large by construction.

### First conversion (2026-11-02, files verified against the SHAs above)

| Graph | Concepts | Positive pairs | Negative pairs | Positives implied by other positives |
|---|---|---|---|---|
| `al_cpl_data_mining` | 120 | 292 | 534 | 180 |
| `al_cpl_geometry` | 89 | 524 | 1157 | 414 |
| `al_cpl_physics` | 153 | 487 | 1475 | 308 |
| `al_cpl_precalculus` | 224 | 699 | 1361 | 454 |
| `university_course` | 521 | 1007 | 1821 | 555 |

AL-CPL counts match the dataset README. No slug collisions. AL-CPL positives have no cycles. **University Course positives contain one cycle:** a strongly connected component of 12 concepts (21 positives inside it). Outside it, 542 of 986 positives are still implied, so closure scoring does not depend on the cycle.

**University Course label `4`: dropped.** `cs_annotations.tsv` contains 99 votes with label `4`, which the dataset README does not define (it lists 1–3). The converter drops them: they count neither for nor against a direction and are left out of the `k/n` agreement shares. No pair has only label-4 votes. This cannot change the positives, negatives or shortcut count (positives come only from `cs_preqs.csv`); the counts above come from the converter with this rule. Any other unknown label is still an error.

### Caveats for evaluation (read before using these numbers in the paper)
- **AL-CPL and University Course positives include transitive pairs** (see the convention above). Say in the paper which convention each number uses.
- **LectureBank direction** is taken from the paper ("the edge direction goes from concept vertex A to concept vertex B" when A is a prerequisite of B) and the column names (`Source_Topic_ID, Target_Topic_ID`). The README itself does not state it.
- **LectureBank negatives are not "both said no".** A 0 means the two annotators did not both say yes.

## Tasks, in order
- [x] **Verify each dataset before use:** official source, commit, file names and blob SHAs above
- [x] **Licence notes:** above; LectureBank's is not stated, so it is excluded from evaluation
- [x] **Download instructions:** above
- [x] Converter per dataset (`al_cpl.py`, `university_course.py`, `lecturebank.py`), with the mapping documented above
- [ ] Sanity report per dataset (concepts, edges, label balance, cycles) → `cdlp/benchmarks/results/`
- [ ] Run discovery + validation on AL-CPL and University Course for RQ1 (P / R / F1)

## RQ1 sample (decided 2026-11-02)

Every graph is scored on a seeded, stratified sample (`python -m cdlp.benchmarks.sample --n 200 --subset 100 --seed 42`): 200 labelled pairs per graph in proportion to its own positive rate, plus a nested 100-pair subset for self-consistency (the single judge is also reported on that subset). It writes `sample_pairs.csv`, `gold_edges_sample.csv`, `gold_edges_subset.csv`, `sample_concepts.json` and `sample.json` (counts and inverse-probability weights) next to each graph's gold file in `outputs/benchmarks/<course>/`.

| Graph | Labelled pairs | Positives | Sample (pos / neg) | Subset (pos / neg) | Concepts in sample |
|---|---|---|---|---|---|
| AL-CPL data mining | 826 | 292 | 71 / 129 | 36 / 64 | 99 |
| AL-CPL geometry | 1,681 | 524 | 62 / 138 | 31 / 69 | 82 |
| AL-CPL physics | 1,962 | 487 | 50 / 150 | 25 / 75 | 119 |
| AL-CPL precalculus | 2,060 | 699 | 68 / 132 | 34 / 66 | 152 |
| University Course | 2,828 | 1,007 | 71 / 129 | 36 / 64 | 207 |

University Course has 3,544 annotation rows but 2,828 distinct pairs: some pairs are annotated more than once (in either order), and the converter keeps one row per pair.

Discovery on a sample uses `--pairs` (benchmarks have no course text, so the candidate filter cannot run) with **`--pairs-direction given`**: the standard pairwise benchmark protocol (decided 2026-11-02). Each sampled pair is asked once, in the dataset's own orientation, and compared with its label. The model sees that orientation; direction errors are still measured where negatives include reversed pairs (AL-CPL). `--pairs-direction both` (the CLI default) asks each pair both ways instead, at twice the calls. Night 1 runs `scripts/rq1_night1.sh`; the commands it runs per graph are:

```bash
python -m cdlp.discovery --concepts outputs/benchmarks/<c>/sample_concepts.json \
    --pairs outputs/benchmarks/<c>/sample_pairs.csv --pairs-direction given \
    --out-dir outputs/rq1/<c> --stats outputs/rq1/<c>/discovery_only.stats.json
python -m cdlp.discovery --concepts outputs/benchmarks/<c>/sample_concepts.json \
    --baseline-only --num-ctx 16384 --out-dir outputs/rq1/<c> \
    --stats outputs/rq1/<c>/baseline_prompt.stats.json
```

The baseline lists every sampled concept in one prompt, which with its answer exceeds Ollama's default 4,096-token context, so it runs with `--num-ctx 16384`.

## Notes for the paper
- **Benchmarks used:** AL-CPL (Liang et al., 2018) and the University Course dataset (Liang et al., 2017), both CC BY-NC-SA 4.0, used for non-commercial research with attribution.
- **Excluded:** LectureBank (Li et al., 2019). Suggested wording: *"We did not use LectureBank because its repository and paper state no licence for the prerequisite annotations."*
- **Scoring convention:** state per dataset whether our predicted edges were compared directly or via their transitive closure (table above). AL-CPL and University Course both use the closure.

## Done when
Each dataset has verified source, version and licence notes here, the CLI converts it, and `pytest cdlp/benchmarks` passes.
