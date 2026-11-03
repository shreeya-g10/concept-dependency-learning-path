# Discovery results

## order_bias_ds101.json (2026-11-03)

Measures whether a neutral prompt's answer depends on which concept is called A. Every pair was asked twice, A and B swapped, with `qwen2.5:7b-instruct` and `discover_v3_1`, on the 85 filtered ds101 concepts: the 5 positive gold pairs plus a seeded sample of 30 other candidate pairs (`order_bias_ds101_pairs.json`, settings in `../configs/order_bias_ds101.json`).

- **Measurement only.** The prompt and the checks were not changed because of it. The bias stays as a limit to report.
- **Gold pairs were seen.** The rule in `../configs/order_rule_v1.json` draws its reasoning from the 30 non-gold sample pairs, but the 5 positive gold pairs were also visible when it was chosen. Say so wherever the rule is described.
- **Two gold IDs were renamed for this test only:** the gold labels say `trees` and `graphs`; the filtered concepts name them `general_tree` and `graph`. The mapping is in the config, and the frozen gold files were not edited.
