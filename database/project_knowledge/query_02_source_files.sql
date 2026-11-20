SELECT
    source_path,
    reference_type,
    content_sha256
FROM project_knowledge.source_references
ORDER BY source_path;