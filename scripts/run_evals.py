# -*- coding: utf-8 -*-
"""运行不需要 LLM 或密钥的固定种子评估。"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from coc_keeper.evaluation import default_rule_suite


def main() -> None:
    suite = default_rule_suite()
    results = suite.run()
    report = {
        "summary": suite.score(results),
        "results": [result.__dict__ for result in results],
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    raise SystemExit(0 if all(result.passed for result in results) else 1)


if __name__ == "__main__":
    main()
