"""Extract agent declarations without executing project modules."""

import ast
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REGISTRY = ROOT / "agents" / "registry.py"
OUTPUT = ROOT / "database" / "project_knowledge" / "agent_inventory.json"

if OUTPUT.exists():
    raise RuntimeError("Inventory already exists; do not overwrite.")

registry_tree = ast.parse(REGISTRY.read_text(encoding="utf-8-sig"))

imports = {}
for node in registry_tree.body:
    if isinstance(node, ast.ImportFrom):
        if not node.module or not node.module.startswith("agents."):
            continue
        for alias in node.names:
            imports[alias.asname or alias.name] = node.module

agent_classes = None

for node in registry_tree.body:
    if isinstance(node, ast.AnnAssign):
        is_registry = isinstance(node.target, ast.Name) and node.target.id == "AGENT_CLASSES"
    elif isinstance(node, ast.Assign):
        is_registry = any(
            isinstance(target, ast.Name) and target.id == "AGENT_CLASSES" for target in node.targets
        )
    else:
        continue

    if not is_registry:
        continue

    if not isinstance(node.value, (ast.Tuple, ast.List)):
        raise RuntimeError("Unexpected registry declaration")

    agent_classes = [item.id for item in node.value.elts if isinstance(item, ast.Name)]

if agent_classes is None or len(agent_classes) != 13:
    raise RuntimeError("Expected exactly 13 registry classes")


def declared_value(node: ast.AST) -> object:
    if (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "frozenset"
    ):
        if not node.args:
            return []
        return sorted(ast.literal_eval(node.args[0]))

    if isinstance(node, ast.Attribute):
        return node.attr.lower()

    return ast.literal_eval(node)


agents = []

for class_name in agent_classes:
    module_name = imports.get(class_name)

    if not module_name:
        raise RuntimeError(f"Missing import for {class_name}")

    source_path = Path(*module_name.split(".")).with_suffix(".py")
    file_path = ROOT / source_path

    if not file_path.is_file():
        raise RuntimeError(f"Missing implementation: {source_path}")

    contents = file_path.read_bytes()
    tree = ast.parse(
        contents.decode("utf-8-sig"),
        filename=str(source_path),
    )

    classes = [
        node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == class_name
    ]

    if len(classes) != 1:
        raise RuntimeError(f"Agent class not uniquely found: {class_name}")

    spec_calls = []

    for node in classes[0].body:
        if not isinstance(node, (ast.Assign, ast.AnnAssign)):
            continue

        value = node.value

        if (
            isinstance(value, ast.Call)
            and isinstance(value.func, ast.Name)
            and value.func.id == "AgentSpec"
        ):
            spec_calls.append(value)

    if len(spec_calls) != 1:
        raise RuntimeError(f"AgentSpec not found: {class_name}")

    spec = {
        keyword.arg: declared_value(keyword.value)
        for keyword in spec_calls[0].keywords
        if keyword.arg is not None
    }

    required = {
        "agent_id",
        "name",
        "description",
        "responsibilities",
        "implementation_status",
        "allowed_tools",
    }

    missing = required - spec.keys()
    if missing:
        raise RuntimeError(f"Missing fields for {class_name}: {sorted(missing)}")

    if not isinstance(spec["agent_id"], str):
        raise RuntimeError(f"Invalid agent ID: {class_name}")

    if not isinstance(spec["allowed_tools"], (list, tuple, set)):
        raise RuntimeError(f"Invalid allowed tools: {class_name}")

    agents.append(
        {
            "agent_id": spec["agent_id"],
            "class_name": class_name,
            "name": spec["name"],
            "description": spec["description"],
            "responsibilities": spec["responsibilities"],
            "implementation_status": spec["implementation_status"],
            "allowed_tools": sorted(spec["allowed_tools"]),
            "source_path": source_path.as_posix(),
            "source_sha256": hashlib.sha256(contents).hexdigest(),
            "verification": "static_source_declaration",
        }
    )

ids = [agent["agent_id"] for agent in agents]

if len(ids) != len(set(ids)):
    raise RuntimeError("Duplicate agent identifiers detected")

OUTPUT.write_text(
    json.dumps(
        {
            "project_key": "dubai-real-estate-ai",
            "generated_at": datetime.now(UTC).isoformat(),
            "agent_count": len(agents),
            "agents": agents,
        },
        indent=2,
    ),
    encoding="utf-8",
)

print("PASS: Agent inventory extracted")
print("Agent count:", len(agents))

for agent in agents:
    allowed_tools = agent["allowed_tools"]
    if not isinstance(allowed_tools, list) or not all(
        isinstance(item, str) for item in allowed_tools
    ):
        raise ValueError("Tool allowlist must contain names")
    print(
        agent["agent_id"],
        "|",
        agent["implementation_status"],
        "| tools:",
        ", ".join(allowed_tools) or "none",
    )

print("Saved:", OUTPUT)
