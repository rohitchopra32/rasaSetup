from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Dict, List, Tuple

import yaml

CATEGORY_PREFIX_MAP: Dict[str, str] = {
    "Settlement Discussions": "wants_settlement",
    "PTP": "ptp",
    "Refusing / Not Willing to Pay": "refuse_to_pay",
    "Objections / Complaints": "objections",
    "Confused / Random / No Clarity": "confused",
    "Information Requested": "info_requested",
    "Paid / Payment Query": "paid",
    "Vehicle related": "vehicle",
}


def normalize_slug(text: str) -> str:
    slug = text.strip().lower()
    slug = re.sub(r"[\s/–—-]+", "_", slug)
    slug = re.sub(r"[^a-z0-9_]+", "", slug)
    slug = re.sub(r"_+", "_", slug)
    return slug.strip("_")


def derive_intent(category: str, scenario: str) -> str:
    prefix = CATEGORY_PREFIX_MAP.get(category.strip(), normalize_slug(category))
    scenario_slug = normalize_slug(scenario)
    if prefix:
        return f"{prefix}__{scenario_slug}" if scenario_slug else prefix
    return scenario_slug or "misc"


def load_domain(path: Path) -> dict:
    if path.exists():
        with path.open("r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
    else:
        data = {}
    data.setdefault("version", "3.1")
    data.setdefault("intents", [])
    data.setdefault("responses", {})
    return data


def save_domain(path: Path, domain: dict) -> None:
    with path.open("w", encoding="utf-8") as f:
        yaml.safe_dump(domain, f, sort_keys=False, allow_unicode=True)


def read_json_items(path: Path) -> List[Dict[str, str]]:
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, list):
        raise ValueError("responses.json must be a JSON array of objects")
    return data  # expect keys: category, scenario, message


def upsert(domain: dict, intent: str, message: str) -> None:
    if intent not in domain["intents"]:
        domain["intents"].append(intent)
    if message:
        action_name = f"utter_{intent}"
        existing: List[Dict[str, str]] = domain["responses"].get(action_name, [])
        if not any(x.get("text") == message for x in existing):
            existing.append({"text": message})
        domain["responses"][action_name] = existing


def main() -> None:
    parser = argparse.ArgumentParser(description="Import intent->response from responses.json into rasa/domain.yml")
    parser.add_argument("--json", dest="json_path", type=Path, default=Path("responses.json"))
    parser.add_argument("--domain", dest="domain_path", type=Path, default=Path("rasa/domain.yml"))
    args = parser.parse_args()

    items = read_json_items(args.json_path)
    domain = load_domain(args.domain_path)

    added: List[Tuple[str, str]] = []
    for item in items:
        category = str(item.get("category", "")).strip()
        scenario = str(item.get("scenario", "")).strip()
        message = str(item.get("message", "")).strip()
        if not scenario:
            # skip malformed rows
            continue
        intent = derive_intent(category, scenario)
        upsert(domain, intent, message)
        added.append((intent, message))

    save_domain(args.domain_path, domain)

    print(f"Updated {args.domain_path} with {len(added)} intents/responses.")


if __name__ == "__main__":
    main()
