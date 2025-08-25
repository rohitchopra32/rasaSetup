import argparse
import csv
import json
import os
import re
from typing import Any, Dict, List, Optional, Tuple

try:
    import yaml  # type: ignore
except Exception:  # pragma: no cover
    yaml = None

try:
    import pandas as pd  # type: ignore
except Exception:  # pragma: no cover
    pd = None  # Fallback if pandas is not installed; CSV will still be produced


ENTITY_MD_REGEX = re.compile(
    r"\[(?P<text>.+?)\]"  # entity surface text
    r"\("
    r"(?P<entity>[\w\.:-]+?)"  # entity type (optionally with role using entity:role)
    r"(?:=(?P<value>[^)]+?))?"  # optional value assignment like entity=value
    r"\)"
)

ENTITY_JSON_REGEX = re.compile(
    r"\[(?P<text>.+?)\]"  # entity surface text
    r"\{\s*\"entity\"\s*:\s*\"(?P<entity>[^\"]+)\"(?:\s*,\s*\"role\"\s*:\s*\"(?P<role>[^\"]+)\")?(?:\s*,\s*\"value\"\s*:\s*\"(?P<value>[^\"]+)\")?[^}]*\}"
)


def extract_entities_from_text(example: str) -> Tuple[str, List[Dict[str, Optional[str]]]]:
    """
    Extract entities from a single Rasa training example (Markdown/JSON inline).

    Returns a tuple of (clean_text, entities_list).
    clean_text has entity annotations stripped, keeping only surface text.
    entities_list contains dicts with keys: text, entity, role, value.
    """
    entities: List[Dict[str, Optional[str]]] = []

    # First handle JSON-style: [text]{"entity": "type", "role": "role", ...}
    def replace_json(match: re.Match) -> str:
        text = match.group("text")
        entity = match.group("entity")
        role = match.group("role")
        value = match.group("value")
        entities.append({"text": text, "entity": entity, "role": role, "value": value})
        return text

    interim = ENTITY_JSON_REGEX.sub(replace_json, example)

    # Then handle Markdown-style: [text](entity) or [text](entity=value) or [text](entity:role)
    def replace_md(match: re.Match) -> str:
        text = match.group("text")
        entity_and_role = match.group("entity")
        value = match.group("value")
        entity = entity_and_role
        role = None
        # Support entity:role notation
        if ":" in entity_and_role:
            entity, role = entity_and_role.split(":", 1)
        entities.append({"text": text, "entity": entity, "role": role, "value": value})
        return text

    clean_text = ENTITY_MD_REGEX.sub(replace_md, interim)
    return clean_text, entities


def split_bullet_examples(block: str) -> List[str]:
    """Split a Rasa YAML examples block (|-style) into individual example lines."""
    examples: List[str] = []
    for raw_line in block.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith("- "):
            examples.append(line[2:].strip())
        else:
            # In case examples are not prefixed (rare), still include
            examples.append(line)
    return examples


def _parse_with_yaml(path: str) -> Dict[str, Any]:
    assert yaml is not None
    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)

    nlu_items: List[Dict[str, Any]] = data.get("nlu", []) or []

    intents: List[Dict[str, Any]] = []
    synonyms: List[Dict[str, Any]] = []
    regexes: List[Dict[str, Any]] = []
    lookups: List[Dict[str, Any]] = []

    for item in nlu_items:
        if not isinstance(item, dict):
            continue
        if "intent" in item:
            intent_name = item.get("intent")
            examples_block = item.get("examples", "")
            examples = split_bullet_examples(examples_block) if isinstance(examples_block, str) else []
            for ex in examples:
                clean, ents = extract_entities_from_text(ex)
                intents.append(
                    {
                        "intent": intent_name,
                        "example": clean,
                        "entities": ents,
                    }
                )
        elif "synonym" in item:
            value = item.get("synonym")
            examples_block = item.get("examples", "")
            items = split_bullet_examples(examples_block) if isinstance(examples_block, str) else []
            for variant in items:
                synonyms.append({"value": value, "synonym": variant})
        elif "regex" in item:
            name = item.get("regex")
            pattern = item.get("pattern")
            if isinstance(pattern, str):
                regexes.append({"name": name, "pattern": pattern})
        elif "lookup" in item:
            name = item.get("lookup")
            if isinstance(item.get("examples"), str):
                items = split_bullet_examples(item["examples"])  # type: ignore[index]
                for val in items:
                    lookups.append({"name": name, "item": val})
            elif isinstance(item.get("files"), list):
                for file_path in item["files"]:
                    lookups.append({"name": name, "item_file": file_path})

    return {
        "intents": intents,
        "synonyms": synonyms,
        "regexes": regexes,
        "lookups": lookups,
    }


def _parse_with_line_scanner(path: str) -> Dict[str, Any]:
    intents: List[Dict[str, Any]] = []
    synonyms: List[Dict[str, Any]] = []
    regexes: List[Dict[str, Any]] = []
    lookups: List[Dict[str, Any]] = []

    current_intent: Optional[str] = None
    in_examples_block: bool = False
    examples_indent: int = 0

    with open(path, "r", encoding="utf-8") as f:
        lines = f.readlines()

    for line in lines:
        raw = line.rstrip("\n")
        # Exit examples block on a new top-level dash-started item
        if in_examples_block and (raw.startswith("- ") or (raw and not raw[0].isspace())):
            in_examples_block = False

        if not in_examples_block:
            # detect new intent
            m_intent = re.match(r"^\s*-\s+intent:\s*(\S+)\s*$", raw)
            if m_intent:
                current_intent = m_intent.group(1)
                continue

            # detect examples block start
            if current_intent is not None:
                m_examples = re.match(r"^(?P<indent>\s*)examples:\s*\|\s*$", raw)
                if m_examples:
                    in_examples_block = True
                    examples_indent = len(m_examples.group("indent"))
                    continue
        else:
            # inside examples: | block
            stripped = raw.strip()
            if stripped.startswith("- ") and current_intent:
                example_text = stripped[2:].strip()
                clean, ents = extract_entities_from_text(example_text)
                intents.append({
                    "intent": current_intent,
                    "example": clean,
                    "entities": ents,
                })
            # continue until block ends

    return {
        "intents": intents,
        "synonyms": synonyms,
        "regexes": regexes,
        "lookups": lookups,
    }


