# Benchmarks · owner: Shreeya

Public prerequisite datasets, converted into our formats so discovery and validation can be scored beyond our own course.

**Question you answer:** *Do our results hold on data we didn't annotate ourselves?*

**You own (only you edit):** `cdlp/benchmarks/`

| | File | Notes |
|---|---|---|
| Input | the downloaded dataset folder (`--raw`, default `data/benchmarks/<dataset>/`) | Never commit raw data: `data/benchmarks/` is gitignored |
| Output | `<out-dir>/<course_id>/concepts.json` | Same contract as extraction |
| Output | `<out-dir>/<course_id>/gold_edges.csv` | Same columns as `data/gold/gold_edges.csv` (`source,target,label,agreement,note`), `label` ∈ `hard` · `soft` · `none` |

```bash
python -m cdlp.benchmarks --dataset al_cpl             # -> outputs/benchmarks/al_cpl_<domain>/ (4 domains)
python -m cdlp.benchmarks --dataset university_course  # -> outputs/benchmarks/university_course/
python -m cdlp.benchmarks --dataset lecturebank        # -> outputs/benchmarks/lecturebank/
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

### LectureBank (1.0 prerequisite annotation): `lecturebank`
- **Paper:** Li, Fabbri, Tung, Radev. *What Should I Learn First: Introducing LectureBank for NLP Education and Prerequisite Chain Learning.* AAAI 2019, 33(01):6674–6681. arXiv 1811.12181.
- **Repository:** <https://github.com/Yale-LILY/LectureBank>, folder `LB-Paper/`, commit `b237565ded5b112295fd5bc39035f53b0dd4286b` (2023-11-06). The repo also holds later lecture-file batches (LectureBank 2/3, CD). Those carry no prerequisite annotation in the README, so they are not used.
- **Licence: could not be confirmed.** Neither the repository README, the `LB-Paper/` README nor the paper states a licence, and the repository has no LICENSE file. The paper says only links to lectures are released "for copyright reasons". **Treat this as all rights reserved:** don't redistribute the data or the converted files, and ask the authors before reporting results on it in the paper.
- **Size (paper):** 208 topics, 921 positive and 41,829 negative pairs. Two annotators; positives are the intersection of their labels; Cohen's κ = 0.7.

| File (`LB-Paper/`) | Bytes | Blob SHA |
|---|---|---|
| `208topics.csv` | 14,387 | `3c1c6e41068732de2c793cf2e872bca83db452a1` |
| `prerequisite_annotation.csv` | 384,322 | `de806920310707fa8e87c1eb0247c3a26dea40a6` |

### What CC BY-NC-SA 4.0 means for us
Research use is fine, with attribution (cite the papers above). Anything we derive and share, such as converted gold files, must stay non-commercial and carry the same licence. We share neither: raw and converted files stay out of git.

## Download steps

Run from the repository root. Each step fetches only the files the loaders need, at the pinned commit.

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

# LectureBank (read the licence note above first)
mkdir -p data/benchmarks/lecturebank/LB-Paper
for f in 208topics.csv prerequisite_annotation.csv; do
  curl -fsSL -o "data/benchmarks/lecturebank/LB-Paper/$f" \
    "https://raw.githubusercontent.com/Yale-LILY/LectureBank/b237565ded5b112295fd5bc39035f53b0dd4286b/LB-Paper/$f"
done

# Verify: every SHA must match the tables above
git hash-object data/benchmarks/al_cpl/data/* data/benchmarks/university_course/* data/benchmarks/lecturebank/LB-Paper/*
```

## How labels are mapped

None of the three datasets distinguishes hard from soft prerequisites, so **every positive becomes `hard`** and every negative becomes `none`. Our `source` is always the prerequisite.

| Dataset | Raw line | Gold row | `agreement` |
|---|---|---|---|
| AL-CPL | `A,B` in `.preqs` (B is a prerequisite of A, README) | `B → A, hard` | empty (one expert-corrected label per pair) |
| AL-CPL | `A,B` in `.pairs` only | `B → A, none` | empty |
| University Course | `A,B` in `cs_preqs.csv` (majority vote; B is a prerequisite of A) | `B → A, hard` | votes for that direction / annotators of the pair, e.g. `2/3` |
| University Course | annotated pair not in `cs_preqs.csv` | `B → A, none` | "no relation" (label 3) votes / annotators |
| LectureBank | `S,T,1` | `S → T, hard` | `2/2` (both annotators) |
| LectureBank | `S,T,0` | `S → T, none` | empty: 0 also covers pairs where one annotator said yes |

**Concepts:** Wikipedia titles become slugs (`Boosting_(machine_learning)` → `boosting_machine_learning`). The title with spaces becomes `name`, and the raw title is kept as an alias. Colliding slugs get `_2`, `_3` and are counted in the sanity line. Benchmarks have no pages, so `sources` points at the dataset file and **`page` holds the 1-based line number** where the concept first appears. For LectureBank, the Wikipedia URL becomes `description`.

### Caveats for evaluation (read before using these numbers in the paper)
- **AL-CPL positives include transitive pairs.** Its authors added positives by transitivity, so shortcut pairs are positive in AL-CPL. Our gold and our discovery treat shortcut pairs as `none`. Scored naively, our recall on AL-CPL is understated. Compare against the transitive closure of our predicted edges, or say clearly which convention each number uses.
- **LectureBank direction** is taken from the paper ("the edge direction goes from concept vertex A to concept vertex B" when A is a prerequisite of B) and the column names (`Source_Topic_ID, Target_Topic_ID`). The README itself does not state it.
- **LectureBank negatives are not "both said no".** A 0 means the two annotators did not both say yes.

## Tasks, in order
- [x] **Verify each dataset before use:** official source, commit, file names and blob SHAs above
- [x] **Licence notes:** above; LectureBank's is unconfirmed
- [x] **Download instructions:** above
- [x] Converter per dataset (`al_cpl.py`, `university_course.py`, `lecturebank.py`), with the mapping documented above
- [ ] Sanity report per dataset (concepts, edges, label balance, cycles) → `cdlp/benchmarks/results/`
- [ ] Run discovery + validation on each converted dataset for RQ1 (P / R / F1)

## Done when
Each dataset has verified source, version and licence notes here, the CLI converts it, and `pytest cdlp/benchmarks` passes.
