# quiz_check_v3 replay on the ds101 review drafts

Working test on the questions that shaped the checks. Not an accuracy result.

Check version `quiz_check_v3`, second model `llama3.1:8b`, prompt `quiz_check_v2`, temperature 0.0, seed 42, date 2026-11-03. Generated from `quiz_check_v3_replay_ds101.json`. Drafts: `quiz_v2`, 32 raw, 12 reached the second model. Calls: 2 new, 10 cached.

| Topic | Question | v2 | v3 | Why |
|---|---|---|---|---|
| avl_tree | What is the maximum depth of an AVL tree with n nodes? | drop (quote_not_in_book) | keep |  |
| avl_tree | How many cases are there for the bottommost unbalanced node after an insertion? | drop (not_about_topic) | drop | not_about_topic |
| avl_tree | What is the key property of an AVL tree that ensures efficient search operations? | keep | keep |  |
| avl_tree | What is the time complexity of insert and delete operations in an AVL tree? | drop (quote_not_in_book) | drop | subject_not_in_source: question says "time complexity" (running_time_analysis); not in the quote or its source chunk |
| binary_search_tree | What is the binary search tree property in a BinarySearchTree? | drop (check_several_true) | drop | check_several_true |
| binary_search_tree | What can happen to a BinarySearchTree? | keep | drop | answer_not_supported: 0.17 of the answer's content words are in the quote |
| binary_search_tree | What is a potential problem with BinarySearchTrees? | drop (near_duplicate) | keep |  |
| binary_search_tree | What is an example of a BinarySearchTree? | keep | drop | answer_not_supported: 0.00 of the answer's content words are in the quote |
| binary_tree | What is the root node in a binary tree? | keep | keep |  |
| binary_tree | How are the children of a node in a binary tree typically distinguished? | keep | keep |  |
| binary_tree | What is the maximum degree of any node in a binary tree? | keep | keep |  |
| binary_tree | What is the height of a binary tree? | keep | drop | answer_not_supported: 0.00 of the answer's content words are in the quote |
| breadth_first_traversal | What is the primary data structure used to implement the queue in a breadth-first traversal? | drop (no_source_quote) | drop | no_source_quote |
| breadth_first_traversal | Why is an auxiliary boolean array used in the breadth-first traversal algorithm? | keep | drop | answer_not_supported: 0.17 of the answer's content words are in the quote |
| breadth_first_traversal | What is the time complexity of the breadth-first traversal algorithm? | keep | drop | subject_not_in_source: question says "time complexity" (running_time_analysis); not in the quote or its source chunk |
| breadth_first_traversal | What is the order in which nodes are added to the queue during a breadth-first traversal starting from node 0? | drop (quote_not_in_book) | drop | subject_not_in_source: question says "queue" (queue); not in the quote or its source chunk |
| graph | What is a graph in mathematics? | drop (check_several_true) | drop | check_several_true |
| graph | What is a cycle in a graph? | drop (quote_not_in_book) | drop | quote_not_in_book |
| graph | What is the purpose of the seen array in the Breadth-First Search algorithm? | drop (not_about_topic) | drop | not_about_topic |
| graph | What is an adjacency matrix used for in graph representation? | keep | keep |  |
| queue | What is the main characteristic of a Queue data structure? | drop (check_several_true) | drop | check_several_true |
| queue | Why is an ArrayStack not a good choice for implementing a Queue? | drop (check_several_true) | drop | answer_not_supported: 0.00 of the answer's content words are in the quote |
| queue | What would make implementing a Queue easier? | keep | drop | answer_not_supported: 0.00 of the answer's content words are in the quote |
| queue | What is the main challenge in implementing an efficient ArrayQueue? | drop (not_about_topic) | drop | not_about_topic |
| rotation | What does rotation do in a red-black tree? | keep | drop | subject_not_in_source: question says "red black tree" (red_black_tree); not in the quote or its source chunk |
| rotation | When might a rotation be needed in a red-black tree? | keep | drop | subject_not_in_source: question says "red black tree" (red_black_tree); not in the quote or its source chunk |
| rotation | What is the purpose of rotation in a red-black tree? | drop (near_duplicate) | drop | subject_not_in_source: question says "red black tree" (red_black_tree); not in the quote or its source chunk |
| rotation | How does rotation affect the height of a red-black tree? | drop (check_quote_no_proof) | drop | answer_not_supported: 0.00 of the answer's content words are in the quote |
| traversal | What is the first step in preorder traversal of a general tree? | drop (check_disagrees) | drop | check_disagrees |
| traversal | Why is inorder traversal not useful for general trees? | keep | keep |  |
| traversal | How does preorder traversal handle the children of a node? | keep | drop | answer_not_supported: 0.00 of the answer's content words are in the quote |
| traversal | What is the main difference between breadth-first search in graphs and trees? | drop (not_about_topic) | drop | not_about_topic |
