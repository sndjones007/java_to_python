"""
Chunker utility to split large Java methods into smaller parts
based on token/character limits from EnvConfig.
"""

from typing import List
from env_config import EnvConfig

class MethodCodeChunker:
    def __init__(self, token_limit: int = None, template_overhead: int = 500):
        # token_limit from .env
        self.token_limit = token_limit or EnvConfig.LLM_TOKEN_LIMIT
        # reserve space for template text
        self.effective_limit = self.token_limit - template_overhead
        # approximate char limit
        self.approx_char_limit = self.effective_limit * 4

    def chunk(self, raw_code: str) -> List[str]:
        lines = raw_code.split("\n")
        chunks, current_chunk, current_size = [], [], 0

        for line in lines:
            line_len = len(line) + 1
            if current_size + line_len > self.approx_char_limit and current_chunk:
                chunks.append("\n".join(current_chunk))
                current_chunk, current_size = [], 0
            current_chunk.append(line)
            current_size += line_len

        if current_chunk:
            chunks.append("\n".join(current_chunk))

        return chunks