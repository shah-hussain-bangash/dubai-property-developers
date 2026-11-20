-- Step 321: source-verified agent inventory.
-- Does not modify application tables or Alembic.
-- Execute without psql -1; transaction is defined below.

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
    $agent_inventory_payload$[{"entry_key":"agent:supervisor","category":"agents","title":"Supervisor Agent","content":"Identifies business intent, selects workflows and agents, escalates sensitive requests.","status":"documented","verification_status":"verified","source_reference":"agents/supervisor/agent.py","metadata":{"agent_id":"supervisor","class_name":"SupervisorAgent","implementation_status":"functional","responsibilities":["Receive user and system requests","Identify business intent","Select specialized agents and workflows","Escalate sensitive requests for human handling"],"allowed_tools":[],"source_sha256":"937c484ba23ba87f96474e17ed978c520c34dac091bce214f1b1439ae24d6810","verification_method":"static_source_declaration","production_enabled":null}},{"entry_key":"agent:lead_intake","category":"agents","title":"Lead Intake Agent","content":"Validates, normalizes and de-duplicates inbound leads.","status":"documented","verification_status":"verified","source_reference":"agents/lead_intake/agent.py","metadata":{"agent_id":"lead_intake","class_name":"LeadIntakeAgent","implementation_status":"functional","responsibilities":["Receive website and portal leads","Validate required information","Normalize phone numbers to E.164","Detect duplicate leads","Prepare structured lead records"],"allowed_tools":["search.lead_duplicates"],"source_sha256":"09b049393077d59b28e51931b2c422856cafbf3af0d498145fb26b25d7ea099a","verification_method":"static_source_declaration","production_enabled":null}},{"entry_key":"agent:qualification","category":"agents","title":"Lead Qualification Agent","content":"Scores leads with explainable factors and assigns a category and route.","status":"documented","verification_status":"verified","source_reference":"agents/qualification/agent.py","metadata":{"agent_id":"qualification","class_name":"QualificationAgent","implementation_status":"functional","responsibilities":["Analyze buying or investment intent","Evaluate lead readiness and budget","Generate explainable lead scores","Assign qualification categories and routing"],"allowed_tools":["analytics.score_lead"],"source_sha256":"f5a96244fdfc8a47c440c3ffdff474e78d455affe0b38dbc1173f436e47956b8","verification_method":"static_source_declaration","production_enabled":null}},{"entry_key":"agent:property_recommendation","category":"agents","title":"Property Recommendation Agent","content":"Matches customer requirements to eligible properties with explained rankings.","status":"documented","verification_status":"verified","source_reference":"agents/property_recommendation/agent.py","metadata":{"agent_id":"property_recommendation","class_name":"PropertyRecommendationAgent","implementation_status":"functional","responsibilities":["Filter properties by budget, location, type and availability","Evaluate payment plan availability","Return ranked, explained recommendations with caveats"],"allowed_tools":["property.match","property.search"],"source_sha256":"bd34eb49f5e267156de875e33ed841211285cec3aea267ca5d4a1846758762bd","verification_method":"static_source_declaration","production_enabled":null}},{"entry_key":"agent:sales_conversation","category":"agents","title":"Sales Conversation Agent","content":"Drafts policy-compliant replies to customer enquiries or escalates to staff.","status":"documented","verification_status":"verified","source_reference":"agents/sales_conversation/agent.py","metadata":{"agent_id":"sales_conversation","class_name":"SalesConversationAgent","implementation_status":"partial","responsibilities":["Handle customer enquiries and project questions","Explain payment plans using cited documents","Support English and Arabic replies","Prepare meeting requests","Hand conversations to human sales agents"],"allowed_tools":["documents.search"],"source_sha256":"ae14bc5b72f37174fd0318537c5f4ee16dd490b200017be0577aa4d86e42a574","verification_method":"static_source_declaration","production_enabled":null}},{"entry_key":"agent:followup","category":"agents","title":"Follow-Up Agent","content":"Finds due follow-ups, checks consent, prepares drafts and requests approved sends.","status":"documented","verification_status":"verified","source_reference":"agents/followup/agent.py","metadata":{"agent_id":"followup","class_name":"FollowUpAgent","implementation_status":"partial","responsibilities":["Track follow-up schedules","Identify unanswered enquiries","Prepare follow-up messages","Request approval-gated sends","Escalate overdue sales activities"],"allowed_tools":["email.render_template","email.send","whatsapp.send_message"],"source_sha256":"b15f9e9ba70c41338fe616edecfb0b3647ef1ade8c2a7e4fce76e0f1e723c20b","verification_method":"static_source_declaration","production_enabled":null}},{"entry_key":"agent:crm","category":"agents","title":"CRM Agent","content":"Persists leads locally and synchronizes them to EspoCRM (mock by default).","status":"documented","verification_status":"verified","source_reference":"agents/crm/agent.py","metadata":{"agent_id":"crm","class_name":"CRMAgent","implementation_status":"functional","responsibilities":["Create and update CRM leads","Retrieve customer information","Update activity histories","Support CRM synchronization"],"allowed_tools":["crm.add_note","crm.create_lead","crm.find_leads","crm.update_lead","leads.save"],"source_sha256":"4a1c01d706cd8f1dbf6778c4dc5aa9335aaa760370029baf7005ff9ab6aa05e3","verification_method":"static_source_declaration","production_enabled":null}},{"entry_key":"agent:email","category":"agents","title":"Email Agent","content":"Prepares template-based email drafts, classifies replies, routes sends via approval.","status":"documented","verification_status":"verified","source_reference":"agents/email/agent.py","metadata":{"agent_id":"email","class_name":"EmailAgent","implementation_status":"partial","responsibilities":["Generate professional email drafts from approved templates","Classify inbound responses","Route outbound messages through approval workflows"],"allowed_tools":["email.render_template","email.send"],"source_sha256":"b01b48dbf9c18e973b42e90da117140283819d062cd3de2d651837dbe3a71abf","verification_method":"static_source_declaration","production_enabled":null}},{"entry_key":"agent:whatsapp","category":"agents","title":"WhatsApp Agent","content":"Handles WhatsApp Business events with opt-in, 24h window and template rules.","status":"documented","verification_status":"verified","source_reference":"agents/whatsapp/agent.py","metadata":{"agent_id":"whatsapp","class_name":"WhatsAppAgent","implementation_status":"partial","responsibilities":["Process WhatsApp Business API events","Maintain conversation state","Prepare contextual replies within messaging rules","Use approved templates outside the service window","Escalate conversations to staff"],"allowed_tools":["whatsapp.send_message"],"source_sha256":"94921f163c8a39a6665f21f507aabd04b4e8389234aa529818cd82532ecfb5a4","verification_method":"static_source_declaration","production_enabled":null}},{"entry_key":"agent:voice","category":"agents","title":"Voice AI Agent","content":"Future voice channel: transcription, intent, summary and human call escalation.","status":"documented","verification_status":"verified","source_reference":"agents/voice/agent.py","metadata":{"agent_id":"voice","class_name":"VoiceAgent","implementation_status":"interface_only","responsibilities":["Speech-to-text processing (pending provider)","Intent detection","Conversation summarization","Appointment request handling","Human call escalation"],"allowed_tools":[],"source_sha256":"1a6a19ccef4d8b9adce61f9a0e2c4acff1a7de152b49bfa62ab8b2c2c2802bcc","verification_method":"static_source_declaration","production_enabled":null}},{"entry_key":"agent:marketing","category":"agents","title":"Marketing Agent","content":"Segments consented leads and prepares campaign copy drafts for review.","status":"documented","verification_status":"verified","source_reference":"agents/marketing/agent.py","metadata":{"agent_id":"marketing","class_name":"MarketingAgent","implementation_status":"partial","responsibilities":["Support lead segmentation","Prepare campaign copy drafts","Identify campaign opportunities","Prepare analytics-driven recommendations"],"allowed_tools":[],"source_sha256":"94098b674f35c4283205ce630722a394ab67c50e34124a710ecfc974b690471f","verification_method":"static_source_declaration","production_enabled":null}},{"entry_key":"agent:documents","category":"agents","title":"Document Agent","content":"Summarizes permitted documents and answers questions with citations (RAG).","status":"documented","verification_status":"verified","source_reference":"agents/documents/agent.py","metadata":{"agent_id":"documents","class_name":"DocumentAgent","implementation_status":"partial","responsibilities":["Read permitted property documents","Extract relevant information","Prepare document summaries","Support retrieval-augmented answers with citations"],"allowed_tools":["documents.search"],"source_sha256":"a6812437c884f4a16637218fd3a927e68c3af45b3f231db0325fd13f6e5b956b","verification_method":"static_source_declaration","production_enabled":null}},{"entry_key":"agent:analytics","category":"agents","title":"Analytics Agent","content":"Reports lead sources, conversion and agent performance metrics.","status":"documented","verification_status":"verified","source_reference":"agents/analytics/agent.py","metadata":{"agent_id":"analytics","class_name":"AnalyticsAgent","implementation_status":"partial","responsibilities":["Report lead sources","Monitor conversion metrics","Analyze agent performance","Report workflow statistics"],"allowed_tools":["analytics.sales_summary"],"source_sha256":"14dbcd05c07be1ad789110e76456ea16d5f046dfb23cb32fc61c0c016420e20a","verification_method":"static_source_declaration","production_enabled":null}}]$agent_inventory_payload$::jsonb
) AS item
WHERE p.project_key = 'dubai-real-estate-ai'
ON CONFLICT (project_id, entry_key) DO NOTHING;

DO $verify_agents$
DECLARE
    actual_count integer;
BEGIN
    SELECT count(*) INTO actual_count
    FROM project_knowledge.knowledge_entries AS k
    JOIN project_knowledge.projects AS p
      ON p.id = k.project_id
    WHERE p.project_key = 'dubai-real-estate-ai'
      AND k.entry_key LIKE 'agent:%';

    IF actual_count <> 13 THEN
        RAISE EXCEPTION
            'Expected 13 agent entries, found %',
            actual_count;
    END IF;
END
$verify_agents$;

COMMIT;
