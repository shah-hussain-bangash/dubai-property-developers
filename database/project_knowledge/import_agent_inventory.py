"""Prepare an atomic, source-verified PostgreSQL agent inventory import."""

import hashlib
import json
import re
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[2]
FOLDER = ROOT / "database" / "project_knowledge"
SOURCE = FOLDER / "agent_inventory.json"
DESTINATION = FOLDER / "004_import_agent_inventory.sql"

PROJECT = "dubai-real-estate-ai"
STATUSES = {"functional", "partial", "interface_only"}

if DESTINATION.exists():
    raise RuntimeError("SQL import already exists. Do not overwrite.")

data = json.loads(SOURCE.read_text(encoding="utf-8"))

if data.get("project_key") != PROJECT:
    raise ValueError("Incorrect project key")

agents = data.get("agents")

if not isinstance(agents, list) or len(agents) != 13:
    raise ValueError("Expected exactly 13 agents")

if data.get("agent_count") != 13:
    raise ValueError("Incorrect agent count")

records = []
seen = set()

for agent in agents:
    agent_id = agent["agent_id"]
    path = agent["source_path"]
    status = agent["implementation_status"]
    digest = agent["source_sha256"]

    if not re.fullmatch(r"[a-z][a-z0-9_]*", agent_id):
        raise ValueError("Invalid agent ID")

    if agent_id in seen:
        raise ValueError("Duplicate agent ID")

    seen.add(agent_id)

    if status not in STATUSES:
        raise ValueError("Unknown implementation status")

    parsed = PurePosixPath(path)

    if (
        parsed.is_absolute()
        or ".." in parsed.parts
        or "\\" in path
        or len(parsed.parts) != 3
        or parsed.parts[0] != "agents"
        or parsed.parts[1] != agent_id
        or parsed.parts[2] != "agent.py"
    ):
        raise ValueError("Unexpected agent source path")

    source_file = ROOT / path

    if not source_file.is_file() or source_file.is_symlink():
        raise ValueError("Agent source missing or symlinked")

    actual_hash = hashlib.sha256(
        source_file.read_bytes()
    ).hexdigest()

    if actual_hash != digest:
        raise ValueError(
            f"Agent source changed after extraction: {agent_id}"
        )

    responsibilities = agent["responsibilities"]
    allowed_tools = agent["allowed_tools"]

    if (
        not isinstance(responsibilities, list)
        or not responsibilities
        or not all(
            isinstance(item, str) and item.strip()
            for item in responsibilities
        )
    ):
        raise ValueError("Invalid responsibilities")

    if (
        not isinstance(allowed_tools, list)
        or not all(
            isinstance(item, str) and item.strip()
            for item in allowed_tools
        )
    ):
        raise ValueError("Invalid allowed tools")

    for field in ("name", "description", "class_name"):
        if not isinstance(agent[field], str) or not agent[field].strip():
            raise ValueError(f"Missing {field}")

    records.append({
        "entry_key": "agent:" + agent_id,
        "category": "agents",
        "title": agent["name"],
        "content": agent["description"],
        "status": "documented",
        "verification_status": "verified",
        "source_reference": path,
        "metadata": {
            "agent_id": agent_id,
            "class_name": agent["class_name"],
            "implementation_status": status,
            "responsibilities": responsibilities,
            "allowed_tools": allowed_tools,
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

delimiter = "$agent_inventory_payload$"

if delimiter in payload:
    raise ValueError("Unsafe SQL delimiter in payload")

sql = f"""-- Step 321: source-verified agent inventory.
-- Does not modify application tables or Alembic.
-- Execute without psql -1; transaction is defined below.

BEGIN;

DO $verify_project$
BEGIN
    IF (
        SELECT count(*)
        FROM project_knowledge.projects
        WHERE project_key = '{PROJECT}'
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
WHERE p.project_key = '{PROJECT}'
ON CONFLICT (project_id, entry_key) DO NOTHING;

DO $verify_agents$
DECLARE
    actual_count integer;
BEGIN
    SELECT count(*) INTO actual_count
    FROM project_knowledge.knowledge_entries AS k
    JOIN project_knowledge.projects AS p
      ON p.id = k.project_id
    WHERE p.project_key = '{PROJECT}'
      AND k.entry_key LIKE 'agent:%';

    IF actual_count <> 13 THEN
        RAISE EXCEPTION
            'Expected 13 agent entries, found %',
            actual_count;
    END IF;
END
$verify_agents$;

COMMIT;
"""

DESTINATION.write_text(sql, encoding="utf-8")

print("PASS: Agent SQL import generated")
print("Validated agents:", len(records))
print("Functional:", sum(
    a["implementation_status"] == "functional"
    for a in agents
))
print("Partial:", sum(
    a["implementation_status"] == "partial"
    for a in agents
))
print("Interface only:", sum(
    a["implementation_status"] == "interface_only"
    for a in agents
))
print("SQL file:", DESTINATION)
