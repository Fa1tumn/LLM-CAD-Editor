"""
Model wrapper for the 7~14B LoRA fine-tuned model.

A unified load/inference interface that isolates the underlying
transformers+peft details. See deploy/quantize.py for quantized
inference (single 24GB GPU, int4).
"""
from __future__ import annotations


class EditModel:
    def __init__(self, base: str, lora_path: str | None = None, quantized: bool = False):
        self.base = base
        self.lora_path = lora_path
        self.quantized = quantized
        # TODO(M3): transformers load + peft LoRA attach + optional bitsandbytes quantization

    def generate(self, prompt: str, valid_refs: list[str] | None = None) -> str:
        """Emit edited DSL.

        When valid_refs is non-empty, constrained decoding is enabled,
        forbidding generation of references that no longer exist (RQ2).
        """
        # TODO(M3): implement generation; valid_refs → logit constraints or post-hoc filtering
        raise NotImplementedError
