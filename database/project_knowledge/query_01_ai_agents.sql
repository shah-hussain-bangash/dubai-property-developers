SELECT
    metadata->>'agent_id' AS agent_name,
    metadata->>'implementation_status' AS status,
    metadata->'responsibilities' AS responsibilities,
    metadata->'allowed_tools' AS allowed_tools
FROM project_knowledge.knowledge_entries
WHERE entry_key LIKE 'agent:%'
ORDER BY agent_name;