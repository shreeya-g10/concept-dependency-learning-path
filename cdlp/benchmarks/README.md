# Benchmarks · owner: Shreeya

Public prerequisite datasets, converted into our formats so discovery and validation can be scored beyond our own course.

**Question you answer:** *Do our results hold on data we didn't annotate ourselves?*

**You own (only you edit):** `cdlp/benchmarks/`

| | File | Notes |
|---|---|---|
| Input | the downloaded dataset folder (`--raw`) | Never commit the raw data; keep it out of git |
| Output | `concepts.json` | Same contract as extraction, `course_id` = dataset name |
| Output | `gold_edges.csv` | Same columns as `data/gold/gold_edges.csv` (`source,target,label,agreement,note`), `label` ∈ `hard` · `soft` · `none` |

`--dataset` is one of `al_cpl`, `university_course`, `lecturebank`.

## Tasks, in order
- [ ] **Verify each dataset before use:** find the official source (paper + repository) and record in this README the exact URL, version or commit, file names and checksum you downloaded. Don't rely on secondary mirrors or remembered links; any citation needs checking against the actual paper
- [ ] **Licence notes:** record each dataset's licence and any terms (research only, no redistribution, attribution). If a licence is unclear, don't redistribute the data or derived files, and ask before using it in the paper
- [ ] **Download instructions:** a short, reproducible step per dataset (where to put it, e.g. `data/benchmarks/<dataset>/`, which must stay out of git)
- [ ] Converter per dataset: concepts → stable slugs; labelled pairs → `hard` / `soft` / `none`. Document how the dataset's labels map to hard/soft, since most datasets only say "prerequisite or not"
- [ ] Sanity report per dataset: number of concepts, edges, label balance, cycles → `cdlp/benchmarks/results/`
- [ ] Run discovery + validation on each converted dataset for RQ1 (P / R / F1)

## Done when
Each dataset has verified source, version and licence notes here, the CLI converts it, and `pytest cdlp/benchmarks` passes.
