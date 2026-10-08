import json
from pathlib import Path

from cdlp.shared.llm import chat_json


def load_prompt() -> str:
    prompt_path = Path(__file__).parent / "prompts" / "quiz_v1.txt"
    return prompt_path.read_text()


def generate_quiz_items(
    concepts: list[dict],
    chunks: list[dict],
) -> list[dict]:
    prompt_template = load_prompt()

    chunk_map = {
        chunk["chunk_id"]: chunk
        for chunk in chunks
    }

    quiz_items = []

    for concept in concepts:
        evidence = []

        for source in concept.get("sources", []):
            chunk_id = source["chunk_id"]

            if chunk_id in chunk_map:
                evidence.append(chunk_map[chunk_id])

        evidence_text = "\n".join(
            f"Chunk ID: {chunk['chunk_id']}\n{chunk['text']}"
            for chunk in evidence
        )

        prompt = prompt_template.format(
            concept_id=concept["id"],
            concept_name=concept["name"],
            concept_description=concept.get(
                "description",
                "",
            ),
            evidence=evidence_text,
        )

        result = chat_json(
            prompt,
            prompt_version="quiz_v1",
            temperature=0.2,
        )

        items = result.get("items", [])

        for item in items:
            quiz_items.append(
                {
                    "id": f"q{len(quiz_items) + 1}",
                    "concept_id": concept["id"],
                    "question": item["question"],
                    "options": item["options"],
                    "answer": item["correct_answer"],
                    "explanation": item["explanation"],
                    "evidence_chunk_ids": item.get(
                        "evidence_chunk_ids",
                        [
                            chunk["chunk_id"]
                            for chunk in evidence
                        ],
                    ),
                }
            )

    return quiz_items


def write_quiz_items(
    items: list[dict],
    output_path: Path,
) -> None:
    output_path.write_text(
        json.dumps(
            items,
            indent=2,
        )
    )