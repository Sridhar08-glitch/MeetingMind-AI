"""MeetingMind AI — shared demo dataset (pure data, no Django imports).

This module is the single source of truth for the demo *script*: the cast, the
projects, and the ~20 meetings with their decisions/actions/risks/etc. It is
imported by two consumers:

  * :mod:`apps.common.demo_media` — turns each meeting's scripted lines into a
    REAL spoken audio (WAV) or video (MP4) file via local TTS + ffmpeg.
  * :mod:`apps.common.demo`      — uploads those real files through the REAL
    processing pipeline (Faster-Whisper → Ollama) to build the demo workspace.

Keeping it import-free (no models, no Django) avoids import cycles between those
two modules and lets media generation run as a standalone step.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

DEMO_EMAIL = "demo@meetingmind.ai"
DEMO_PASSWORD = "DemoPass123!"
DEMO_FIRST = "Demo"
DEMO_LAST = "Evaluator"
WORKSPACE_NAME = "MeetingMind AI Demo"

# ── Cast (a consistent set of people so cross-meeting knowledge/consensus is coherent) ──
CAST = {
    "Alice Chen": "Engineering Lead",
    "Bob Martins": "Backend Engineer",
    "Carol Nwosu": "Product Manager",
    "Dave Okoro": "QA Lead",
    "Erin Walsh": "Product Designer",
    "Frank Li": "Account Executive",
    "Grace Kim": "Customer Success",
    "Henry Adler": "CTO",
    "Priya Rao": "Data Engineer",
    "Sam Turner": "Mobile Engineer",
}
# External participants (for sales / customer interviews)
NORTHWIND = "Jordan Blake (Northwind)"
CONTOSO = "Riley Sen (Contoso)"
FABRIKAM = "Morgan Reed (Fabrikam)"
BETA_USER = "Taylor Brooks (Beta user)"
ENTERPRISE = "Alex Yamada (Zenith Corp)"

PROJECTS = [
    ("Apollo Platform", "Core multi-tenant SaaS platform: auth, data, API gateway, billing."),
    ("Helios CRM", "Customer relationship management product and analytics dashboards."),
    ("Nova Mobile", "Native mobile companion app: onboarding, offline sync, notifications."),
]


@dataclass
class MeetingSpec:
    project: str
    mtype: str  # sprint_planning | standup | sales_call | customer_interview | executive | design_review
    title: str
    days_ago: int
    media: str  # "audio" | "video"
    minutes: int
    participants: list
    intro: str
    topics: list
    decisions: list = field(default_factory=list)      # (text, reason, [participants])
    actions: list = field(default_factory=list)        # (task, owner, priority, due_days, status)
    risks: list = field(default_factory=list)          # (risk, severity, mitigation, status)
    issues: list = field(default_factory=list)         # (title, type, severity, description)
    follow_ups: list = field(default_factory=list)     # (item, owner)
    deadlines: list = field(default_factory=list)      # (item, when)
    chat: list = field(default_factory=list)           # (question, answer, found)
    agenda: list = field(default_factory=list)


def _p(*names):
    return list(names)


# ─────────────────────────── The demo dataset (~20 meetings, 6 types, 3 projects) ───────────────────────────
MEETINGS: list[MeetingSpec] = [
    MeetingSpec(
        "Apollo Platform", "sprint_planning", "Apollo Sprint 24 Planning", 26, "video", 23,
        _p("Carol Nwosu", "Alice Chen", "Bob Martins", "Dave Okoro", "Priya Rao"),
        "Let's plan Sprint 24. The theme is authentication hardening and the new API gateway.",
        ["authentication", "API gateway", "rate limiting", "sprint capacity"],
        decisions=[
            ("Adopt OAuth2 with OIDC for authentication", "Standardises SSO and passed the security review", ["Alice Chen", "Henry Adler"]),
            ("Introduce the API gateway in front of all services", "Centralises rate limiting and auth", ["Carol Nwosu", "Alice Chen"]),
        ],
        actions=[
            ("Implement OAuth2 + OIDC login flow", "Bob Martins", "high", 12, "in_progress"),
            ("Stand up the API gateway skeleton", "Priya Rao", "high", 9, "todo"),
            ("Write rate-limiting integration tests", "Dave Okoro", "medium", 14, "todo"),
            ("Document the auth migration for other teams", "Carol Nwosu", "low", 20, "backlog"),
        ],
        risks=[
            ("Auth token rotation is not yet automated", "high", "Add refresh-token rotation before GA", "open"),
            ("Gateway could become a single point of failure", "medium", "Run two gateway replicas behind a load balancer", "mitigating"),
        ],
        issues=[("Legacy sessions do not expire server-side", "security", "high", "Sessions persist even after logout on old endpoints.")],
        follow_ups=[("Confirm SSO provider list with IT", "Carol Nwosu"), ("Book a load test window", "Priya Rao")],
        deadlines=[("Sprint 24 review", "in 2 weeks"), ("Auth GA readiness", "end of quarter")],
        chat=[
            ("What did we decide about authentication?", "The team decided to adopt OAuth2 with OIDC because it standardises SSO and passed the security review.", True),
            ("Who owns the API gateway work?", "Priya Rao is standing up the API gateway skeleton this sprint.", True),
            ("What is the marketing budget?", "I couldn't find that information in this meeting.", False),
        ],
        agenda=["Review last sprint", "Authentication hardening", "API gateway kickoff", "Capacity & commitments"],
    ),
    MeetingSpec(
        "Apollo Platform", "standup", "Apollo Platform Standup — Monday", 24, "audio", 7,
        _p("Alice Chen", "Bob Martins", "Priya Rao", "Dave Okoro"),
        "Quick standup — blockers first, then what everyone is picking up today.",
        ["OAuth2 progress", "gateway skeleton", "CI flakiness"],
        actions=[
            ("Fix the flaky auth integration test in CI", "Dave Okoro", "medium", 2, "in_progress"),
            ("Wire the gateway health check endpoint", "Priya Rao", "medium", 3, "todo"),
        ],
        risks=[("CI flakiness is slowing merges", "medium", "Quarantine the flaky test and track it", "mitigating")],
        follow_ups=[("Pair on the token refresh bug after standup", "Bob Martins")],
        chat=[("Any blockers today?", "Yes — CI flakiness on the auth integration test is slowing merges; Dave is quarantining it.", True)],
        agenda=["Blockers", "In progress", "Today's plan"],
    ),
    MeetingSpec(
        "Apollo Platform", "design_review", "Apollo API Gateway Design Review", 19, "video", 27,
        _p("Alice Chen", "Priya Rao", "Bob Martins", "Henry Adler", "Dave Okoro"),
        "Design review for the API gateway: routing, auth handoff, rate limiting and observability.",
        ["gateway routing", "rate limiting", "observability", "failover", "backpressure"],
        decisions=[
            ("Use token-bucket rate limiting at the gateway", "Predictable limits and simple to reason about", ["Priya Rao", "Alice Chen"]),
            ("Emit structured access logs from the gateway", "Needed for auditing and debugging", ["Alice Chen", "Henry Adler"]),
        ],
        actions=[
            ("Prototype token-bucket limiter with Redis", "Priya Rao", "high", 10, "in_progress"),
            ("Define the gateway → service auth contract", "Bob Martins", "high", 8, "todo"),
            ("Add gateway dashboards and alerts", "Dave Okoro", "medium", 16, "backlog"),
        ],
        risks=[
            ("Redis outage would disable rate limiting", "high", "Fail open with a local fallback limiter", "open"),
            ("Backpressure under load is untested", "medium", "Schedule a soak test", "open"),
        ],
        issues=[("No distributed tracing across services yet", "tech_debt", "medium", "Hard to follow a request across the gateway and services.")],
        follow_ups=[("Compare token-bucket vs leaky-bucket numbers", "Priya Rao")],
        deadlines=[("Gateway prototype demo", "in 10 days")],
        chat=[
            ("Which rate-limiting algorithm did we pick?", "Token-bucket rate limiting at the gateway, because it gives predictable limits and is simple to reason about.", True),
            ("What happens if Redis goes down?", "It's an open risk; the mitigation is to fail open with a local fallback limiter.", True),
        ],
        agenda=["Routing model", "Auth handoff", "Rate limiting", "Observability", "Failure modes"],
    ),
    MeetingSpec(
        "Apollo Platform", "executive", "Apollo Q3 Executive Review", 12, "video", 20,
        _p("Henry Adler", "Carol Nwosu", "Alice Chen", "Frank Li"),
        "Quarterly executive review of Apollo: delivery health, risks, and Q4 priorities.",
        ["delivery health", "auth GA", "hiring", "Q4 roadmap"],
        decisions=[
            ("Prioritise auth GA over new reporting features in Q4", "Security and enterprise deals depend on it", ["Henry Adler", "Carol Nwosu"]),
        ],
        actions=[
            ("Draft the Q4 roadmap one-pager", "Carol Nwosu", "high", 7, "in_progress"),
            ("Open a backend engineer requisition", "Henry Adler", "medium", 14, "todo"),
        ],
        risks=[
            ("Auth GA slipping would delay two enterprise deals", "critical", "Weekly GA readiness check-in", "mitigating"),
            ("Backend team is at capacity", "high", "Hire or reprioritise scope", "open"),
        ],
        follow_ups=[("Share the enterprise pipeline with engineering", "Frank Li")],
        deadlines=[("Q4 roadmap sign-off", "in 1 week"), ("Auth GA", "end of quarter")],
        chat=[
            ("What is the top priority for Q4?", "Prioritising auth GA over new reporting features, because security and enterprise deals depend on it.", True),
            ("What is the biggest risk right now?", "Auth GA slipping — it's rated critical because it would delay two enterprise deals.", True),
        ],
        agenda=["Delivery health", "Risks", "Hiring", "Q4 priorities"],
    ),
    MeetingSpec(
        "Apollo Platform", "standup", "Apollo Platform Standup — Wednesday", 22, "audio", 6,
        _p("Alice Chen", "Bob Martins", "Priya Rao"),
        "Midweek standup. Auth flow is close; gateway prototype is progressing.",
        ["OAuth2 flow", "gateway prototype"],
        actions=[("Finish the OAuth2 callback handler", "Bob Martins", "high", 1, "in_progress")],
        follow_ups=[("Demo the gateway prototype Friday", "Priya Rao")],
        chat=[("Is the OAuth2 flow done?", "Almost — Bob is finishing the OAuth2 callback handler today.", True)],
        agenda=["Blockers", "Progress"],
    ),
    MeetingSpec(
        "Apollo Platform", "design_review", "Apollo Billing Service Design Review", 8, "video", 20,
        _p("Alice Chen", "Bob Martins", "Carol Nwosu", "Priya Rao"),
        "Design review for the metered billing service: usage events, invoicing, idempotency.",
        ["metered billing", "usage events", "idempotency", "invoicing"],
        decisions=[("Store usage events append-only with idempotency keys", "Prevents double-billing on retries", ["Bob Martins", "Alice Chen"])],
        actions=[
            ("Design the usage-event schema", "Bob Martins", "high", 9, "todo"),
            ("Prototype invoice generation", "Priya Rao", "medium", 15, "backlog"),
        ],
        risks=[("Double-billing if idempotency is missed", "critical", "Enforce idempotency keys at the API edge", "open")],
        issues=[("No reconciliation report between usage and invoices", "problem", "medium", "Finance cannot verify invoice totals against raw usage.")],
        follow_ups=[("Check tax requirements with finance", "Carol Nwosu")],
        deadlines=[("Billing schema sign-off", "in 9 days")],
        chat=[("How do we avoid double-billing?", "Usage events are stored append-only with idempotency keys, enforced at the API edge.", True)],
        agenda=["Usage events", "Idempotency", "Invoicing", "Reconciliation"],
    ),
    MeetingSpec(
        "Helios CRM", "sales_call", "Helios CRM — Northwind Traders Sales Call", 21, "video", 28,
        _p("Frank Li", "Carol Nwosu", NORTHWIND),
        "Sales call with Northwind Traders to walk through Helios CRM and scope a pilot.",
        ["pilot scope", "data import", "pricing", "security review", "timeline"],
        decisions=[("Run a 30-day Helios pilot with Northwind", "Lets both sides validate fit before a full rollout", ["Frank Li", NORTHWIND])],
        actions=[
            ("Send Northwind the pilot agreement and pricing", "Frank Li", "high", 3, "in_progress"),
            ("Prepare a sample data-import template", "Carol Nwosu", "medium", 5, "todo"),
            ("Schedule the security questionnaire review", "Frank Li", "medium", 7, "todo"),
        ],
        risks=[
            ("Northwind's data is in a legacy format", "medium", "Provide an import template and a mapping call", "mitigating"),
            ("Procurement could delay the pilot start", "medium", "Start the security review in parallel", "open"),
        ],
        follow_ups=[("Loop in Northwind's IT for the security review", "Frank Li"), ("Confirm the pilot success metrics", CONTOSO)],
        deadlines=[("Pilot agreement sent", "in 3 days"), ("Pilot kickoff", "in 3 weeks")],
        chat=[
            ("What did the customer agree to?", "Northwind agreed to run a 30-day Helios pilot so both sides can validate fit before a full rollout.", True),
            ("What is blocking the pilot?", "Two things: Northwind's data is in a legacy format, and procurement could delay the start.", True),
        ],
        agenda=["Intros", "Product walkthrough", "Pilot scope", "Security & pricing", "Next steps"],
    ),
    MeetingSpec(
        "Helios CRM", "customer_interview", "Helios CRM — Contoso Discovery Interview", 18, "video", 31,
        _p("Carol Nwosu", "Grace Kim", CONTOSO),
        "Discovery interview with Contoso about their CRM pain points and reporting needs.",
        ["reporting", "pipeline visibility", "integrations", "onboarding pain"],
        decisions=[("Prioritise a pipeline dashboard for Contoso's use case", "It was their most-repeated pain point", ["Carol Nwosu", "Grace Kim"])],
        actions=[
            ("Turn Contoso's reporting needs into user stories", "Carol Nwosu", "high", 6, "todo"),
            ("Share the integrations roadmap with Contoso", "Grace Kim", "medium", 8, "todo"),
        ],
        risks=[("Contoso may churn without better reporting", "high", "Fast-track the pipeline dashboard", "open")],
        issues=[
            ("Onboarding takes Contoso's team over a week", "customer", "high", "New reps struggle to import and map their data."),
            ("No Salesforce import path", "customer", "medium", "Contoso can't migrate historical data easily."),
        ],
        follow_ups=[("Send Contoso the beta of the dashboard when ready", "Grace Kim")],
        deadlines=[("Dashboard user stories", "in 6 days")],
        chat=[
            ("What is Contoso's biggest pain point?", "Pipeline visibility — reporting was their most-repeated pain point, so we're prioritising a pipeline dashboard.", True),
            ("Why might Contoso churn?", "There's a high risk they churn without better reporting; the mitigation is to fast-track the pipeline dashboard.", True),
        ],
        agenda=["Current workflow", "Pain points", "Reporting needs", "Integrations", "Wrap-up"],
    ),
    MeetingSpec(
        "Helios CRM", "sprint_planning", "Helios Sprint 12 Planning", 16, "audio", 17,
        _p("Carol Nwosu", "Bob Martins", "Erin Walsh", "Dave Okoro"),
        "Planning Sprint 12 for Helios: the pipeline dashboard and a data-import wizard.",
        ["pipeline dashboard", "import wizard", "reporting API"],
        decisions=[("Ship the pipeline dashboard behind a feature flag", "Lets us pilot it with Contoso safely", ["Carol Nwosu", "Erin Walsh"])],
        actions=[
            ("Build the pipeline dashboard UI", "Erin Walsh", "high", 12, "in_progress"),
            ("Expose the reporting aggregation API", "Bob Martins", "high", 11, "todo"),
            ("Design the CSV import wizard", "Erin Walsh", "medium", 14, "todo"),
            ("Add dashboard regression tests", "Dave Okoro", "medium", 16, "backlog"),
        ],
        risks=[("Reporting queries may be slow at scale", "medium", "Pre-aggregate and index the reporting tables", "mitigating")],
        follow_ups=[("Validate dashboard metrics with Grace", "Carol Nwosu")],
        deadlines=[("Sprint 12 review", "in 2 weeks")],
        chat=[("How are we shipping the dashboard safely?", "Behind a feature flag, so we can pilot it with Contoso before a wider release.", True)],
        agenda=["Sprint goal", "Dashboard", "Import wizard", "Testing"],
    ),
    MeetingSpec(
        "Helios CRM", "design_review", "Helios Dashboard Redesign Review", 14, "video", 24,
        _p("Erin Walsh", "Carol Nwosu", "Alice Chen", "Grace Kim"),
        "Reviewing the redesigned Helios dashboard: layout, drill-downs, and accessibility.",
        ["dashboard layout", "drill-down", "accessibility", "empty states"],
        decisions=[
            ("Adopt a card-based dashboard layout", "Scales better across screen sizes", ["Erin Walsh", "Carol Nwosu"]),
            ("Meet WCAG AA contrast on all charts", "Required for enterprise customers", ["Erin Walsh", "Alice Chen"]),
        ],
        actions=[
            ("Finalise the dashboard card components", "Erin Walsh", "high", 9, "in_progress"),
            ("Add keyboard navigation to charts", "Alice Chen", "medium", 13, "todo"),
        ],
        risks=[("Redesign could confuse existing users", "medium", "Ship with an opt-in preview and a tour", "mitigating")],
        issues=[("Charts have no empty-state design", "problem", "low", "New workspaces see blank charts with no guidance.")],
        follow_ups=[("Usability test the new layout with two customers", "Grace Kim")],
        deadlines=[("Dashboard redesign GA", "in 3 weeks")],
        chat=[("What layout did we choose?", "A card-based dashboard layout, because it scales better across screen sizes.", True)],
        agenda=["Layout", "Drill-downs", "Accessibility", "Migration"],
    ),
    MeetingSpec(
        "Helios CRM", "standup", "Helios CRM Standup", 13, "audio", 6,
        _p("Carol Nwosu", "Erin Walsh", "Bob Martins"),
        "Standup — dashboard UI and reporting API status.",
        ["dashboard UI", "reporting API"],
        actions=[("Hook the dashboard up to the reporting API", "Bob Martins", "high", 2, "in_progress")],
        risks=[("Reporting API contract is still changing", "low", "Freeze the contract by end of week", "open")],
        chat=[("What's in progress?", "Bob is hooking the dashboard up to the reporting API.", True)],
        agenda=["Blockers", "Progress"],
    ),
    MeetingSpec(
        "Helios CRM", "executive", "Helios Go-to-Market Exec Sync", 6, "video", 19,
        _p("Henry Adler", "Frank Li", "Carol Nwosu", "Grace Kim"),
        "Go-to-market sync for Helios: pilots, pricing, and the launch date.",
        ["pilots", "pricing", "launch date", "customer health"],
        decisions=[
            ("Target a Helios GA launch next quarter", "Two pilots convert around then", ["Henry Adler", "Frank Li"]),
            ("Introduce a mid-tier pricing plan", "Fills the gap between starter and enterprise", ["Frank Li", "Carol Nwosu"]),
        ],
        actions=[
            ("Finalise the mid-tier pricing", "Frank Li", "high", 10, "todo"),
            ("Build the GA launch checklist", "Carol Nwosu", "medium", 12, "todo"),
        ],
        risks=[("Only one of two pilots is fully engaged", "high", "Assign a dedicated CSM to the quieter pilot", "mitigating")],
        follow_ups=[("Share pilot health weekly", "Grace Kim")],
        deadlines=[("Pricing finalised", "in 10 days"), ("Helios GA", "next quarter")],
        chat=[("When are we launching Helios?", "GA is targeted for next quarter, timed to when the two pilots convert.", True)],
        agenda=["Pilot status", "Pricing", "Launch plan"],
    ),
    MeetingSpec(
        "Nova Mobile", "sprint_planning", "Nova Mobile Sprint 8 Planning", 20, "audio", 16,
        _p("Carol Nwosu", "Sam Turner", "Erin Walsh", "Dave Okoro"),
        "Planning Sprint 8 for Nova Mobile: offline sync and push notifications.",
        ["offline sync", "push notifications", "battery usage"],
        decisions=[("Use a local-first sync with conflict resolution", "Keeps the app usable offline", ["Sam Turner", "Carol Nwosu"])],
        actions=[
            ("Implement the offline sync queue", "Sam Turner", "high", 12, "in_progress"),
            ("Add push notification opt-in flow", "Erin Walsh", "medium", 14, "todo"),
            ("Measure battery impact of background sync", "Dave Okoro", "medium", 15, "backlog"),
        ],
        risks=[
            ("Sync conflicts could lose user edits", "high", "Last-write-wins with a visible conflict log", "open"),
            ("Background sync may drain battery", "medium", "Batch syncs and respect low-power mode", "mitigating"),
        ],
        follow_ups=[("Decide the conflict-resolution UX", "Erin Walsh")],
        deadlines=[("Sprint 8 review", "in 2 weeks")],
        chat=[("How does offline mode work?", "A local-first sync with conflict resolution, so the app stays usable offline.", True)],
        agenda=["Sprint goal", "Offline sync", "Notifications", "Performance"],
    ),
    MeetingSpec(
        "Nova Mobile", "standup", "Nova Mobile Standup", 17, "audio", 7,
        _p("Sam Turner", "Erin Walsh", "Dave Okoro"),
        "Standup — offline sync queue progress and a notifications blocker.",
        ["offline sync", "notifications blocker"],
        actions=[("Investigate iOS push token registration failure", "Sam Turner", "high", 1, "in_progress")],
        risks=[("iOS push registration is failing intermittently", "medium", "Add retry with backoff on token registration", "open")],
        follow_ups=[("Pair on the push token bug", "Erin Walsh")],
        chat=[("Any blockers?", "Yes — iOS push token registration is failing intermittently; Sam is adding retry with backoff.", True)],
        agenda=["Blockers", "Progress"],
    ),
    MeetingSpec(
        "Nova Mobile", "design_review", "Nova Onboarding Flow Design Review", 15, "video", 21,
        _p("Erin Walsh", "Carol Nwosu", "Sam Turner", "Grace Kim"),
        "Design review of the Nova onboarding flow to reduce first-run drop-off.",
        ["onboarding steps", "permissions priming", "drop-off", "empty states"],
        decisions=[("Cut onboarding from five steps to three", "Fewer steps reduce drop-off", ["Erin Walsh", "Carol Nwosu"])],
        actions=[
            ("Redesign onboarding step two", "Erin Walsh", "high", 8, "in_progress"),
            ("Add a permissions priming screen", "Sam Turner", "medium", 12, "todo"),
        ],
        risks=[("Drop-off is rising on the current step two", "high", "Ship the three-step flow and measure", "mitigating")],
        issues=[("No analytics on onboarding step completion", "problem", "medium", "We can't see exactly where users drop off.")],
        follow_ups=[("Add funnel analytics to onboarding", "Sam Turner")],
        deadlines=[("New onboarding live", "in 2 weeks")],
        chat=[
            ("How are we improving onboarding?", "By cutting onboarding from five steps to three, since fewer steps reduce drop-off.", True),
            ("Where are users dropping off?", "Mostly on step two — drop-off is rising there, which is why it's being redesigned.", True),
        ],
        agenda=["Current funnel", "New flow", "Permissions", "Analytics"],
    ),
    MeetingSpec(
        "Nova Mobile", "customer_interview", "Nova Mobile — Beta User Interview", 11, "audio", 23,
        _p("Grace Kim", "Erin Walsh", BETA_USER),
        "Interview with a Nova beta user about their day-to-day usage and frustrations.",
        ["daily usage", "offline reliability", "notifications", "feature requests"],
        decisions=[("Add a manual 'sync now' control", "Beta users want visible control over syncing", ["Erin Walsh", "Grace Kim"])],
        actions=[
            ("Add a manual sync-now button", "Sam Turner", "medium", 10, "todo"),
            ("Summarise beta feedback for the team", "Grace Kim", "low", 4, "todo"),
        ],
        risks=[("Beta users distrust background sync", "medium", "Show sync status and a manual control", "mitigating")],
        issues=[("Notifications arrive late on Android", "bug", "high", "Push notifications can be delayed by several minutes on Android.")],
        follow_ups=[("Recruit two more beta interviewees", "Grace Kim")],
        chat=[("What did the beta user want most?", "A manual 'sync now' control — beta users want visible control over syncing.", True)],
        agenda=["Usage", "Reliability", "Requests"],
    ),
    MeetingSpec(
        "Nova Mobile", "sales_call", "Nova Mobile — Enterprise Pilot Sales Call", 9, "video", 25,
        _p("Frank Li", "Henry Adler", ENTERPRISE),
        "Enterprise sales call to scope a Nova Mobile pilot with device management needs.",
        ["MDM support", "SSO", "pilot scope", "security"],
        decisions=[("Scope a Nova enterprise pilot with SSO", "Enterprise requires SSO before rollout", ["Frank Li", ENTERPRISE])],
        actions=[
            ("Confirm MDM compatibility for Nova", "Sam Turner", "high", 9, "todo"),
            ("Send the enterprise security overview", "Frank Li", "high", 4, "in_progress"),
        ],
        risks=[("Nova lacks MDM support today", "high", "Scope MDM as a pilot prerequisite", "open")],
        follow_ups=[("Align SSO approach with the Apollo auth work", "Henry Adler")],
        deadlines=[("Security overview sent", "in 4 days")],
        chat=[
            ("What does the enterprise customer need?", "SSO before rollout, plus MDM support — so we're scoping a pilot with SSO.", True),
            ("What's the main gap for this deal?", "Nova lacks MDM support today; it's an open risk scoped as a pilot prerequisite.", True),
        ],
        agenda=["Requirements", "Security", "Pilot scope", "Next steps"],
    ),
    MeetingSpec(
        "Nova Mobile", "executive", "Nova Launch Readiness Exec Review", 4, "video", 18,
        _p("Henry Adler", "Carol Nwosu", "Sam Turner", "Dave Okoro"),
        "Executive review of Nova launch readiness: quality bar, blockers and the go/no-go.",
        ["launch readiness", "crash rate", "blockers", "go/no-go"],
        decisions=[("Hold the Nova launch until the crash rate is under 1%", "Quality bar for a public launch", ["Henry Adler", "Dave Okoro"])],
        actions=[
            ("Drive the crash rate below 1%", "Sam Turner", "critical", 10, "in_progress"),
            ("Prepare the launch communications", "Carol Nwosu", "medium", 12, "todo"),
        ],
        risks=[
            ("Crash rate is above the launch bar", "critical", "Fix the top three crashes before launch", "mitigating"),
            ("App store review could add days", "medium", "Submit the build a week early", "open"),
        ],
        follow_ups=[("Daily crash triage until launch", "Dave Okoro")],
        deadlines=[("Crash rate under 1%", "in 10 days"), ("Nova public launch", "in 3 weeks")],
        chat=[
            ("Are we ready to launch Nova?", "Not yet — the launch is held until the crash rate is under 1%, which is the quality bar.", True),
            ("What's the critical blocker?", "The crash rate is above the launch bar; the team is fixing the top three crashes.", True),
        ],
        agenda=["Quality bar", "Blockers", "Timeline", "Go/no-go"],
    ),
    MeetingSpec(
        "Helios CRM", "customer_interview", "Helios CRM — Fabrikam Feedback Session", 7, "audio", 22,
        _p("Grace Kim", "Carol Nwosu", FABRIKAM),
        "Feedback session with Fabrikam after their first month on Helios CRM.",
        ["adoption", "reporting", "support experience", "renewal"],
        decisions=[("Assign a dedicated CSM to Fabrikam", "Improves adoption ahead of renewal", ["Grace Kim", "Carol Nwosu"])],
        actions=[
            ("Set up a monthly Fabrikam success review", "Grace Kim", "medium", 6, "todo"),
            ("Fix Fabrikam's duplicate-contact issue", "Bob Martins", "high", 8, "todo"),
        ],
        risks=[("Fabrikam renewal is at risk without better adoption", "high", "Dedicated CSM and a success plan", "mitigating")],
        issues=[("Duplicate contacts on import", "bug", "medium", "Fabrikam's import created duplicate contact records.")],
        follow_ups=[("Send Fabrikam a tailored onboarding guide", "Grace Kim")],
        deadlines=[("Fabrikam success review scheduled", "in 6 days")],
        chat=[("How do we protect the Fabrikam renewal?", "By assigning a dedicated CSM to improve adoption ahead of renewal.", True)],
        agenda=["First-month recap", "What's working", "Pain points", "Plan"],
    ),
    MeetingSpec(
        "Apollo Platform", "standup", "Apollo Platform Standup — Friday", 20, "audio", 6,
        _p("Alice Chen", "Priya Rao", "Dave Okoro"),
        "End-of-week standup and a quick gateway prototype demo recap.",
        ["gateway prototype demo", "rate limiter"],
        actions=[("Write up the gateway prototype results", "Priya Rao", "low", 3, "todo")],
        follow_ups=[("Plan the soak test for next week", "Dave Okoro")],
        chat=[("How did the prototype demo go?", "Well — the token-bucket rate limiter worked; Priya is writing up the results.", True)],
        agenda=["Demo recap", "Next week"],
    ),
]


# ─────────────────────────── voices (local Windows SAPI) ───────────────────────────
# Only two SAPI voices exist on the box (Hazel en-GB, Zira en-US); we vary the
# speaking rate per speaker so a listener can still tell people apart. Whisper
# does not diarize, so this is purely for a pleasant, human-sounding recording.
_VOICE_PALETTE = [
    ("Microsoft Hazel Desktop", 0),
    ("Microsoft Zira Desktop", 1),
    ("Microsoft Hazel Desktop", 3),
    ("Microsoft Zira Desktop", -2),
    ("Microsoft Hazel Desktop", -3),
    ("Microsoft Zira Desktop", 4),
    ("Microsoft Hazel Desktop", 2),
]


def speaker_voices(spec: MeetingSpec) -> dict:
    """Deterministically map each distinct speaker in a meeting to (voice, rate)."""
    mapping: dict = {}
    for i, name in enumerate(spec.participants):
        mapping[name] = _VOICE_PALETTE[i % len(_VOICE_PALETTE)]
    return mapping


def _first_name(name: str) -> str:
    return name.split("(")[0].strip().split()[0]


def _lower_first(text: str) -> str:
    return text[:1].lower() + text[1:] if text else text


def sanitize_tts(text: str) -> str:
    """Reduce text to plain ASCII the SAPI engine and JSON round-trip handle well."""
    repl = {
        "—": "-", "–": "-", "’": "'", "‘": "'", "“": '"', "”": '"', "…": "...",
        "%": " percent", "&": " and ", "/": " ", "→": " to ",
    }
    for k, v in repl.items():
        text = text.replace(k, v)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def build_script_lines(spec: MeetingSpec) -> list:
    """Turn a MeetingSpec into a concise, coherent list of (speaker, text) lines.

    This is the spoken script that gets synthesized to audio. It deliberately
    includes the intro, agenda, topics, decisions (with reasoning), action-item
    hand-offs, risks and follow-ups — so the REAL transcript that Whisper
    produces contains genuine, extractable content for Ollama to analyse. It
    omits the "filler" padding the old fabricated seeder used, keeping each
    recording to roughly 1.5–3 minutes so a full 20-meeting run stays practical.
    """
    fac = spec.participants[0]
    others = spec.participants[1:] or [fac]
    lines: list = []

    openers = {
        "sprint_planning": "Thanks everyone for joining sprint planning.",
        "standup": "Morning all, let's keep this standup quick.",
        "sales_call": "Thanks for making the time today.",
        "customer_interview": "Thanks for taking part in this session; there are no wrong answers.",
        "executive": "Let's get into the review and keep to the agenda.",
        "design_review": "Thanks for coming to the design review.",
    }
    closers = {
        "sprint_planning": "Okay, that's the sprint. Owners are clear, thanks everyone.",
        "standup": "Great, that's it. Unblock each other after this.",
        "sales_call": "This was great. I'll follow up with the next steps.",
        "customer_interview": "This is incredibly helpful, thank you. We'll follow up.",
        "executive": "Good. Decisions and owners are captured, thanks.",
        "design_review": "Thanks for the feedback. I'll fold it in.",
    }

    lines.append((fac, openers[spec.mtype]))
    lines.append((fac, spec.intro))
    if spec.agenda:
        lines.append((fac, "On the agenda today: " + ", ".join(spec.agenda) + "."))

    for i, topic in enumerate(spec.topics[:3]):
        sp = others[i % len(others)]
        lines.append((sp, f"Let's talk about {topic}."))

    for text, reason, who in spec.decisions:
        proposer = who[0] if who and who[0] in spec.participants else fac
        lines.append((proposer, f"I propose we {_lower_first(text)}."))
        lines.append((proposer, f"The reasoning is that {_lower_first(reason)}."))
        lines.append((fac, f"Okay, decision made: {text}."))

    for task, owner, prio, _due, _st in spec.actions:
        owner_sp = owner if owner in spec.participants else fac
        lines.append((fac, f"{_first_name(owner_sp)}, can you take this action item: {_lower_first(task)}?"))
        reply = "Yes, I'll own that and treat it as a priority." if prio in ("high", "critical") else "Yes, I'll own that."
        lines.append((owner_sp, reply))

    for risk, sev, mit, _st in spec.risks:
        raiser = others[len(lines) % len(others)]
        lines.append((raiser, f"One risk to flag: {_lower_first(risk)}."))
        lines.append((fac, f"That's {sev} severity. The mitigation is to {_lower_first(mit)}."))

    for item, owner in spec.follow_ups:
        owner_sp = owner if owner in spec.participants else fac
        lines.append((owner_sp, f"A follow-up for me: {_lower_first(item)}."))

    lines.append((fac, closers[spec.mtype]))

    return [(sp, sanitize_tts(text)) for sp, text in lines]


def slug(title: str) -> str:
    s = title.lower()
    s = s.replace("—", "-").replace("–", "-")
    s = re.sub(r"[^a-z0-9]+", "_", s)
    return s.strip("_")


def media_filename(index: int, spec: MeetingSpec) -> str:
    ext = "mp4" if spec.media == "video" else "wav"
    return f"{index + 1:02d}_{slug(spec.title)}.{ext}"