def parse_nlu_yaml(path: str) -> Dict[str, Any]:
    if yaml is not None:
        try:
            return _parse_with_yaml(path)
        except Exception:
            # Fallback to line scanner if YAML parsing fails
            pass
    return _parse_with_line_scanner(path)


def ensure_dir(path: str) -> None:
    os.makedirs(path, exist_ok=True)


def export_to_csv(parsed: Dict[str, Any], out_dir: str) -> Dict[str, str]:
    ensure_dir(out_dir)
    outputs: Dict[str, str] = {}

    # Intents & examples
    intents_csv = os.path.join(out_dir, "nlu_intents_examples.csv")
    with open(intents_csv, "w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["intent", "example"])  # simple, user-friendly
        for row in parsed["intents"]:
            writer.writerow([
                row.get("intent"),
                row.get("example")
            ])
    outputs["intents_csv"] = intents_csv

    # Synonyms
    if parsed["synonyms"]:
        synonyms_csv = os.path.join(out_dir, "nlu_synonyms.csv")
        with open(synonyms_csv, "w", encoding="utf-8", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["value", "synonym"])  # canonical value and its synonym
            for row in parsed["synonyms"]:
                writer.writerow([row.get("value"), row.get("synonym")])
        outputs["synonyms_csv"] = synonyms_csv

    # Regexes
    if parsed["regexes"]:
        regexes_csv = os.path.join(out_dir, "nlu_regexes.csv")
        with open(regexes_csv, "w", encoding="utf-8", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["name", "pattern"])
            for row in parsed["regexes"]:
                writer.writerow([row.get("name"), row.get("pattern")])
        outputs["regexes_csv"] = regexes_csv

    # Lookups
    if parsed["lookups"]:
        lookups_csv = os.path.join(out_dir, "nlu_lookups.csv")
        with open(lookups_csv, "w", encoding="utf-8", newline="") as f:
            writer = csv.writer(f)
            # Either item (inline) or item_file (referenced file)
            writer.writerow(["name", "item", "item_file"])
            for row in parsed["lookups"]:
                writer.writerow([row.get("name"), row.get("item"), row.get("item_file")])
        outputs["lookups_csv"] = lookups_csv

    return outputs


def export_to_excel(parsed: Dict[str, Any], out_dir: str) -> Optional[str]:
    ensure_dir(out_dir)
    if pd is None:
        return None

    xlsx_path = os.path.join(out_dir, "nlu_export.xlsx")

    # Build dataframes
    intents_df = pd.DataFrame(parsed["intents"]) if parsed["intents"] else pd.DataFrame(columns=["intent", "example", "entities"])
    if not intents_df.empty:
        # pretty-print entities as JSON strings
        intents_df = intents_df.assign(entities=intents_df["entities"].apply(lambda v: json.dumps(v, ensure_ascii=False)))

    synonyms_df = pd.DataFrame(parsed["synonyms"]) if parsed["synonyms"] else pd.DataFrame(columns=["value", "synonym"])  # type: ignore[arg-type]
    regexes_df = pd.DataFrame(parsed["regexes"]) if parsed["regexes"] else pd.DataFrame(columns=["name", "pattern"])  # type: ignore[arg-type]
    lookups_df = pd.DataFrame(parsed["lookups"]) if parsed["lookups"] else pd.DataFrame(columns=["name", "item", "item_file"])  # type: ignore[arg-type]

    # Write to Excel with multiple sheets
    with pd.ExcelWriter(xlsx_path, engine="openpyxl") as writer:  # type: ignore[arg-type]
        intents_df.to_excel(writer, index=False, sheet_name="Intents")
        if not synonyms_df.empty:
            synonyms_df.to_excel(writer, index=False, sheet_name="Synonyms")
        if not regexes_df.empty:
            regexes_df.to_excel(writer, index=False, sheet_name="Regexes")
        if not lookups_df.empty:
            lookups_df.to_excel(writer, index=False, sheet_name="Lookups")

    return xlsx_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Export Rasa NLU YAML to CSV/Excel for non-technical users")
    parser.add_argument("--input", "-i", default=os.path.join("rasa", "data", "nlu.yml"), help="Path to nlu.yml")
    parser.add_argument("--out", "-o", default=os.path.join("exports"), help="Output directory for CSV/XLSX")
    args = parser.parse_args()

    parsed = parse_nlu_yaml(args.input)
    csv_outputs = export_to_csv(parsed, args.out)
    xlsx_output = export_to_excel(parsed, args.out)

    print("CSV files written:")
    for key, path in csv_outputs.items():
        print(f" - {key}: {path}")
    if xlsx_output:
        print(f"Excel file written: {xlsx_output}")
    else:
        print("Excel export skipped (pandas/openpyxl not installed)")


if __name__ == "__main__":
    main()


