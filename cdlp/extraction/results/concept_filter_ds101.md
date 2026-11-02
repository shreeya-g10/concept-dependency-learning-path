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

## Check against the hand-annotated list

Run once, after the settings were committed in `3334662`. Nothing was changed because of it, so the settings were not tuned on gold.

| Exact id match with `data/gold/gold_concepts.json` | Before | After |
|---|---|---|
| Gold concepts found (of 6) | 4 | 4 |
| Recall | 0.67 | 0.67 |
| Precision | 0.015 | 0.047 |

The filter lost no gold concept. Both misses exist before the filter too: gold `graphs` is the node `graph` (a naming mismatch), and gold `trees` has no node of its own (the closest is `general_tree`, with the alias "Tree").

Do not report the precision. The gold list has only 6 concepts and does not cover the course, so most correct concepts count as false positives. This is a check that core topics survive, not an unbiased measure of filter quality.

## Kinds of bad concepts in the 259

Sorted by hand, by reading the list without gold. Each concept has one kind, and the kinds are one reader's judgement, so these counts are not an independent measure.

| Kind | Example | Count | Removed | Still kept |
|---|---|---:|---:|---|
| Code names | `gather_u`, `push_black` | 41 | 39 | `remove_fixup`, `resize` |
| Aside structures, named in passing or in exercises | `treque`, `splay_tree` | 27 | 27 | |
| Generic words and vague labels | `lemma`, `array_representation` | 25 | 21 | `borrowing`, `running_time_analysis`, `array_based_implementations`, `shift_elements` |
| Exercise labels | `avl_tree_exercise` | 21 | 21 | |
| Near-duplicates | `amortized_cost`, `array_based_stack` | 19 | 14 | `amortized_time`, `no_red_edge`, `rebuilding`, `space_efficient_array_stack`, `merging` |
| Examples | `factorial`, `palindrome_check` | 17 | 16 | `towers_of_hanoi` |
| Not marked as bad | | 109 | 36 | 73 others |

## Useful topics lost

Of the 36 removed concepts not marked as bad, these are the ones a teacher would likely miss. The filter removes them because the text gives them little support outside the exercises.

- Tree traversals: `pre_order_traversal` (used by the demo topic list, with 3 quiz items), `postorder_traversal`. `tree_traversal` and `traversal` remain.
- Graphs: `directed_graph` (the text only says "undirected graph"), `connected_graph`, `strongly_connected_graph`, `dense_graph`, `shortest_path`.
- Stack and search basics: `push_operation`, `pop_operation`, `find_operation`, `successful_search`, `unsuccessful_search`. `stack`, `queue` and `binary_search_tree` remain.
- Trees: `descendant`, `parent_pointers`, `left_leaning_red_black_tree`.
- Other: `circular_array`, `modular_arithmetic`, and the removed code names `rotate_left`, `bubble_up`, `trickle_down`, `flip_left`, `push_black`, `pull_black`, `splice`.

## Kept (85)

- In a heading (37): `abstract_data_type`, `adjacency_list`, `adjacency_matrix`, `array_based_list`, `array_based_queue`, `array_deque`, `array_stack`, `avl_tree`, `balanced_binary_tree`, `binary_search_tree`, `binary_tree`, `deque`, `doubly_linked_list`, `dual_array_deque`, `fast_array_stack`, `general_tree`, `graph`, `heap`, `linked_list`, `meldable_heap`, `node`, `partial_rebuilding`, `queue`, `rebuilding`, `recursive_function`, `red_black_tree`, `rootish_array_stack`, `scapegoat_tree`, `singly_linked_list`, `space_efficient_array_stack`, `space_efficient_linked_list`, `stack`, `towers_of_hanoi`, `traversal`, `tree_traversal`, `two_four_tree`, `unbalanced_binary_search_tree`
- Many source chunks (4): `add_operation`, `recursion`, `remove_operation`, `resize`
- Many mentions (34): `amortized_analysis`, `amortized_time`, `backing_array`, `black_height`, `block_size`, `breadth_first_traversal`, `constant_time`, `cycle`, `depth_first_search`, `depth_of_node`, `double_black_node`, `dummy_node`, `edge`, `expected_time`, `external_node`, `height_of_tree`, `height_property`, `left_leaning_property`, `logarithmic_time`, `merging`, `no_red_edge`, `no_red_edge_property`, `path`, `random_walk`, `recursive_algorithm`, `remove_fixup`, `rotation`, `scapegoat_node`, `shift_elements`, `sibling`, `sset`, `subtree`, `vertex`, `wasted_space`
- Several documents (6): `ancestor`, `array_based_implementations`, `borrowing`, `forest`, `logarithmic_height`, `potential_method`
- Source chunks and mentions (4): `degree_property`, `height_of_node`, `meld`, `running_time_analysis`

