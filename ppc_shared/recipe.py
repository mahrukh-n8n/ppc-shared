"""
Recipe creation and validation.
Shared between ppc-shared and ppc-logs-app.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml

RECIPE_SCHEMA = {
    "required_fields": ["id", "title", "ad_type", "objective", "status"],
    "field_types": {
        "id": "string",
        "title": "string",
        "tags": "array",
        "ad_type": "string",
        "objective": "string",
        "match_type": "string",
        "targeting_type": "string",
        "ad_format": "string",
        "purpose": "string",
        "targeting": "object",
        "settings": "object",
        "placement_focus": "array",
        "works_when": "array",
        "does_not_work_when": "array",
        "tested_on": "array",
        "status": "string",
        "notes": "string",
        "strategy": "object",
    },
    "ad_types": ["SP", "SB", "SD"],
    "valid_statuses": ["blueprint", "proven", "testing", "failed"],
    "tag_legend": {
        "ChrisR": "Chris Rawlings framework blueprint (reference/theoretical)",
        "Mahrukh": "Field-tested recipe with real account results",
    },
    "status_legend": {
        "blueprint": "Framework reference — not yet field-tested",
        "proven": "Tested and confirmed working",
        "testing": "Currently being tested",
        "failed": "Tested and does not work",
    },
    "_py_types": {
        "id": str,
        "title": str,
        "tags": list,
        "ad_type": str,
        "objective": str,
        "match_type": str,
        "targeting_type": str,
        "ad_format": str,
        "purpose": str,
        "targeting": dict,
        "settings": dict,
        "placement_focus": list,
        "works_when": list,
        "does_not_work_when": list,
        "tested_on": list,
        "status": str,
        "notes": str,
        "strategy": dict,
    },
}

RECIPE_TEMPLATE = """\
# Campaign Recipe Template
# Copy this file, rename it, fill in fields. Remove comments before committing.
# Fields marked [REQUIRED] must be filled.

id: ""                              # [REQUIRED] Unique snake_case ID
title: ""                           # [REQUIRED] Human-readable name
tags: []                            # [REQUIRED] ChrisR | Mahrukh
ad_type: ""                         # [REQUIRED] SP | SB | SD
objective: ""                       # [REQUIRED] rank | profit | shield | research
match_type: ""                      # [OPTIONAL] exact | broad | phrase
targeting_type: ""                  # [OPTIONAL] keyword | product | auto | category | audience
ad_format: ""                       # [OPTIONAL] video | image_or_default | product_collection | store_spotlight
purpose: ""                         # [REQUIRED] One-line description
targeting:                          # [REQUIRED]
  type: ""                          # keyword | asin | auto | category | audiences
  strategy: ""                      # how to select targets
settings:                           # [REQUIRED]
  bid_type: ""                      # fixed | down_only | up_and_down | automatic
  base_bid: null                    # numeric or null
  tos_adjustment: null              # % integer or null
  ros_adjustment: null              # % integer or null
  pp_adjustment: null               # % integer or null
  b2b_adjustment: null              # % integer or null
  budget: null                      # numeric or null
  bid_strategy: ""                  # down_only | up_and_down | fixed_bids | automatic
