from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import List, Dict

import yaml


def load_inbox(path: Path) -> List[Dict]:
    items: List[Dict] = []
    if not path.exists():
        return items
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                items.append(json.loads(line))
            except Exception:
                continue
    return items


def append_to_nlu_yaml(nlu_path: Path, samples: Dict[str, List[str]]) -> None:
    data: dict = {}
    if nlu_path.exists():
        with nlu_path.open("r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
    data.setdefault("version", "3.1")
    data.setdefault("nlu", [])

    # Build quick index
    by_intent: Dict[str, Dict] = {}
    for block in data["nlu"]:
        if isinstance(block, dict) and block.get("intent"):
            by_intent[block["intent"]] = block

    for intent, utterances in samples.items():
        if not intent or not utterances:
            continue
        block = by_intent.get(intent)
        if not block:
            block = {"intent": intent, "examples": "|\n"}
            data["nlu"].append(block)
            by_intent[intent] = block
        # Merge, avoid duplicates
        existing = set(
            [
                e.strip(" -")
                for e in (block.get("examples") or "").splitlines()
                if e.strip().startswith("-")
            ]
        )
        for u in utterances:
            u = u.strip()
            if not u:
                continue
            if u not in existing:
                block["examples"] += f"  - {u}\n"

    with nlu_path.open("w", encoding="utf-8") as f:
        yaml.safe_dump(data, f, sort_keys=False, allow_unicode=True)


def main() -> None:
    parser = argparse.ArgumentParser(description="Collect LLM fallback suggestions into NLU YAML groups")
    parser.add_argument("--inbox", type=Path, default=Path("rasa/data/fallback_inbox.jsonl"))
    parser.add_argument("--nlu", type=Path, default=Path("rasa/data/nlu.yml"))
    args = parser.parse_args()

    items = load_inbox(args.inbox)
    grouped: Dict[str, List[str]] = {}
    for it in items:
        intent = (it.get("suggested_intent") or "out_of_scope").strip()
        exs = it.get("suggested_examples") or []
        # Always include original text as a training example
        examples = [it.get("text", "").strip()] + [e for e in exs if e]
        grouped.setdefault(intent, [])
        for ex in examples:
            if ex and ex not in grouped[intent]:
                grouped[intent].append(ex)

    append_to_nlu_yaml(args.nlu, grouped)
    print(f"Merged {sum(len(v) for v in grouped.values())} examples into {args.nlu}")


if __name__ == "__main__":
    main()


