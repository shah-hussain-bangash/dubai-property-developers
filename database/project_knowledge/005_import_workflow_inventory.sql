-- Step 325: Verified workflow inventory
-- Does not change public application tables or Alembic.

BEGIN;

DO $verify_project$
BEGIN
    IF (
        SELECT count(*)
        FROM project_knowledge.projects
        WHERE project_key = 'dubai-real-estate-ai'
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
    $workflow_inventory_payload$[{"entry_key":"workflow:lead_processing","category":"workflows","title":"Lead Processing","content":"Validate, normalize, de-duplicate, qualify, route and store inbound leads.","status":"documented","verification_status":"verified","source_reference":"workflows/lead_flow.py","metadata":{"workflow_id":"lead_processing","workflow_type":"primary","implementation_status":"functional","step_count":5,"steps":[{"name":"validate_normalize_deduplicate","handler_expression":"intake"},{"name":"duplicate_gate","handler_expression":"duplicate_gate"},{"name":"qualify","handler_expression":"qualify"},{"name":"route","handler_expression":"route"},{"name":"store_in_crm","handler_expression":"store_in_crm"}],"source_sha256":"9fc379c9c357a88cba2c6fa9f2313360e243045416610f1842f24979c6f5cdf8","verification_method":"static_source_declaration","production_enabled":null}},{"entry_key":"workflow:property_recommendation","category":"workflows","title":"Property Recommendation","content":"Search, filter, rank and explain properties against customer requirements.","status":"documented","verification_status":"verified","source_reference":"workflows/property_flow.py","metadata":{"workflow_id":"property_recommendation","workflow_type":"primary","implementation_status":"functional","step_count":2,"steps":[{"name":"search_filter_rank","handler_expression":"recommend"},{"name":"compliance_check","handler_expression":"compliance_check"}],"source_sha256":"56d3b6ee695996689d47467f9ec6be12a4817edcbf6a6fc4dcd10eaad348425f","verification_method":"static_source_declaration","production_enabled":null}},{"entry_key":"workflow:sales_conversation","category":"workflows","title":"Sales Conversation","content":"Detect intent, retrieve authorized context, draft a policy-checked reply, then request approval to send or escalate to staff.","status":"documented","verification_status":"verified","source_reference":"workflows/sales_flow.py","metadata":{"workflow_id":"sales_conversation","workflow_type":"primary","implementation_status":"partial","step_count":3,"steps":[{"name":"detect_intent","handler_expression":"detect_intent"},{"name":"retrieve_context_and_draft","handler_expression":"draft_reply"},{"name":"approve_and_dispatch","handler_expression":"dispatch"}],"source_sha256":"300e01579b164af2face676fe75fbf4ac8d409827af11d2c43790014d9e5cc25","verification_method":"static_source_declaration","production_enabled":null}},{"entry_key":"workflow:followup_automation","category":"workflows","title":"Follow-Up Automation","content":"Check due follow-ups, verify consent/status, prepare messages and request approval-gated sends; escalate overdue items.","status":"documented","verification_status":"verified","source_reference":"workflows/followup_flow.py","metadata":{"workflow_id":"followup_automation","workflow_type":"primary","implementation_status":"partial","step_count":1,"steps":[{"name":"check_prepare_request_approval","handler_expression":"plan_and_request"}],"source_sha256":"7e7180be9c067deb15bfda47c8dd1f022a4e20a5f3f80cea14cb6e344ad987dc","verification_method":"static_source_declaration","production_enabled":null}},{"entry_key":"workflow:crm_sync","category":"workflows","title":"CRM Synchronization","content":"Validate external CRM events, match records, resolve conflicts, update and audit.","status":"documented","verification_status":"verified","source_reference":"workflows/crm_sync_flow.py","metadata":{"workflow_id":"crm_sync","workflow_type":"primary","implementation_status":"partial","step_count":4,"steps":[{"name":"validate","handler_expression":"validate"},{"name":"match_and_resolve_conflicts","handler_expression":"match_and_resolve"},{"name":"compute_update","handler_expression":"compute_update"},{"name":"audit","handler_expression":"audit"}],"source_sha256":"cff6283f9c14dbfa9e78ecad8166e21ced109ad34d8f1b6715ebfcba60e547e4","verification_method":"static_source_declaration","production_enabled":null}},{"entry_key":"workflow:knowledge_support","category":"workflows","title":"Knowledge-Based Support","content":"Answer questions from authorized documents with citations, or hand off to a human.","status":"documented","verification_status":"verified","source_reference":"workflows/customer_support_flow.py","metadata":{"workflow_id":"knowledge_support","workflow_type":"primary","implementation_status":"partial","step_count":2,"steps":[{"name":"retrieve_and_prepare_cited_answer","handler_expression":"retrieve_and_answer"},{"name":"confidence_evaluation","handler_expression":"confidence_gate"}],"source_sha256":"e76e9fcf0c4205830b8bbdff3563bf59942ce7da33e5c210b09613e31f7b004e","verification_method":"static_source_declaration","production_enabled":null}},{"entry_key":"workflow:lead_requalification","category":"workflows","title":"Lead Re-qualification","content":"Re-score and re-route an existing lead.","status":"documented","verification_status":"verified","source_reference":"workflows/qualification_flow.py","metadata":{"workflow_id":"lead_requalification","workflow_type":"sub_flow","implementation_status":"functional","step_count":1,"steps":[{"name":"qualify_and_route","handler_expression":"qualify"}],"source_sha256":"189c2f66a0abc14536f8f9f145948c5ed33cccdbf0ac3d16e183eaa8f0b56ece","verification_method":"static_source_declaration","production_enabled":null}}]$workflow_inventory_payload$::jsonb
) AS item
WHERE p.project_key = 'dubai-real-estate-ai'
ON CONFLICT (project_id, entry_key) DO NOTHING;

DO $verify_count$
DECLARE
    actual_count integer;
BEGIN
    SELECT count(*) INTO actual_count
    FROM project_knowledge.knowledge_entries AS k
    JOIN project_knowledge.projects AS p
      ON p.id = k.project_id
    WHERE p.project_key = 'dubai-real-estate-ai'
      AND k.entry_key LIKE 'workflow:%';

    IF actual_count <> 7 THEN
        RAISE EXCEPTION
            'Expected seven workflow records; found %',
            actual_count;
    END IF;
END
$verify_count$;

COMMIT;
