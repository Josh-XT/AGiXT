// Auto-ported from web ResourceGuidanceCard mounts
window.AgixtPromptGuidanceData = {
  "tickets": {
    title: "Coach your agent through tickets",
    description: "Create, triage, or close tickets in natural language and let the agent keep this list synced.",
    requiredAbilities: ["List Tickets", "Create Ticket", "Update Ticket", "Close Ticket", "Delete Ticket"],
    extensionName: "tickets",
    enableInstructions: "Enable the Ticket abilities in Settings → Extensions → Core Abilities so your agent can work tickets from chat.",
    examples: [
      {
        label: "Triage the open backlog",
        prompt: "Review every open ticket for {{company}} and produce a prioritized triage list. For each ticket, weigh stated priority, age, time since last update, customer impact, and SLA risk. Recommend the next action (assign, escalate, request info, close) and flag anything that looks stalled or misclassified.",
        placeholders: [
          { id: "company", label: "Company", type: "company", inputType: "text" }
        ]
      },
      {
        label: "Find related & duplicate tickets",
        prompt: "Look at ticket {{ticketNumber}} and find other open or recently closed tickets across {{company}} that look like duplicates, related symptoms, or the same root cause. Summarize the cluster and recommend whether to merge, link, or treat separately.",
        placeholders: [
          { id: "ticketNumber", label: "Ticket", type: "ticket", required: true, inputType: "text" },
          { id: "company", label: "Company", type: "company", inputType: "text" }
        ]
      },
      {
        label: "Draft a customer reply",
        prompt: "Read the full history of ticket {{ticketNumber}}, search for similar past tickets that were resolved, and draft a clear, professional reply to the customer. Tone: {{tone}}. Include next steps, what we need from them, and a realistic ETA. Do not send it — show me the draft for review.",
        placeholders: [
          { id: "ticketNumber", label: "Ticket", type: "ticket", required: true, inputType: "text" },
          { id: "tone", label: "Tone", description: "e.g. apologetic, reassuring, concise & technical, executive-friendly", required: true, inputType: "text" }
        ]
      },
      {
        label: "SLA breach risk report",
        prompt: "Identify every open {{priority}} ticket for {{company}} that is at risk of breaching SLA in the next 24 hours, or has already breached. For each, summarize current state, who is assigned, what is blocking it, and the single most useful next step.",
        placeholders: [
          { id: "priority", label: "Priority", type: "priority", inputType: "text" },
          { id: "company", label: "Company", type: "company", inputType: "text" }
        ]
      },
      {
        label: "Recurring issue analysis",
        prompt: "Analyze tickets opened in the last {{days}} days for {{company}}. Cluster them by underlying root cause (not just title), identify the top 3 recurring problems, quantify the time spent on each, and recommend a permanent fix (KB article, automation, package, configuration change) for each.",
        placeholders: [
          { id: "days", label: "Lookback (days)", required: true, inputType: "text" },
          { id: "company", label: "Company", type: "company", inputType: "text" }
        ]
      },
      {
        label: "Workload rebalance",
        prompt: "Show current open ticket counts and weighted workload (by priority and age) per assignee for {{company}}. Identify anyone overloaded or under-utilized and propose specific reassignments to balance the queue, with reasoning for each move.",
        placeholders: [
          { id: "company", label: "Company", type: "company", inputType: "text" }
        ]
      },
      {
        label: "Weekly status report",
        prompt: "Produce a weekly status report for {{company}}: tickets opened, closed, still open by priority, average time-to-resolution, biggest wins, biggest concerns, and any tickets that are stuck. Format it as something I can paste into an email to a stakeholder.",
        placeholders: [
          { id: "company", label: "Company", type: "company", required: true, inputType: "text" }
        ]
      },
      {
        label: "Convert a resolved ticket to a KB article",
        prompt: "Take resolved ticket {{ticketNumber}} and turn it into a knowledge base article: problem statement, environment, symptoms, root cause, step-by-step resolution, and how to prevent recurrence. Then suggest a short title and tags.",
        placeholders: [
          { id: "ticketNumber", label: "Ticket", type: "ticket", required: true, inputType: "text" }
        ]
      }
    ]
  },

  "secrets": {
    title: "Let your agent stay on top of secrets",
    description: "Rotate expiring credentials, add new entries, or audit access right from chat so this vault stays current.",
    requiredAbilities: ["List Secrets", "Get Expiring Soon Secrets", "Create Secret", "Update Secret", "Delete Secret"],
    extensionName: "secrets",
    enableInstructions: "Enable the Secrets abilities in Settings → Extensions → Core Abilities so your agent can securely manage credentials for you.",
    examples: [
      {
        label: "Rotation plan for expiring secrets",
        prompt: "List every secret expiring in the next 30 days. For each, identify what it protects, who owns it, and the safest rotation order (dependencies first). Produce a step-by-step rotation runbook including who to notify, where the secret is consumed, and the rollback plan if rotation fails."
      },
      {
        label: "Stale & abandoned secret audit",
        prompt: "Find secrets that look stale or abandoned: not updated in over a year, owned by users who have left, tied to retired services, or with no owner at all. Recommend whether each should be rotated, archived, or deleted, with the reasoning."
      },
      {
        label: "Coverage gap analysis",
        prompt: "For each company, list the categories of secrets we typically expect (cloud admin, VPN, database, API keys, service accounts, certificates) and identify which ones we appear to be missing or under-documented. Flag anything that suggests credentials are being managed outside this vault."
      },
      {
        label: "Blast-radius assessment",
        prompt: "For secret \"{{secret_name}}\", explain its blast radius: what systems and accounts it can access, who currently uses it, last rotation, expiry, and any dependent automations. Then rate the risk if it leaked and recommend hardening steps."
      },
      {
        label: "Bulk rotation by category",
        prompt: "I want to rotate every {{category}} secret across all companies. Build a staged rotation plan: which to do first, which require coordination with vendors, which are safe to automate, and which need a human in the loop. Do not rotate anything yet — show me the plan."
      },
      {
        label: "Compliance & policy audit",
        prompt: "Audit secrets for policy compliance: every secret should have an owner, expiration date, category, and last-rotated date within policy. Output a non-compliance report grouped by company with the specific fix for each row."
      },
      {
        label: "Onboard a new system",
        prompt: "I am onboarding a new system \"{{system_name}}\" for {{company}}. Walk me through which secrets we should provision (admin, service, integration, monitoring), suggest naming and expiry conventions, and create the entries — but ask me to confirm each value before saving."
      }
    ]
  },

  "assets": {
    title: "Ask your agent to manage assets",
    description: "Register new equipment, update ownership, or pull inventories from chat while keeping this table current.",
    requiredAbilities: ["List Assets", "Create Asset", "Update Asset", "Delete Asset", "Assign Asset Owner"],
    extensionName: "assets",
    enableInstructions: "Enable the Asset abilities in Settings → Extensions so your agent can catalog and maintain assets automatically.",
    examples: [
      {
        label: "Reconcile assets to discovered devices",
        prompt: "Compare the asset inventory against devices discovered on the network and registered machines. List devices that have no matching asset (need to be added), assets that have no live device (likely retired or stolen), and mismatches in serial number, hostname, or owner. Propose a reconciliation plan."
      },
      {
        label: "Identify ownership & data gaps",
        prompt: "Find every asset that is missing an owner, missing a serial number, missing a location/site, or has not been updated in over a year. Group by asset type and recommend the lowest-effort fix for each cluster."
      },
      {
        label: "Lifecycle & refresh planning",
        prompt: "Build a hardware refresh plan for the next 12 months: identify assets approaching warranty expiration, end-of-life models, and machines with degraded performance. Group by department and propose a quarterly replacement schedule with estimated impact."
      },
      {
        label: "Offboarding sweep for a person",
        prompt: "List every asset currently assigned to {{owner}}. Note location, last seen, and condition for each, and produce a checklist for collecting/wiping/reassigning each item before they leave."
      },
      {
        label: "Bulk import from a spreadsheet",
        prompt: "Here is an asset list (paste CSV or attach file). For each row, check whether it already exists in our inventory, propose create or update, normalize fields (serial format, manufacturer name, asset type), and show me the dry-run plan before saving anything."
      },
      {
        label: "License & compliance audit",
        prompt: "For software-license assets, check that we have enough seats for currently assigned users, identify any license assigned to someone who has left, and flag licenses approaching renewal in the next 90 days with their cost."
      },
      {
        label: "Site / location inventory report",
        prompt: "Produce an inventory report for {{site}}: assets on site grouped by type, value, age, and owner. Highlight anything anomalous (unowned, unreturned, recently moved) and summarize total replacement value."
      }
    ]
  },

  "contacts": {
    title: "Let your agent keep contacts up to date",
    description: "You can capture new people, update details, or pull quick lists just by asking in the chat.",
    requiredAbilities: ["List Contacts", "Create Contact", "Update Contact", "Delete Contact"],
    extensionName: "contacts",
    enableInstructions: "Enable the Contacts abilities in Settings → Extensions → Core Abilities so your agent can view and manage contacts for you.",
    examples: [
      {
        label: "Deduplicate the contact list",
        prompt: "Scan all contacts at {{company}} for likely duplicates (same person across slightly different names, emails, phones, or formatting). Group them, recommend which record to keep, and propose the merge plan — but do not delete anything until I approve.",
        placeholders: [
          { id: "company", label: "Company", inputType: "text" }
        ]
      },
      {
        label: "Find data quality gaps",
        prompt: "Audit contacts at {{company}} for missing or low-quality data: no email, no phone, no company link, invalid email format, generic shared inbox addresses, or contacts not updated in over a year. Output a prioritized cleanup list with the suggested fix for each.",
        placeholders: [
          { id: "company", label: "Company", inputType: "text" }
        ]
      },
      {
        label: "Build a stakeholder map",
        prompt: "Build a stakeholder map for {{company}}: who are the decision makers, technical contacts, billing contacts, and day-to-day users based on contact roles, titles, and historical interactions? Highlight any role we appear to be missing a contact for.",
        placeholders: [
          { id: "company", label: "Company", required: true, inputType: "text" }
        ]
      },
      {
        label: "Quarterly outreach plan",
        prompt: "Suggest a quarterly outreach plan for {{company}}. Identify which contacts we have not engaged in {{days}}+ days, prioritize who to reach out to, draft a short personalized opener for each, and group them by relationship strength.",
        placeholders: [
          { id: "company", label: "Company", required: true, inputType: "text" },
          { id: "days", label: "No-contact threshold (days)", inputType: "text", required: true }
        ]
      },
      {
        label: "Capture contacts from a conversation",
        prompt: "Here is the text of an email/meeting/transcript: <paste content>. Extract every person mentioned, infer their company, role, email, and phone if present, check whether each one already exists as a contact, and propose either a create or update for each — show me the plan before saving anything."
      },
      {
        label: "Investigate a single contact",
        prompt: "Give me a full briefing on {{contactName}}: their company, role, recent tickets, recent estimates, notes, last interactions, and anything noteworthy. End with the 1-2 things I should mention or follow up on next time we talk.",
        placeholders: [
          { id: "contactName", label: "Contact", required: true, inputType: "text" }
        ]
      },
      {
        label: "Re-classify contact statuses",
        prompt: "Review every contact at {{company}} and propose status updates based on actual recent activity (active, dormant, churned, prospect). Show the current status, recommended status, and the evidence for each change. Do not apply changes until I approve.",
        placeholders: [
          { id: "company", label: "Company", inputType: "text" }
        ]
      }
    ]
  },

  "estimates": {
    title: "Estimate Assistant",
    description: "Let AI help you create and manage estimates faster",
    requiredAbilities: ["Create Estimate", "Decode VIN", "Analyze Damage"],
    extensionName: "ultraestimate",
    examples: [
      {
        label: "Build a complete estimate from a VIN + photos",
        prompt: "Decode VIN {{vin}} for customer {{customer}}. Identify the year/make/model/trim, look up OEM part numbers for the {{impact}} area, analyze any photos I attach for visible damage, and build a full draft estimate with R&R, repair, refinish, and related operations (clear coat, hazardous waste, cover car, etc.). Use realistic labor times and call out anything that needs a human inspection before finalizing.",
        placeholders: [
          { id: "vin", label: "VIN", type: "text", required: true, inputType: "text" },
          { id: "customer", label: "Customer", type: "select", required: true, inputType: "text" },
          {
            id: "impact", label: "Point of Impact", type: "select", required: true, inputType: "select",
            options: [
              { value: "front", label: "front" },
              { value: "front_left", label: "front_left" },
              { value: "front_right", label: "front_right" },
              { value: "left", label: "left" },
              { value: "right", label: "right" },
              { value: "rear", label: "rear" },
              { value: "rear_left", label: "rear_left" },
              { value: "rear_right", label: "rear_right" },
              { value: "top", label: "top" },
              { value: "undercarriage", label: "undercarriage" },
              { value: "multiple", label: "multiple" }
            ]
          }
        ]
      },
      {
        label: "Photo-driven damage analysis",
        prompt: "Analyze the attached photos of {{vehicle}}. List every damaged panel and component, classify each as repair vs. replace based on severity, identify likely hidden damage (intrusion, sensors, brackets, foam absorbers), and produce a line-item draft estimate with reasoning for each call.",
        placeholders: [
          { id: "vehicle", label: "Vehicle", type: "select", required: true, inputType: "text" }
        ]
      },
      {
        label: "Find missing operations on an estimate",
        prompt: "Review estimate #{{estimateNumber}} and identify commonly missed operations: clear coat, color tint, edging, blend panels, R&I of attached parts, seatbelt/airbag inspection, ADAS calibration, pre/post scans, hazardous waste, cover car, feather/prime/block. Recommend which apply for this specific repair and why.",
        placeholders: [
          { id: "estimateNumber", label: "Estimate #", type: "text", required: true, inputType: "text" }
        ]
      },
      {
        label: "Sanity-check labor hours and pricing",
        prompt: "Audit estimate #{{estimateNumber}} for line items where labor hours look low or high vs. typical industry times for this vehicle, missing OEM part numbers, parts priced significantly above or below normal, and operations that should be R&R instead of repair (or vice versa). Output a prioritized review list with the suggested change for each.",
        placeholders: [
          { id: "estimateNumber", label: "Estimate #", type: "text", required: true, inputType: "text" }
        ]
      },
      {
        label: "Generate insurance-ready supplement justification",
        prompt: "For estimate #{{estimateNumber}}, draft clear, defensible justifications for each line item likely to be questioned by an insurance reviewer. Cite the operation reason (e.g. structural intrusion, ADAS recalibration requirement, OEM repair procedure) so I can paste this into a supplement request.",
        placeholders: [
          { id: "estimateNumber", label: "Estimate #", type: "text", required: true, inputType: "text" }
        ]
      },
      {
        label: "Compare estimate to similar past jobs",
        prompt: "Find past estimates for the same/similar vehicle and impact area as estimate #{{estimateNumber}}. Compare total hours, parts cost, and operation list. Highlight what is different and whether the differences look justified by the damage on this job.",
        placeholders: [
          { id: "estimateNumber", label: "Estimate #", type: "text", required: true, inputType: "text" }
        ]
      },
      {
        label: "Customer-friendly estimate summary",
        prompt: "Take estimate #{{estimateNumber}} and produce a plain-English summary for the customer: what we are repairing vs. replacing, what the timeline looks like, what the total is, and what insurance vs. customer is likely to cover. Keep it short, friendly, and free of body shop jargon.",
        placeholders: [
          { id: "estimateNumber", label: "Estimate #", type: "text", required: true, inputType: "text" }
        ]
      },
      {
        label: "Pipeline & approval status",
        prompt: "Show every estimate currently waiting on customer approval, insurance approval, or supplement, sorted by age. For each, summarize what it is waiting on and recommend the next nudge or follow-up action."
      }
    ]
  },

  "invoices": {
    title: "Let your agent run your billing operations",
    description: "Generate recurring invoices, chase overdue balances, reconcile payments, and design templates without leaving chat.",
    requiredAbilities: ["Get Invoices", "Create Invoice", "Update Invoice", "Add Payment", "Create Invoice Template", "Create Invoice From Product", "Split Bill Across Contacts", "Create Monthly Service Invoice"],
    extensionName: "invoices",
    enableInstructions: "Enable the Invoices extension in Settings → Extensions so your agent can create invoices, record payments, and manage products and templates for you.",
    examples: [
      {
        label: "Bill recurring services for the month",
        prompt: "Generate this month's recurring service invoices for every active managed-services customer. Pull line items from their assigned products, apply standard taxes, set the due date to net-30, and stage them as drafts so I can review before sending."
      },
      {
        label: "Run an AR aging review",
        prompt: "Build an accounts-receivable aging report grouping outstanding invoices into 0-30, 31-60, 61-90, and 90+ day buckets by customer. Highlight the top five overdue balances and suggest the next dunning step for each."
      },
      {
        label: "Draft a polite collections sequence",
        prompt: "For every invoice past due by more than 15 days, draft a friendly first-reminder email referencing the invoice number, amount, and due date. Mark anything past 45 days for a phone-call escalation and draft a script for it."
      },
      {
        label: "Convert an estimate to an invoice",
        prompt: "Take the most recent approved estimate for {customer_name}, copy its line items into a new invoice, apply a 50% deposit-paid credit, and set terms to net-15. Show me the draft before saving."
      },
      {
        label: "Split a shared bill across residents",
        prompt: "Split this $4,800 landscaping invoice across all active homeowners in {hoa_name} proportional to their unit count, generate one child invoice per resident, and link them back to the parent for reconciliation."
      },
      {
        label: "Find revenue leaks",
        prompt: "Compare the last 90 days of invoices to active service agreements. Flag any customer who is on a recurring plan but has not been invoiced this cycle, and any one-off work that should have been billed against an existing retainer."
      },
      {
        label: "Build a new invoice template",
        prompt: "Create a new invoice template named \"Quarterly MSP\" with our standard remote-monitoring, patching, and helpdesk line items, a quarterly recurrence, net-15 terms, and our boilerplate footer. Save it so I can apply it to customers."
      },
      {
        label: "Reconcile a batch of payments",
        prompt: "Here is a CSV of payments from our payment processor. Match each one to its open invoice by amount and customer, record the payments, mark fully-paid invoices closed, and tell me anything that did not match cleanly."
      },
      {
        label: "Summarize this month for the books",
        prompt: "Summarize this month's invoicing activity: total invoiced, total collected, outstanding balance, top 10 customers by revenue, and the change vs. last month. Format it so I can paste it into our finance channel."
      },
      {
        label: "Rebuild the product catalog",
        prompt: "Audit our product catalog. Group products by category, flag any with no recent sales, suggest price tier consolidation where SKUs overlap, and propose three new bundle products based on what customers actually buy together."
      }
    ]
  },

  "machines": {
    title: "Machine Control Tips",
    description: "Manage machine registrations, execute remote commands, transfer files, capture screenshots, and automate workflows using the AGiXT Machines API. Use the + button in the toolbar to add a new machine.",
    requiredAbilities: ["Get Machines", "Get Machine Details", "Get Machines by Status", "Create Machine Note", "Get Machine Note", "Update Machine Note", "Delete Machine Note", "Delete Machine", "List Machine Notes", "Search Machine Notes", "Open Remote Terminal", "Execute in Terminal", "Close Remote Terminal", "Send Mouse Click", "Move Mouse", "Drag Mouse", "Send Keyboard Input", "Capture Screenshot", "Upload File to Machine", "Download File from Machine", "Get Agent Installers"],
    extensionName: "machines",
    enableInstructions: "Enable the Machines extension inside AGiXT > Settings > Extensions to unlock full machine control: approvals, remote commands, file operations, screenshots, and automation.",
    examples: [
      {
        label: "Fleet-wide health audit",
        prompt: "Audit every online machine for low disk space (under 10% free), sustained high CPU or memory usage, and pending OS updates. Group findings by severity, propose a prioritized remediation plan, and add a note to each affected machine summarizing what needs attention."
      },
      {
        label: "Investigate offline machines",
        prompt: "List every machine that went offline in the last {{hours}} hours. For each, pull its last known alerts, recent commands, and tags, then summarize the most likely causes grouped by location or tag pattern. Flag any that look like a coordinated outage versus isolated incidents.",
        placeholders: [
          { id: "hours", label: "Lookback window (hours)", required: true }
        ]
      },
      {
        label: "Compliance audit across the fleet",
        prompt: "Audit all machines for compliance: every machine should have the latest endpoint agent version, at least one assigned policy, an owner tag, and have checked in within the last 24 hours. Produce a non-compliance report grouped by company and propose the exact fix for each row."
      },
      {
        label: "Suspected compromise — incident response",
        prompt: "I suspect {{hostname}} is compromised. Take a screenshot, list running processes and listening network connections, capture the last hour of relevant alerts, then write a detailed forensic note with your findings and a recommended containment plan. Do not make destructive changes — only gather evidence and recommend.",
        placeholders: [
          { id: "hostname", label: "Hostname", required: true }
        ]
      },
      {
        label: "Onboard newly approved machines",
        prompt: "Find every machine approved in the last 7 days that has no policy assigned or is missing standard tags. Assign the \"{{policy_name}}\" policy, add the \"{{tag}}\" tag, run a baseline health check, and reply with a summary of what was changed on each.",
        placeholders: [
          { id: "policy_name", label: "Policy to assign", required: true },
          { id: "tag", label: "Tag to add", required: true }
        ]
      },
      {
        label: "Software inventory & gap analysis",
        prompt: "Build a fleet-wide software inventory of installed applications and versions. Highlight any machines missing \"{{required_software}}\", running outdated versions, or with unauthorized software installed. Output a table grouped by company and tag.",
        placeholders: [
          { id: "required_software", label: "Required software (name or pattern)", required: true }
        ]
      },
      {
        label: "Cross-machine log correlation",
        prompt: "Across every machine tagged \"{{tag}}\", search system logs and event logs for occurrences of \"{{search_term}}\" within the last {{hours}} hours. Correlate timestamps to identify whether issues are spreading, isolated, or recurring on a schedule, and write a single combined report with timeline.",
        placeholders: [
          { id: "tag", label: "Machine tag", required: true },
          { id: "search_term", label: "Term or error to search for", required: true },
          { id: "hours", label: "Lookback window (hours)", required: true }
        ]
      },
      {
        label: "Failed deployment triage",
        prompt: "Review package deployments from the last 14 days that failed or partially succeeded. Group failures by error pattern, identify common root causes (network, permissions, dependencies, OS version), and propose a concrete fix or retry strategy for each cluster."
      },
      {
        label: "Capacity & rightsizing report",
        prompt: "For every machine, summarize average CPU, memory, and disk utilization over the last 30 days. Identify machines that are consistently over-provisioned (under 20% utilization) or under-provisioned (over 80%), and recommend rightsizing or workload rebalancing actions."
      },
      {
        label: "Targeted bulk diagnostic",
        prompt: "On every {{os}} machine matching tag \"{{tag}}\", run a diagnostic sweep: collect OS version, patch level, network configuration, and the top 10 processes by memory. Summarize the results in a single comparison table and call out any outliers.",
        placeholders: [
          { id: "os", label: "Operating system (Windows / Linux / macOS)", required: true },
          { id: "tag", label: "Machine tag to target", required: true }
        ]
      }
    ]
  },

  "monitors": {
    title: "Let your agent design and tune monitors",
    description: "Monitors evaluate machine telemetry (CPU, memory, disk, offline, container/service state, network, website health) and trigger actions like webhooks, command execution, container/service control, or package deployment. Ask the agent to draft, audit, or tune them in plain English.",
    requiredAbilities: ["Get Machines", "Get Machine Details", "Get Machines by Status"],
    extensionName: "machines",
    enableInstructions: "Enable the Machines extension in Settings → Extensions so your agent can manage monitors for you.",
    examples: [
      {
        label: "Build a tiered CPU/memory monitor set",
        prompt: "Create a tiered set of monitors for every machine tagged \"{{tag}}\": warning when CPU stays above 80% for 10 minutes, critical when CPU stays above 95% for 5 minutes, warning when memory stays above 85% for 10 minutes, and critical when memory stays above 95% for 5 minutes. Set cooldown to 30 minutes for warnings and 10 minutes for critical. On critical, run a webhook action so it surfaces in the alerts feed; on warning, just notify. Show me the monitor specs before creating them."
      },
      {
        label: "Disk space early warning ladder",
        prompt: "Create disk monitors per mount for {{target}}: info at 70% used, warning at 85%, critical at 95%, all sustained for 15 minutes. On critical, also queue the \"Cleanup Temp & Logs\" package (deploy_package action) and send a webhook. Use a 60-minute cooldown so we do not spam alerts during ongoing cleanup."
      },
      {
        label: "Self-healing container monitor",
        prompt: "For machines tagged \"{{tag}}\", create a container_state monitor for the \"{{container_name}}\" container. When it is not running for more than 60 seconds, automatically run a docker_action of type \"start\", and if that fails, escalate to a webhook alert. Cooldown 5 minutes. Severity warning. Show me the JSON before saving."
      },
      {
        label: "Self-healing service monitor",
        prompt: "Create a service_state monitor for \"{{service_name}}\" on machines matching {{target}}. Expected state is running. When breached for 30 seconds, automatically run a manage_service action of type \"start\", then re-evaluate; if still down after the next check, escalate via webhook with severity critical."
      },
      {
        label: "Offline machine alerting",
        prompt: "Create an \"offline\" monitor for every approved machine in {{company}} that triggers critical when a machine has not checked in for 10 minutes. Cooldown 30 minutes. Action: webhook only — no auto-remediation. Skip machines tagged \"maintenance\" or \"decommissioned\"."
      },
      {
        label: "Website health monitor with on-call escalation",
        prompt: "Create a website_health monitor for {{url}}: trigger warning if response time exceeds {{slow_ms}}ms for 3 consecutive checks, critical if status is non-2xx or unreachable for 2 consecutive checks. On critical, fire a webhook action and run the \"On-Call Notify\" package (deploy_package). 5-minute cooldown."
      },
      {
        label: "Docker Compose stack auto-recovery",
        prompt: "For the machine running our \"{{stack_name}}\" stack, create a monitor that detects when key containers in the stack are not running, then runs a docker_compose_action of \"up\" against {{compose_path}}. If recovery fails twice in a row, send a critical webhook so a human takes over."
      },
      {
        label: "Audit existing monitors for gaps",
        prompt: "List all current monitors and audit them: missing severities, no actions configured, cooldowns that are too short or too long, monitors targeting \"all\" instead of specific scopes, and machines with no monitor coverage at all (no CPU, memory, disk, or offline monitor). Output a prioritized fix list."
      },
      {
        label: "Convert noisy alerts into better thresholds",
        prompt: "Review the last 30 days of alerts. Identify monitors that fire frequently and resolve quickly (likely thresholds too tight or duration_seconds too short). For each, recommend a specific threshold/duration adjustment with reasoning, and propose the updated condition JSON. Do not apply changes — show the diff for review."
      },
      {
        label: "Adopt and tune a template",
        prompt: "List the available monitor templates. Pick the most relevant one for {{use_case}}, instantiate it for {{target}}, and tune the thresholds based on the typical workload of those machines. Explain why you chose those values."
      },
      {
        label: "Coverage matrix by company",
        prompt: "Produce a coverage matrix: for every company, every approved machine, show which of {cpu, memory, disk, offline} monitors are configured and which are missing. Highlight machines with zero monitors and propose a baseline monitor pack to apply."
      },
      {
        label: "Quiet a machine going into maintenance",
        prompt: "I am putting {{hostname}} into maintenance for {{hours}} hours. Temporarily disable any monitors that target it (or whose target includes it) and remind me to re-enable them after. List exactly which monitors you are touching before doing so."
      }
    ]
  },

  "packages": {
    title: "Ask your agent to design and deploy packages",
    description: "Packages are reusable scripts you can push to one machine or your whole fleet. The agent can author, audit, migrate, and roll them out — or convert manual runbooks into reusable automation.",
    requiredAbilities: ["Get Machines", "Get Machine Details", "Execute in Terminal", "Open Remote Terminal"],
    extensionName: "machines",
    enableInstructions: "Enable the Machines extension abilities in Settings → Extensions so your agent can author, deploy, and verify packages across your fleet.",
    examples: [
      {
        label: "Author a hardened install package",
        prompt: "Author a cross-platform package that installs and configures the latest stable version of a tool I name. Include OS detection (Windows/Linux/macOS), idempotency checks so re-runs are safe, verification of the install (version check + service running), structured logging, and clean failure handling with a non-zero exit on any unrecoverable error. Explain each section before writing it."
      },
      {
        label: "Convert a runbook into a package",
        prompt: "Here is a manual runbook I follow on machines: <paste runbook>. Turn it into a reusable package script with parameters, idempotent steps, dry-run support, rollback on failure, and detailed logs. Then suggest which machine tags it should be deployed to and a sensible schedule."
      },
      {
        label: "Audit & harden an existing package",
        prompt: "Review the \"{{package_name}}\" package for: hardcoded secrets, missing error handling, non-idempotent operations, unsafe shell quoting, missing OS guards, and overly broad permissions. Produce a diff with concrete fixes and a short risk summary."
      },
      {
        label: "Diagnose recent deployment failures",
        prompt: "Pull the last 14 days of deployment runs for \"{{package_name}}\". Cluster failures by error message and OS, identify the most likely root cause for each cluster, and propose a code change to the package script that would prevent the most common failure."
      },
      {
        label: "Generate a baseline compliance package",
        prompt: "Generate a compliance baseline package that checks (without changing anything) for: firewall enabled, disk encryption on, automatic updates configured, screen lock policy, and antivirus running. Output JSON results so they can be aggregated across the fleet, and write a companion remediation package that fixes any failures."
      },
      {
        label: "Migrate a package across OSes",
        prompt: "Take the existing \"{{package_name}}\" package (currently {{current_os}}) and produce an equivalent version for {{target_os}}. Preserve behavior, parameters, and exit semantics. Highlight every place where OS differences forced a behavior change."
      },
      {
        label: "Plan a staged rollout",
        prompt: "Plan a staged rollout for \"{{package_name}}\": pilot on machines tagged \"canary\" first, then expand by company in waves with success criteria between waves (failure rate, post-deploy health). Generate the deployment schedule and the rollback package to use if a wave fails."
      },
      {
        label: "Document a package for end users",
        prompt: "Write end-user and operator documentation for \"{{package_name}}\": what it does, prerequisites, parameters with examples, what changes on the machine, how to verify success, how to roll back, and known failure modes with fixes."
      }
    ]
  },

  "patches": {
    title: "Let your agent run patch operations",
    description: "Patch the right machines at the right time. Ask the agent to design policies, plan staged rollouts, run vulnerability response, audit failures, or report on compliance.",
    requiredAbilities: ["Get Machines", "Get Machine Details", "Get Machines by Status"],
    extensionName: "machines",
    enableInstructions: "Enable the Machines extension abilities in Settings → Extensions so your agent can plan and report on patching.",
    examples: [
      {
        label: "Fleet-wide patch posture report",
        prompt: "Produce a current patch posture report across all machines: count of missing critical, security, and optional updates per machine, average days behind, machines with reboots pending, and machines that have not reported patch status recently. Highlight the riskiest 10 machines and explain why each made the list."
      },
      {
        label: "Critical / zero-day rapid response",
        prompt: "A critical vulnerability ({{cve_or_kb}}) was just disclosed. Find every machine missing the relevant patch, group them by company and outage window, propose an emergency rollout schedule that respects existing windows, and draft a stakeholder notification email."
      },
      {
        label: "Design a patch policy from scratch",
        prompt: "Design a patch policy for {{company}} based on their workload. Recommend approval delays for critical / security / optional updates, reboot behavior, package categories to auto-approve vs. require review, package holds for known-problem packages, and an appropriate outage window cadence. Explain the reasoning for each setting."
      },
      {
        label: "Audit existing policies for risk",
        prompt: "Review every patch policy in use. Flag policies that auto-approve too aggressively, never reboot, leave critical updates pending too long, or apply to companies whose workload mismatches the policy. For each, recommend a specific change with reasoning."
      },
      {
        label: "Plan and stage a major OS update",
        prompt: "Plan a staged rollout of {{patch_or_update}} across the fleet: pilot ring (machines tagged \"canary\"), broad ring, then production. Define success criteria between rings (failure rate, post-patch health checks, support ticket volume), required outage windows, and a rollback plan if a ring fails."
      },
      {
        label: "Investigate patch failures",
        prompt: "Pull the last 30 days of patch installation failures. Cluster them by error code, OS, package, and policy. Identify the top 3 failure patterns, propose a fix for each (held package, registry workaround, retry strategy, denied list), and recommend which machines need manual intervention."
      },
      {
        label: "Outage window optimization",
        prompt: "Review existing outage windows. Identify machines with no window assigned, windows that overlap critical business hours, windows too short for typical patch cycles, or windows that have not actually been used recently. Propose an optimized schedule."
      },
      {
        label: "Denied patch sanity check",
        prompt: "List every currently denied patch / held package. For each, evaluate whether the original reason still applies, whether a newer fixed version is available, and whether continuing to deny it leaves us exposed. Recommend keep-deny, release, or replace for each."
      },
      {
        label: "Per-customer compliance report",
        prompt: "Generate a per-customer patch compliance report for {{company}}: percentage of machines current on critical and security patches, oldest unpatched vulnerability, machines outside policy, and trend over the last 90 days. Format it as a customer-facing PDF/email summary."
      },
      {
        label: "Reboot coordination",
        prompt: "List every machine with a pending reboot. Group by company and outage window, identify any that have been pending longer than {{days}} days, and propose a coordinated reboot schedule with notifications to end users beforehand."
      }
    ]
  },

  "residents": {
    title: "Let your agent help manage resident care",
    description: "Add residents, record care notes, and search records using natural language commands.",
    requiredAbilities: ["List Residents", "Create Resident", "Update Resident", "Add Resident Note"],
    extensionName: "nursing",
    enableInstructions: "Enable the Nursing abilities in Settings → Extensions → Healthcare so your agent can manage residents for you.",
    examples: [
      {
        label: "Daily shift handoff briefing",
        prompt: "Produce a concise shift handoff briefing for every active resident: significant changes in the last 24 hours, new orders, recent incidents, behavioral notes, and anything the next shift needs to watch for. Group residents by floor or unit."
      },
      {
        label: "Care plan review for a resident",
        prompt: "Pull everything we have on {{residentName}}: diagnoses, allergies, code status, diet, recent vitals, current medications, recent care notes, and family communications. Summarize their current condition, any trends (improving, declining, stable), and flag anything in the care plan that may be out of date or contradicted by recent notes.",
        placeholders: [
          { id: "residentName", label: "Resident", required: true, inputType: "text" }
        ]
      },
      {
        label: "Spot trends across recent notes",
        prompt: "Review the last {{days}} days of care notes for {{residentName}}. Identify trends — increasing pain reports, sleep disturbances, weight changes, behavioral shifts, falls or near-falls, appetite changes — and recommend whether anything warrants escalation to the physician.",
        placeholders: [
          { id: "residentName", label: "Resident", required: true, inputType: "text" },
          { id: "days", label: "Lookback (days)", required: true }
        ]
      },
      {
        label: "Draft a family update",
        prompt: "Draft a warm, plain-language update to the family of {{residentName}} covering how they have been over the last week: mood, activities, meals, any incidents, and care team observations. Avoid clinical jargon. Show me the draft for review before anything is sent.",
        placeholders: [
          { id: "residentName", label: "Resident", required: true, inputType: "text" }
        ]
      },
      {
        label: "Fall & incident risk audit",
        prompt: "Across all active residents, identify those with elevated fall or incident risk based on recent notes, diagnoses, medications known to increase fall risk, and incident history in the last 90 days. Output a prioritized watchlist with the specific risk factors driving each."
      },
      {
        label: "Medication & allergy cross-check",
        prompt: "For {{residentName}}, cross-check current medications against listed allergies, diagnoses, and diet restrictions. Flag any potential conflicts, duplicates, or items that should be reviewed with the physician. This is advisory only — do not change orders.",
        placeholders: [
          { id: "residentName", label: "Resident", required: true, inputType: "text" }
        ]
      },
      {
        label: "Documentation completeness audit",
        prompt: "Audit all active residents for missing or incomplete required documentation: code status, allergies, primary diagnosis, emergency contact, physician info, diet, recent assessment. Output a per-resident gap list sorted by how many fields are missing."
      },
      {
        label: "Census & care-mix snapshot",
        prompt: "Give me a current census snapshot: active residents by floor/unit, primary diagnoses grouped by category, code status distribution, recent admissions and discharges, and average length of stay. Highlight anything notable compared to last month."
      }
    ]
  },

  "chains": {
    title: "Let your agent build and tune Automation Chains",
    description: "Chains run prompts, commands, and other chains in sequence. Ask the agent to design, audit, refactor, or compose them in plain English.",
    requiredAbilities: ["Get Chain List", "Get Chain Details", "Create Automation Chain", "Modify Automation Chain", "Explain Chain"],
    extensionName: "essential_abilities",
    enableInstructions: "Enable the Essential Abilities extension in Settings → Extensions so your agent can author and edit Automation Chains for you.",
    examples: [
      {
        label: "Build a chain from a description",
        prompt: "Design and create a new automation chain that does the following: <describe the multi-step workflow>. Pick the right step type for each part (Prompt, Command, or Chain), wire arguments between steps using {STEP_OUTPUT}, and explain each step before creating it."
      },
      {
        label: "Convert a manual runbook into a chain",
        prompt: "Here is a runbook I follow manually: <paste runbook>. Turn it into an Automation Chain. Use Command steps for the parts an extension can do directly, Prompt steps for the parts that need reasoning or summarization, and chain it all together so a single trigger runs the whole thing."
      },
      {
        label: "Audit and improve an existing chain",
        prompt: "Look at the \"{{chain_name}}\" chain. Identify steps that are redundant, missing error handling, passing arguments that no longer match what the next step expects, or could be parallelized. Propose a concrete cleanup plan and the updated step list."
      },
      {
        label: "Add a step to an existing chain",
        prompt: "In the \"{{chain_name}}\" chain, add a step that {{action}} between step {{step_number}} and the next one. Make sure outputs from the prior step are correctly fed in and downstream steps still work. Show me the diff."
      },
      {
        label: "Explain a chain visually",
        prompt: "Explain the \"{{chain_name}}\" chain to me. Produce a Mermaid diagram and a plain-English walkthrough of what happens at each step, what each step depends on, and what the final output should look like."
      },
      {
        label: "Compose a chain of chains",
        prompt: "Create a master chain that runs these existing chains in sequence: {{chain_a}}, then {{chain_b}}, then {{chain_c}}, passing the output of each into the next. Add a final summarization Prompt step that produces a clean report combining the results."
      },
      {
        label: "Recommend reusable chains for my workflows",
        prompt: "Look at the conversations and tasks I have been running recently. Identify repeating multi-step workflows that would be good candidates for an Automation Chain, and propose a chain (with steps) for each one — strongest candidates first."
      },
      {
        label: "Refactor: extract a sub-chain",
        prompt: "In \"{{chain_name}}\", steps {{start}}-{{end}} look like a self-contained workflow. Extract them into a new chain called \"{{new_chain_name}}\", then replace those steps in the original chain with a single Chain step that calls the new one. Verify argument plumbing still works."
      },
      {
        label: "Migrate a chain across agents",
        prompt: "Copy the \"{{chain_name}}\" chain so it works with agent \"{{target_agent}}\". Identify any steps that depend on commands the new agent does not have enabled, and either swap them for equivalents or call them out so I can enable the missing abilities."
      }
    ]
  },

  "tasks": {
    title: "Let your agent do the scheduling",
    description: "The agent can schedule one-off and recurring follow-ups that run in the background, message you with results, and chain steps together. Ideal for recurring reports, monitored conditions, follow-ups, and routine work.",
    requiredAbilities: ["Schedule Follow-Up Message", "Schedule Recurring Follow-Up", "Get Scheduled Follow-Ups", "Modify Scheduled Follow-Up"],
    extensionName: "essential_abilities",
    enableInstructions: "Enable the Essential Abilities extension in Settings → Extensions so your agent can schedule and manage tasks for you.",
    examples: [
      {
        label: "Recurring report on a schedule",
        prompt: "Every {{frequency}} at {{time}}, run a report covering {{topic}} and message me with the results. Include a short summary at the top, the data table, and any items that need my attention. Schedule it starting tomorrow and continuing until I tell you to stop."
      },
      {
        label: "Smart follow-up after a deadline",
        prompt: "Schedule a follow-up for {{when}} that checks whether {{condition}} has happened. If it has, message me a confirmation summary. If it has not, message me with what you found and propose the next escalation step."
      },
      {
        label: "Recurring health check with auto-remediation",
        prompt: "Every morning at {{time}}, check {{target}} for health issues. If everything is fine, just send me a one-line green status. If anything is unhealthy, run the safe remediation steps you have available and then message me a detailed report."
      },
      {
        label: "Customer follow-up cadence",
        prompt: "For {{customer_or_company}}, schedule a recurring weekly check-in that summarizes new tickets, open tickets, recent escalations, and anything that has been stale for over {{days}} days. Message me the summary every {{day_of_week}} morning."
      },
      {
        label: "Time-boxed monitoring window",
        prompt: "For the next {{hours}} hours, check {{target}} every {{interval_minutes}} minutes. Only message me if something looks wrong — otherwise stay quiet. After the window, send a final summary of everything you observed."
      },
      {
        label: "Dependency-aware task chain",
        prompt: "Schedule a task for {{when}} that does the following in order: 1) verify {{precondition}}, 2) if true, perform {{action}}, 3) report results. If the precondition fails, postpone the task to the next {{retry_window}} and notify me."
      },
      {
        label: "Audit my schedule",
        prompt: "List all my scheduled tasks. Identify duplicates, tasks that no longer make sense given recent changes, recurring tasks that are firing too often or not often enough, and any that have been failing. Recommend specific changes — modify or cancel — for each."
      },
      {
        label: "Reschedule everything in a window",
        prompt: "I will be unavailable from {{start}} to {{end}}. Move every scheduled task that would fire during that window to either before or after, whichever makes more sense for each task. Show me the proposed plan before applying changes."
      },
      {
        label: "Convert a manual routine into a schedule",
        prompt: "Here is something I do manually: <describe routine>. Convert it into a scheduled task with the right frequency, what to check or run, and what to message me with each time. Suggest sensible defaults and ask me to confirm before scheduling."
      },
      {
        label: "Quarterly review reminder",
        prompt: "Schedule a recurring quarterly task on the first Monday of each quarter to compile a review covering {{areas}} for the previous quarter and message me the summary as a starting point for my planning."
      }
    ]
  }
};