placement_focus: []                 # [OPTIONAL] TOS | ROS | PP | B2B
works_when: []                      # [REQUIRED]
does_not_work_when: []              # [REQUIRED]
tested_on: []                       # [OPTIONAL - for Mahrukh field recipes]
#   - {product: "name", marketplace: "UK/USA", acos: "xx%", note: "...", status: proven}
status: ""                          # [REQUIRED] proven | blueprint | testing | failed
notes: ""                           # [OPTIONAL] Free-text notes
# strategy:                         # [OPTIONAL] Optimization strategy
#   phase_1:
#     target: "TOS IS% >= 30%"
#     signal: "dashboard TOS IS% report"
#     check_frequency: weekly
#     if_not_met: "increase TOS adjuster by 50%"
#     if_met: "proceed to phase 2"
"""


def recipe_to_yaml(data: dict[str, Any]) -> str:
    """Serialize a recipe dict to normalized YAML."""
    return yaml.dump(data, default_flow_style=False, sort_keys=False, width=1000)


def normalize_recipe_yaml(yaml_content: str) -> str:
    """Parse recipe dict and re-serialize it as clean YAML."""
    data = yaml.safe_load(yaml_content)
    if not isinstance(data, dict):
        raise ValueError("Recipe YAML must be a YAML mapping")
    return recipe_to_yaml(data)


def yaml_validate_fields(data: dict[str, Any]) -> list[str]:
    """Validate recipe fields against schema. Returns list of error strings."""
    errors: list[str] = []

    for field in RECIPE_SCHEMA["required_fields"]:
        val = data.get(field)
        if not val and val != 0:
            errors.append(f"Missing required field: {field}")

    field_types = RECIPE_SCHEMA.get("_py_types", {})
    for field, expected_type in field_types.items():
        if field in data and data[field] is not None and not isinstance(data[field], expected_type):
            errors.append(
                f"Field '{field}' must be of type {expected_type.__name__}, got {type(data[field]).__name__}"
            )

    ad_type = data.get("ad_type", "")
    if ad_type and str(ad_type).upper() not in RECIPE_SCHEMA["ad_types"]:
        errors.append(
            f"Invalid ad_type: '{ad_type}'. Must be one of {RECIPE_SCHEMA['ad_types']}"
        )

    status = data.get("status", "")
    if status and status not in RECIPE_SCHEMA["valid_statuses"]:
        errors.append(
            f"Invalid status: '{status}'. Must be one of {RECIPE_SCHEMA['valid_statuses']}"
        )

    return errors


def parse_recipe_yaml(yaml_content: str) -> dict[str, Any]:
    """Parse and validate a recipe YAML string. Returns the parsed dict."""
    try:
        data = yaml.safe_load(yaml_content)
    except yaml.YAMLError as error:
        raise ValueError(f"Invalid YAML syntax: {error}") from error

    if not isinstance(data, dict):
        raise ValueError("Recipe YAML must be a YAML mapping")

    errors = yaml_validate_fields(data)
    if errors:
        raise ValueError("\n".join(f"  - {error}" for error in errors))

    return data


def create_recipe_file(
    recipe_id: str,
    title: str,
    ad_type: str,
    objective: str,
    status: str,
    purpose: str = "",
    match_type: str = "",
    targeting_type: str = "",
    output_dir: Path | str | None = None,
    tag: str = "",
) -> Path:
    """Create a recipe YAML file from provided fields."""
    tags = [tag] if tag else []
    directory = "field" if tag == "Mahrukh" else "framework" if tag == "ChrisR" else "custom"

    output_path = Path(output_dir) if output_dir else Path(".")
    target_dir = output_path / directory
    target_dir.mkdir(parents=True, exist_ok=True)

    file_path = target_dir / f"{recipe_id.replace(' ', '-')}.yaml"
    recipe_data: dict[str, Any] = {
        "id": recipe_id,
        "title": title,
        "tags": tags,
        "ad_type": ad_type,
        "objective": objective,
        "status": status,
        "targeting": {"type": "", "strategy": ""},
        "settings": {
            "bid_type": "",
            "base_bid": None,
            "tos_adjustment": None,
            "ros_adjustment": None,
            "pp_adjustment": None,
            "b2b_adjustment": None,
            "budget": None,
            "bid_strategy": "",
        },
        "placement_focus": [],
        "works_when": [],
        "does_not_work_when": [],
        "tested_on": [],
    }

    if match_type:
        recipe_data["match_type"] = match_type
    if targeting_type:
        recipe_data["targeting_type"] = targeting_type
    if purpose:
        recipe_data["purpose"] = purpose
        recipe_data["notes"] = ""

    file_path.write_text(f"{recipe_to_yaml(recipe_data).rstrip()}\n", encoding="utf-8")
    return file_path


def check_recipe_duplicate(recipe_id: str, index_path: Path | str) -> dict[str, Any] | None:
    """Check if recipe_id already exists in the index."""
    index_file = Path(index_path)
    if not index_file.exists():
        return None

    index = json.loads(index_file.read_text(encoding="utf-8"))
    for recipe in index.get("recipes", []):
        if recipe.get("id") == recipe_id:
            return recipe
    return None


def register_recipe_in_index(
    recipe_id: str,
    title: str,
    ad_type: str,
    objective: str,
    status: str,
    file_path: str,
    index_path: Path | str,
    match_type: str = "",
    targeting_type: str = "",
    tags: list[str] | None = None,
) -> dict[str, Any]:
    """Add a recipe entry to the _index.json file."""
    index_file = Path(index_path)

    if index_file.exists():
        index = json.loads(index_file.read_text(encoding="utf-8"))
    else:
        index = json.loads(generate_index_json())

    entry: dict[str, Any] = {
        "id": recipe_id,
        "title": title,
        "tags": tags or [],
        "ad_type": ad_type,
        "objective": objective,
        "status": status,
        "file": file_path,
    }
    if match_type:
        entry["match_type"] = match_type
    if targeting_type:
        entry["targeting_type"] = targeting_type

    index["recipes"].append(entry)
    index_file.write_text(f"{json.dumps(index, indent=2)}\n", encoding="utf-8")
    return index


def update_recipe_tested_on(
    recipe_id: str,
    test_entry: dict[str, Any],
    yaml_path: Path | str,
    index_path: Path | str,
) -> dict[str, Any]:
    """Add a tested_on entry to an existing recipe instead of creating a new file."""
    _ = recipe_id
    _ = index_path

    yaml_file = Path(yaml_path)
    if not yaml_file.exists():
        raise FileNotFoundError(f"Recipe file not found: {yaml_path}")

    recipe_data = yaml.safe_load(yaml_file.read_text(encoding="utf-8"))
    if not isinstance(recipe_data, dict):
        raise ValueError("Recipe YAML must be a YAML mapping")

    tested_on = recipe_data.get("tested_on") or []
    tested_on.append(test_entry)
    recipe_data["tested_on"] = tested_on

    yaml_file.write_text(f"{recipe_to_yaml(recipe_data).rstrip()}\n", encoding="utf-8")
    return recipe_data


def generate_index_json() -> str:
    """Generate the _index.json skeleton from Python schema."""
    return json.dumps(
        {
            "version": "1.0",
            "description": "Campaign Recipe Book - index of all PPC campaign recipes.",
            "tags_legend": RECIPE_SCHEMA["tag_legend"],
            "status_legend": RECIPE_SCHEMA["status_legend"],
            "recipes": [],
        },
        indent=2,
    ) + "\n"


def generate_ts_validator() -> str:
    """Generate the legacy TypeScript validator module from the Python schema."""
    required = RECIPE_SCHEMA["required_fields"]
    zod_types = {
        "string": "z.string()",
        "number": "z.number()",
        "array": "z.array(z.unknown())",
        "object": "z.record(z.string(), z.unknown())",
    }

    field_schema_parts: list[str] = []
    for field, ts_type in RECIPE_SCHEMA["field_types"].items():
        zod = zod_types.get(ts_type, "z.unknown()")
        if field in required and ts_type == "string":
            field_schema_parts.append(f'  {field}: z.string().min(1, "{field} is required"),')
        elif field in required:
            field_schema_parts.append(f"  {field}: {zod},")
        else:
            field_schema_parts.append(f"  {field}: {zod}.optional(),")

    return f'''// AUTO-GENERATED — DO NOT EDIT MANUALLY
// Source of truth: ppc-shared/ppc_shared/recipe.py

import yaml from "js-yaml";
import {{ z }} from "zod";

export const sharedRecipeYamlSchema = z.object({{
{chr(10).join(field_schema_parts)}
}});

export type SharedParsedRecipe = z.infer<typeof sharedRecipeYamlSchema>;

export interface RecipeYamlValidationResult {{
  valid: boolean;
  normalizedYaml: string;
  fixes: Array<{{ code: string; message: string; line: number }}>;
  errors: string[];
  recipe?: SharedParsedRecipe;
}}

export function validateRecipeYamlContent(yamlContent: string): RecipeYamlValidationResult {{
  try {{
    const parsed = yaml.load(yamlContent, {{ schema: yaml.DEFAULT_SCHEMA }}) ?? {{}};
    const normalizedYaml = yaml.dump(parsed as Record<string, unknown>, {{ lineWidth: -1, noRefs: true, quotingType: '"' }});
    const result = sharedRecipeYamlSchema.safeParse(parsed);
    if (!result.success) {{
      return {{
        valid: false,
        normalizedYaml,
        fixes: [],
        errors: result.error.issues.map((issue) => issue.message),
      }};
    }}
    return {{ valid: true, normalizedYaml, fixes: [], errors: [], recipe: result.data }};
  }} catch (error) {{
    return {{
      valid: false,
      normalizedYaml: yamlContent,
      fixes: [],
      errors: [error instanceof Error ? error.message : "Invalid YAML"],
    }};
  }}
}}
'''


if __name__ == "__main__":
    import sys

    args = sys.argv[1:]
    if "--gen-ts" in args:
        print(generate_ts_validator())
    elif "--gen-index" in args:
        print(generate_index_json())
    elif "--gen-template" in args:
        print(RECIPE_TEMPLATE)
    else:
        print("Usage: python -m ppc_shared.recipe [--gen-ts | --gen-index | --gen-template]")
        sys.exit(1)
