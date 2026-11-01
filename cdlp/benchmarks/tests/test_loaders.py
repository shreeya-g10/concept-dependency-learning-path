"""Loader semantics on the hand-made fixtures: direction, labels, agreement, traceability."""

from pathlib import Path

import pytest

from cdlp.benchmarks import al_cpl, lecturebank, university_course
from cdlp.benchmarks.common import SlugMap, slugify

FIXTURES = Path(__file__).parent / "fixtures"


def gold(course) -> dict:
    return {k: (r["label"], r["agreement"]) for k, r in course.rows.items()}


def test_slugify_wikipedia_titles():
    assert slugify("Boosting_(machine_learning)") == "boosting_machine_learning"
    assert slugify("Bayes'_theorem") == "bayes_theorem"
    assert slugify("K-means_clustering") == "k_means_clustering"


def test_slug_collisions_get_a_suffix():
    slug = SlugMap()

    assert [slug("C++"), slug("C"), slug("C++")] == ["c", "c_2", "c"]
    assert slug.collisions == [("C", "c_2")]


def test_al_cpl_column_two_is_the_prerequisite():
    (dm,) = al_cpl.load(FIXTURES / "al_cpl", domains=("data_mining",))

    assert dm.course_id == "al_cpl_data_mining"
    assert gold(dm) == {
        ("euclidean_distance", "k_means_clustering"): ("hard", ""),
        ("bayes_theorem", "k_means_clustering"): ("none", ""),
        ("bayes_theorem", "naive_bayes_classifier"): ("hard", ""),
        ("decision_tree_learning", "boosting_machine_learning"): ("hard", ""),
        ("k_means_clustering", "euclidean_distance"): ("none", ""),  # the reversed pair
    }


def test_al_cpl_concepts_are_traceable_to_a_file_line():
    (dm,) = al_cpl.load(FIXTURES / "al_cpl", domains=("data_mining",))

    boosting = dm.concepts["boosting_machine_learning"]
    assert boosting["name"] == "Boosting (machine learning)"
    assert boosting["aliases"] == ["Boosting_(machine_learning)"]
    assert boosting["sources"] == [{"doc": "data_mining.pairs", "page": 4}]  # page = line


def test_al_cpl_loads_all_four_domains():
    ids = [c.course_id for c in al_cpl.load(FIXTURES / "al_cpl")]

    assert ids == [f"al_cpl_{d}" for d in al_cpl.DOMAINS]


def test_university_course_majority_direction_and_agreement():
    (uc,) = university_course.load(FIXTURES / "university_course")

    assert gold(uc) == {
        # label 1 x2, 2 x1 -> "B before A": Linear_algebra -> Machine_learning
        ("linear_algebra", "machine_learning"): ("hard", "2/3"),
        # label 2 means A before B; cs_preqs lists it reversed: Algorithm -> DP
        ("algorithm", "dynamic_programming"): ("hard", "2/3"),
        # not in cs_preqs.csv: none, with the share of "3" votes
        ("linear_programming", "game_theory"): ("none", "2/3"),
    }


def test_university_course_drops_undefined_label_4(tmp_path):
    # label 4 occurs in the released data but is not defined by the dataset README
    (tmp_path / "cs_annotations.tsv").write_text(
        "Concept_A\tConcept_B\tAnnotator_1\tAnnotator_2\tAnnotator_3\n"
        "A\tB\t1\t4\t1\n"
        "C\tD\t3\t4\t1\n"
    )
    (tmp_path / "cs_preqs.csv").write_text("A,B\n")
    (uc,) = university_course.load(tmp_path)

    assert gold(uc) == {("b", "a"): ("hard", "2/2"), ("d", "c"): ("none", "1/2")}


def test_university_course_rejects_unknown_labels(tmp_path):
    (tmp_path / "cs_annotations.tsv").write_text("Concept_A\tConcept_B\tAnnotator_1\nA\tB\t7\n")
    (tmp_path / "cs_preqs.csv").write_text("")

    with pytest.raises(ValueError, match="unknown labels"):
        university_course.load(tmp_path)


def test_lecturebank_source_is_the_prerequisite_and_names_may_have_commas():
    (lb,) = lecturebank.load(FIXTURES / "lecturebank")

    assert lb.concepts["parsing_dependency"]["name"] == "Parsing, Dependency"
    assert lb.concepts["word_embeddings"]["description"].endswith("/Word_embedding")
    assert gold(lb) == {
        ("language_modeling", "word_embeddings"): ("hard", "2/2"),
        ("language_modeling", "parsing_dependency"): ("none", ""),
        ("word_embeddings", "parsing_dependency"): ("hard", "2/2"),
        ("word_embeddings", "language_modeling"): ("none", ""),
        ("parsing_dependency", "language_modeling"): ("none", ""),
    }


@pytest.mark.parametrize(
    "annotation, error",
    [("1,2,2\n", "If_prerequisite"), ("1,9,1\n", "unknown topic id"), ("1,2\n", "3 columns")],
)
def test_lecturebank_bad_rows_fail_loudly(tmp_path, annotation, error):
    (tmp_path / "208topics.csv").write_text("1,A,https://x\n2,B,https://y\n")
    (tmp_path / "prerequisite_annotation.csv").write_text(annotation)

    with pytest.raises(ValueError, match=error):
        lecturebank.load(tmp_path)


def test_transitive_closure_and_implied_pairs():
    from cdlp.benchmarks.common import implied_pairs, transitive_closure

    chain = {("a", "b"), ("b", "c"), ("c", "d")}
    assert transitive_closure(chain) == chain | {("a", "c"), ("a", "d"), ("b", "d")}
    assert implied_pairs(chain) == set()
    assert implied_pairs(chain | {("a", "d")}) == {("a", "d")}


def test_stats_count_transitive_positives():
    (geo,) = al_cpl.load(FIXTURES / "al_cpl", domains=("geometry",))
    (lb,) = lecturebank.load(FIXTURES / "lecturebank")

    assert geo.stats()["transitive_positives"] == 0
    assert lb.stats()["transitive_positives"] == 0  # 1->2, 2->3 but no 1->3 positive
