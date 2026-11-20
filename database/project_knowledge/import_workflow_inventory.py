"""Validate workflow inventory and generate a transactional SQL import."""

import hashlib
import json
import re
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[2]
FOLDER = ROOT / "database" / "project_knowledge"
SOURCE = FOLDER / "workflow_inventory.json"
DESTINATION = FOLDER / "005_import_workflow_inventory.sql"

PROJECT_KEY = "dubai-real-estate-ai"

EXPECTED_IDS = {
    "lead_processing",
    "property_recommendation",
    "sales_conversation",
    "followup_automation",
    "crm_sync",
    "knowledge_support",
    "lead_requalification",
}

if DESTINATION.exists():
    raise RuntimeError("SQL file already exists. Stop.")

data = json.loads(SOURCE.read_text(encoding="utf-8"))

if data.get("project_key") != PROJECT_KEY:
    raise ValueError("Incorrect project key")

workflows = data.get("workflows")

if not isinstance(workflows, list) or len(workflows) != 7:
    raise ValueError("Expected seven workflows")

if data.get("workflow_count") != 7:
    raise ValueError("Incorrect workflow count")

ids = {w["workflow_id"] for w in workflows}

if ids != EXPECTED_IDS:
    raise ValueError("Unexpected workflow identifiers")

records = []

for workflow in workflows:
    workflow_id = workflow["workflow_id"]
    path = workflow["source_path"]
    digest = workflow["source_sha256"]
    status = workflow["implementation_status"]
    workflow_type = workflow["workflow_type"]
    steps = workflow["steps"]

    if not re.fullmatch(r"[a-z][a-z0-9_]*", workflow_id):
        raise ValueError("Invalid workflow ID")

    parsed = PurePosixPath(path)

    if (
        parsed.is_absolute()
        or ".." in parsed.parts
        or "\\" in path
        or len(parsed.parts) != 2
        or parsed.parts[0] != "workflows"
        or not parsed.name.endswith(".py")
    ):
        raise ValueError(f"Unexpected source path: {path}")

    source_file = ROOT / path

    if not source_file.is_file() or source_file.is_symlink():
        raise ValueError(f"Missing source file: {path}")

    actual_hash = hashlib.sha256(
        source_file.read_bytes()
    ).hexdigest()

    if actual_hash != digest:
        raise ValueError(
            f"Source file changed after extraction: {path}"
        )

    if status not in {"functional", "partial", "interface_only"}:
        raise ValueError("Invalid implementation status")

    expected_type = (
        "sub_flow"
        if workflow_id == "lead_requalification"
        else "primary"
    )

    if workflow_type != expected_type:
        raise ValueError("Incorrect workflow type")

    if not isinstance(steps, list) or not steps:
        raise ValueError("Workflow has no steps")

    step_names = []

    for step in steps:
        name = step.get("name")
        handler = step.get("handler_expression")

        if not isinstance(name, str) or not name.strip():
            raise ValueError("Invalid step name")

        if not isinstance(handler, str) or not handler.strip():
            raise ValueError("Invalid handler")

        step_names.append(name)

    if len(step_names) != len(set(step_names)):
        raise ValueError("Duplicate step names")

    if not isinstance(workflow["name"], str):
        raise ValueError("Invalid workflow name")

    if not isinstance(workflow["description"], str):
        raise ValueError("Invalid workflow description")

    records.append({
        "entry_key": "workflow:" + workflow_id,
        "category": "workflows",
        "title": workflow["name"],
        "content": workflow["description"],
        "status": "documented",
        "verification_status": "verified",
        "source_reference": path,
        "metadata": {
            "workflow_id": workflow_id,
            "workflow_type": workflow_type,
            "implementation_status": status,
            "step_count": len(steps),
            "steps": steps,
            "source_sha256": digest,
            "verification_method": "static_source_declaration",
            "production_enabled": None,
        },
    })

payload = json.dumps(
    records,
    ensure_ascii=True,
    separators=(",", ":"),
)

delimiter = "$workflow_inventory_payload$"

if delimiter in payload:
    raise ValueError("Unsafe SQL delimiter")

sql = f"""-- Step 325: Verified workflow inventory
-- Does not change public application tables or Alembic.

BEGIN;

DO $verify_project$
BEGIN
    IF (
        SELECT count(*)
        FROM project_knowledge.projects
        WHERE project_key = '{PROJECT_KEY}'
    ) <> 1 THEN
        RAISE EXCEPTION 'Target project missing';
    END IF;
END
$verify_project$;

INSERT INTO project_knowledge.knowledge_entries
    (
        project_id,
        entry_key,
        category,
        title,
        content,
        status,
        verification_status,
        source_reference,
        metadata
    )
SELECT
    p.id,
    item->>'entry_key',
    item->>'category',
    item->>'title',
    item->>'content',
    item->>'status',
    item->>'verification_status',
    item->>'source_reference',
    item->'metadata'
FROM project_knowledge.projects AS p
CROSS JOIN jsonb_array_elements(
    {delimiter}{payload}{delimiter}::jsonb
) AS item
WHERE p.project_key = '{PROJECT_KEY}'
ON CONFLICT (project_id, entry_key) DO NOTHING;

DO $verify_count$
DECLARE
    actual_count integer;
BEGIN
    SELECT count(*) INTO actual_count
    FROM project_knowledge.knowledge_entries AS k
    JOIN project_knowledge.projects AS p
      ON p.id = k.project_id
    WHERE p.project_key = '{PROJECT_KEY}'
      AND k.entry_key LIKE 'workflow:%';

    IF actual_count <> 7 THEN
        RAISE EXCEPTION
            'Expected seven workflow records; found %',
            actual_count;
    END IF;
END
$verify_count$;

COMMIT;
"""

DESTINATION.write_text(sql, encoding="utf-8")

print("PASS: Workflow SQL import generated")
print("Validated workflows:", len(records))
print("Total workflow steps:", sum(
    len(w["steps"]) for w in workflows
))
print("SQL file:", DESTINATION)