## Removed (174)

- Generic word (5): `correctness`, `lemma`, `removal`, `theorems`, `theoretical_analysis`
- Code name (31): `add_before`, `add_child`, `add_edge`, `add_fixup`, `add_i_x`, `bubble_up`, `decrease_key`, `find_x`, `flip_left`, `gather_method`, `gather_u`, `get_node`, `get_set_operations`, `grow_method`, `has_edge`, `in_edges`, `insert_fixup`, `out_edges`, `pull_black`, `push_black`, `rebuild_u`, `remove_edge`, `remove_i`, `remove_i_x`, `remove_node`, `rotate_left`, `shrink_method`, `splice`, `spread_method`, `spread_u`, `trickle_down`
- Only in exercises or summaries (61): `amortized_complexity`, `array_based_data_structures`, `array_based_list_modification`, `array_based_pointers`, `array_rotation`, `avl_rebalancing`, `avl_removal`, `avl_removal_complexity`, `avl_tree_comparison`, `avl_tree_exercise`, `avl_tree_experiments`, `avl_tree_performance`, `balance_invariant`, `binary_search_tree_deletion`, `binary_search_tree_insertion`, `binary_search_tree_range_query`, `binary_tree_shape`, `bit_representation`, `bitwise_and`, `bitwise_exclusive_or`, `check_size`, `connected_component_labeling`, `connected_graph`, `countdown_tree`, `cubish_array_stack`, `d_ary_heap`, `d_ary_tree`, `dijkstra_shortest_path_algorithm`, `double_linked_list`, `dynamite_tree`, `height_bound`, `incidence_matrix`, `kth_smallest_value`, `left_child_right_child_pointers`, `maze_exploration`, `merge_sort`, `min_deque`, `min_queue`, `min_stack`, `pairing_heap`, `palindrome_check`, `planarity_testing`, `random_queue`, `recursive_methods`, `red_black_tree_exercise`, `red_black_tree_experiments`, `red_black_tree_implementations`, `red_black_tree_performance`, `reverse_operation`, `rotate_operation`, `search_path_length`, `size_of_subtree`, `space_efficient_selist`, `spanning_forest`, `splitting`, `strongly_connected_graph`, `treque`, `truncate_operation`, `two_level_tiered_vector`, `universal_sink`, `weight_balanced_tree`
- Weak evidence (77): `amortized_cost`, `array_based_deque`, `array_based_stack`, `array_representation`, `array_summation`, `b_tree`, `back_stack`, `balance_method`, `balance_operation`, `block_based_data_structure`, `block_based_insertion`, `block_indexing`, `block_management`, `bounded_deque`, `child_access`, `circular_array`, `credit_scheme`, `credit_system`, `dense_graph`, `descendant`, `directed_graph`, `entropy`, `expected_running_time`, `eytzingers_method`, `factorial`, `fast_array_copying`, `fibonacci_sequence`, `find_operation`, `flip_color`, `flipping`, `fragile_node`, `front_stack`, `geometric_series`, `get_operation`, `heapsort`, `indexing_in_data_structures`, `initialize_operation`, `left_leaning_red_black_tree`, `linked_list_based_implementations`, `logarithmic_time_complexity`, `matrix_multiplication`, `modular_arithmetic`, `non_recursive_algorithm`, `non_recursive_traversal`, `ordered_binary_tree`, `out_degree`, `parent_pointers`, `pop_operation`, `postorder_traversal`, `pre_order_traversal`, `push_operation`, `quadratic_equation_solution`, `reachable_vertex`, `rebuild_operation`, `rooted_binary_tree`, `rugged_node`, `set_node`, `set_operation`, `shortest_path`, `size_function`, `size_of_a_node`, `skiplist`, `skiplist_sset`, `space_overhead`, `space_usage_analysis`, `splay_tree`, `successful_search`, `timetable_conflict_graph`, `treap`, `tree_edges`, `tree_initialization`, `tree_notation`, `union_find`, `unsuccessful_search`, `unwinding_phase`, `winding_phase`, `xor_list`
