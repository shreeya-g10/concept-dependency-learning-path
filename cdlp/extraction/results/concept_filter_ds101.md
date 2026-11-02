# Concept filter on ds101

`concept_filter_ds101.json` holds the settings, the input file hashes and the decision and evidence for each concept.

Settings were chosen by reading the ds101 concept list and chunks, without opening `data/gold`. They were committed before the gold comparison was run, and they were not changed after it. Because they were chosen on this same course, they have not been shown to work on another course.

| | Concepts |
|---|---|
| Before | 259 |
| After | 85 |
| Removed: weak evidence | 77 |
| Removed: only in exercises or summaries | 61 |
| Removed: code name | 31 |
| Removed: generic word | 5 |
