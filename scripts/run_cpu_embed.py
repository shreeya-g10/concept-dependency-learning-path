"""Run a cdlp module with the embedding model on the CPU.

On an 8 GB laptop the embedding model and Ollama's model can't share the GPU.

    python scripts/run_cpu_embed.py cdlp.validation --relationships ... --out ...
"""

import runpy
import sys
from pathlib import Path

import sentence_transformers

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

_original = sentence_transformers.SentenceTransformer
sentence_transformers.SentenceTransformer = lambda *a, **k: _original(*a, **{**k, "device": "cpu"})

module = sys.argv[1]
sys.argv = [module, *sys.argv[2:]]
runpy.run_module(module, run_name="__main__", alter_sys=True)
