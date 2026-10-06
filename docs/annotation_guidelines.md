# Annotation guidelines (draft — agree on Day 1)

For each ordered pair **A → B**, ask: *Does a student need A to understand B?*

| Label | Meaning | Example |
|---|---|---|
| `hard` | B can't be understood without A; B is defined in terms of A | binary_tree → binary_search_tree |
| `soft` | A clearly helps, but B can be learned without it | recursion → binary_tree |
| `none` | No dependency, or the dependency runs the other way | graphs → avl_tree |

Rules:
1. Judge the **direct** dependency. Don't label `trees → avl_tree` as `hard` just because it holds through a chain; label `none` for shortcut pairs when an intermediate concept exists.
2. Judge using what **this course** teaches, not what you happen to know.
3. If you're unsure after 30 seconds, write `soft` and add a note.
4. Concepts: keep ones a lecture would title a section with. Drop too-fine ("left subtree") and too-broad ("computer science") ones.
