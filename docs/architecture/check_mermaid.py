#!/usr/bin/env python3
"""check_mermaid.py — md 내 ```mermaid 블록 구조 검증(오프라인·표준 라이브러리만).

완전 파서가 아니라 자주 깨지는 항목 검사:
  · 다이어그램 타입 선언(graph/flowchart/sequenceDiagram/stateDiagram...)
  · 블록 내부 펜스(```) 잔존 금지
  · subgraph/end 균형, []·{}·() 균형, 따옴표(") 짝수
"""
import re
import sys

VALID = ("graph ", "flowchart ", "sequenceDiagram", "stateDiagram",
         "erDiagram", "classDiagram", "graph\n", "flowchart\n")


def check(path):
    text = open(path, encoding="utf-8").read()
    blocks = re.findall(r"```mermaid\n(.*?)```", text, re.S)
    if not blocks:
        print(f"FAIL {path}: mermaid 블록 없음")
        return 1
    errs = []
    for i, b in enumerate(blocks, 1):
        first = next((ln.strip() for ln in b.splitlines() if ln.strip()), "")
        if not first.startswith(VALID):
            errs.append(f"#{i}: 다이어그램 타입 선언 누락(첫 줄='{first[:40]}')")
        if "```" in b:
            errs.append(f"#{i}: 블록 내부에 펜스(```) 잔존")
        sg = len(re.findall(r"\bsubgraph\b", b))
        en = len(re.findall(r"^\s*end\s*$", b, re.M))
        if sg != en:
            errs.append(f"#{i}: subgraph({sg}) != end({en})")
        for op, cl in (("[", "]"), ("{", "}"), ("(", ")")):
            if b.count(op) != b.count(cl):
                errs.append(f"#{i}: '{op}{cl}' 불균형 {b.count(op)}/{b.count(cl)}")
        if b.count('"') % 2:
            errs.append(f'#{i}: 따옴표(") 홀수')
    if errs:
        print(f"FAIL {path} ({len(blocks)} blocks):")
        for e in errs:
            print("  -", e)
        return 1
    print(f"OK {path}: {len(blocks)} mermaid blocks 통과")
    return 0


if __name__ == "__main__":
    p = sys.argv[1] if len(sys.argv) > 1 else "docs/architecture/05_mermaid_architecture.md"
    sys.exit(check(p))
