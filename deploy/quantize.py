"""
Quantization for single 24GB GPU inference (RQ4/G6).

Prior work used a 32B model (8x A100); this work targets on-prem
deployment with a 7~14B model + int4 quantization, aiming for
latency/edit ≤30 seconds. Quantized performance loss on G1–G3 must be
re-benchmarked after quantization.
"""
from __future__ import annotations


def quantize(model_path: str, out_path: str, bits: int = 4) -> None:
    # TODO(M10): bitsandbytes / GPTQ int4 quantization
    raise NotImplementedError
