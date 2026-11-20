"""Extract source-declared workflow definitions without executing them."""

import ast
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUTPUT = ROOT / "database/project_knowledge/workflow_inventory.json"
REGISTRY = ROOT / "workflows/registry.py"

EXPECTED = {
    "LEAD_PROCESSING": "lead_flow.py",
    "PROPERTY_RECOMMENDATION": "property_flow.py",
    "SALES_CONVERSATION": "sales_flow.py",
    "FOLLOWUP_AUTOMATION": "followup_flow.py",
    "CRM_SYNC": "crm_sync_flow.py",
    "KNOWLEDGE_SUPPORT": "customer_support_flow.py",
    "LEAD_REQUALIFICATION": "qualification_flow.py",
}

if OUTPUT.exists():
    raise RuntimeError("Workflow inventory already exists. Stop.")

registry_source = REGISTRY.read_text(encoding="utf-8-sig")
registry_tree = ast.parse(registry_source)

registered_imports = {}

for node in registry_tree.body:
    if isinstance(node, ast.ImportFrom):
        for alias in node.names:
            registered_imports[alias.asname or alias.name] = node.module

if not all(
    registered_imports.get(name) == "workflows." + filename[:-3]
    for name, filename in EXPECTED.items()
):
    raise RuntimeError("Workflow registry imports do not match expected files")

workflows = []

for constant, filename in EXPECTED.items():
    path = ROOT / "workflows" / filename
    content = path.read_bytes()
    tree = ast.parse(content.decode("utf-8-sig"), filename=str(path))

    definitions = []

    for node in tree.body:
        if not isinstance(node, (ast.Assign, ast.AnnAssign)):
            continue

        targets = node.targets if isinstance(node, ast.Assign) else [node.target]

        if not any(isinstance(target, ast.Name) and target.id == constant for target in targets):
            continue

        value = node.value

        if (
            isinstance(value, ast.Call)
            and isinstance(value.func, ast.Name)
            and value.func.id == "WorkflowDefinition"
        ):
            definitions.append(value)

    if len(definitions) != 1:
        raise RuntimeError(f"Expected one definition for {constant}")

    keywords = {kw.arg: kw.value for kw in definitions[0].keywords if kw.arg is not None}

    workflow_id = ast.literal_eval(keywords["workflow_id"])
    name = ast.literal_eval(keywords["name"])
    description = ast.literal_eval(keywords["description"])

    status_node = keywords["implementation_status"]

    if not (
        isinstance(status_node, ast.Attribute)
        and isinstance(status_node.value, ast.Name)
        and status_node.value.id == "ImplementationStatus"
    ):
        raise RuntimeError(f"Unexpected status for {workflow_id}")

    status = status_node.attr.lower()

    if status not in {"functional", "partial", "interface_only"}:
        raise RuntimeError(f"Unknown status for {workflow_id}")

    steps_node = keywords["steps"]

    if not isinstance(steps_node, (ast.Tuple, ast.List)):
        raise RuntimeError(f"Unexpected steps for {workflow_id}")

    steps = []

    for step in steps_node.elts:
        if not (
            isinstance(step, ast.Call)
            and isinstance(step.func, ast.Name)
            and step.func.id == "Step"
            and len(step.args) >= 2
        ):
            raise RuntimeError(f"Unexpected step in {workflow_id}")

        step_name = ast.literal_eval(step.args[0])

        if not isinstance(step_name, str):
            raise RuntimeError(f"Invalid step name in {workflow_id}")

        handler = ast.unparse(step.args[1])

        steps.append(
            {
                "name": step_name,
                "handler_expression": handler,
            }
        )

    if not steps:
        raise RuntimeError(f"No steps found for {workflow_id}")

    workflows.append(
        {
            "workflow_id": workflow_id,
            "name": name,
            "description": description,
            "implementation_status": status,
            "workflow_type": ("sub_flow" if constant == "LEAD_REQUALIFICATION" else "primary"),
            "steps": steps,
            "source_path": "workflows/" + filename,
            "source_sha256": hashlib.sha256(content).hexdigest(),
            "verification_method": "static_source_declaration",
        }
    )

ids = [w["workflow_id"] for w in workflows]

if len(workflows) != 7 or len(set(ids)) != 7:
    raise RuntimeError("Expected seven unique workflows")

OUTPUT.write_text(
    json.dumps(
        {
            "project_key": "dubai-real-estate-ai",
            "generated_at": datetime.now(UTC).isoformat(),
            "workflow_count": len(workflows),
            "workflows": workflows,
        },
        indent=2,
    ),
    encoding="utf-8",
)

print("PASS: Workflow inventory extracted")
print("Total workflows:", len(workflows))

for workflow in workflows:
    print(
        workflow["workflow_id"],
        "|",
        workflow["implementation_status"],
        "| steps:",
        len(workflow["steps"]),
    )
    for step in workflow["steps"]:
        print("  -", step["name"])

print("Saved:", OUTPUT)
