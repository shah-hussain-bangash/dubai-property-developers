# Send a FICTIONAL lead to the development-only demo endpoint (API must be running).
$body = @{
    full_name = "Demo Lead One"
    email = "demo.lead.one@example.com"
    phone = "050 000 0001"
    source = "website"
    message = "Looking for a 1 bedroom in Business Bay, would like a viewing."
    budget_max_aed = "1500000"
    preferred_locations = @("Business Bay")
    property_types = @("apartment")
    bedrooms = 1
    purpose = "investment"
    timeline_months = 3
    consent_whatsapp = $true
} | ConvertTo-Json
Invoke-RestMethod -Method Post -Uri "http://localhost:8000/api/v1/leads/demo-process" `
    -ContentType "application/json" -Body $body | ConvertTo-Json -Depth 10
