# -*- coding: utf-8 -*-
"""零外部服务的规则书 BM25 检索。

规则全文按页切块，命中结果始终保留页码，方便 KP 给出可追溯的出处。
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


CORE_RULES_TEXT = """===== 第 70 页 =====
百分骰检定使用技能或属性值作为目标。困难难度为半值，极难难度为五分之一值。
奖励骰额外掷十位骰并取较小结果，惩罚骰取较大结果。
===== 第 78 页 =====
对抗检定比较双方成功度；成功度相同时，技能或属性值较高的一方获胜。
===== 第 104 页 =====
战斗中攻击必须通过技能检定。伤害先扣除护甲；单次伤害达到最大生命值的一半会造成重伤。
===== 第 133 页 =====
理智检定成功与失败使用不同的理智损失表达式。单次损失五点或更多需要进行智力检定以判断临时性疯狂。
===== 第 139 页 =====
一个游戏日内累计损失达到当日开始时理智值的五分之一，会进入不定性疯狂；理智降至零会永久疯狂。
"""


def tokenize(text: str) -> list[str]:
    """中英文混合分词：中文按字切分，英文/数字按词切分。"""
    tokens: list[str] = []
    for part in re.findall(r"[\u4e00-\u9fff]|[A-Za-z0-9_]+", text.lower()):
        tokens.append(part)
    return tokens


@dataclass(frozen=True)
class RuleChunk:
    page: int
    text: str
    score: float = 0.0


class RuleIndex:
    """内存 BM25 索引，适合规则书规模的几百页文本。"""

    def __init__(self, chunks: Iterable[RuleChunk]):
        self.chunks = list(chunks)
        self._tokens = [tokenize(c.text) for c in self.chunks]
        self._lengths = [len(t) for t in self._tokens]
        self._avgdl = sum(self._lengths) / max(1, len(self._lengths))
        self._df: dict[str, int] = {}
        for tokens in self._tokens:
            for token in set(tokens):
                self._df[token] = self._df.get(token, 0) + 1

    @classmethod
    def from_text(cls, text: str) -> "RuleIndex":
        pattern = re.compile(r"=====\s*第\s*(\d+)\s*页\s*=====\s*")
        matches = list(pattern.finditer(text))
        chunks: list[RuleChunk] = []
        for i, match in enumerate(matches):
            end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
            body = text[match.end():end].strip()
            if body:
                chunks.append(RuleChunk(page=int(match.group(1)), text=body))
        if not chunks and text.strip():
            chunks.append(RuleChunk(page=0, text=text.strip()))
        return cls(chunks)

    @classmethod
    def from_file(cls, path: str | Path) -> "RuleIndex":
        return cls.from_text(Path(path).read_text(encoding="utf-8"))

    def search(self, query: str, *, limit: int = 5, min_score: float = 0.0) -> list[RuleChunk]:
        terms = tokenize(query)
        if not terms or not self.chunks:
            return []
        k1, b = 1.5, 0.75
        n = len(self.chunks)
        scored: list[RuleChunk] = []
        for chunk, tokens, length in zip(self.chunks, self._tokens, self._lengths):
            counts: dict[str, int] = {}
            for token in tokens:
                counts[token] = counts.get(token, 0) + 1
            score = 0.0
            for term in terms:
                tf = counts.get(term, 0)
                if not tf:
                    continue
                df = self._df.get(term, 0)
                idf = math.log(1 + (n - df + 0.5) / (df + 0.5))
                norm = tf * (k1 + 1) / (tf + k1 * (1 - b + b * length / max(1, self._avgdl)))
                score += idf * norm
            if score > max(0.0, min_score):
                scored.append(RuleChunk(chunk.page, chunk.text, score))
        scored.sort(key=lambda c: (-c.score, c.page))
        return scored[: max(1, int(limit))]


def load_default_index(data_path: str | Path | None = None) -> RuleIndex:
    """加载 ``data/rulebook/fulltext.txt``，不存在时返回空索引。"""
    if data_path is None:
        data_path = Path(__file__).resolve().parents[3] / "data" / "rulebook" / "fulltext.txt"
    path = Path(data_path)
    return RuleIndex.from_file(path) if path.exists() else RuleIndex.from_text(CORE_RULES_TEXT)


def search_rules(query: str, *, limit: int = 5, data_path: str | Path | None = None) -> list[dict]:
    """返回可直接交给 Agent 的规则命中列表。"""
    return [
        {"page": hit.page, "score": round(hit.score, 4), "text": hit.text}
        for hit in load_default_index(data_path).search(query, limit=limit)
    ]
