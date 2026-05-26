# B2B CRM — User Guide

> **Who this is for:** A founder or sales rep doing their own outreach who has the system running and wants a practical day-to-day operations manual.

---

## Quick Reference Card

| Item | Detail |
|------|--------|
| **Frontend URL** | `http://localhost:8501` |
| **Backend API** | `http://localhost:8000` (not for daily use — backend only) |
| **📊 Pipeline** | Daily outreach dashboard — your home screen |
| **🔍 Lead Detail** | Full profile, AI hook, email draft, activity log for one lead |
| **⚡ Sourcing** | Trigger sourcing runs, score unscored leads, monitor data health |
| **📈 Analytics** | Read-only charts — pipeline stage distribution and tier breakdown |
| **⚙️ Settings** | API key status, ICP configuration, pipeline stage reference |
| **Identified** | Sourced but no email, no outreach yet |
| **Enriched** | Verified email found |
| **Contacted** | First outreach logged |
| **Engaged** | Lead has replied positively |
| **Most important daily action** | Check **Tier A Uncontacted** count in sidebar — if >0, open those leads first |

**Streamlit keyboard tips:**

| Shortcut | What it does |
|----------|-------------|
| `Enter` inside a form | Submits the form (same as clicking the submit button) |
| `Ctrl+R` / `Cmd+R` | Reloads the page (clears all filters and state) |
| Arrow keys on a table | Navigate selected rows |

---

## Part 1 — First-Time Setup Checklist

Run through this once before your first real outreach. Skip nothing.

### 1. Verify API connections on the Settings page

Open **⚙️ Settings → Section 1: API Key Status**. You will see a banner showing the active lead provider and coloured dots (🟢/🔴) for each API.

**What ✅ looks like:** The active provider banner shows your provider as `PDL` or `APOLLO` with a 🟢 dot, plus 🟢 dots for Hunter and Anthropic. The **Config status** under each provider reads `✅ Configured`.

**What ⚠️ means:** A missing key. Go to your `.env` file, add the missing variable, and run `docker compose restart backend`. Refresh the Settings page — the dot should turn 🟢.

**Critical:** If Anthropic is ⚠️, scoring will not work at all. Every other page depends on it.

### 2. Calibrate the ICP prompt before trusting any scores

Open **⚙️ Settings → Section 2: ICP Configuration**. Check that your target job titles, locations, and employee range are set. Then expand **View full prompt** under "ICP Scoring Prompt" and read it carefully.

The prompt at `backend/prompts/icp_v1.md` is what Claude uses to score every lead. If it doesn't match your actual buyer, every score it produces is wrong — regardless of how green the UI looks.

**Good:** The prompt clearly states your buyer persona, the problem you solve, and concrete disqualifiers (e.g., "companies below 50 employees are too small").

**Not good:** The template text is unchanged, or the prompt describes a buyer type you no longer target.

### 3. Run the first sourcing batch

Go to **⚡ Sourcing → Section 1: Run a Sourcing Job**. Expand "Current ICP Settings" to confirm your titles and locations are loaded. Leave the pages slider at **1** for your first run. Click **🚀 Start Sourcing Run**.

**What to expect on PDL free tier:** 15–25 new leads per page, depending on filter specificity. A narrow title list (e.g., "CTO" only in one country) may return fewer. A run completing with `0 new leads` means either the filters are too specific or your PDL credits are exhausted — check Section 4 (Data Health) and the Settings page.

### 4. Score your first batch and verify the results match your mental model

After sourcing completes, go to **⚡ Sourcing → Section 3: Score Management**. Click **🤖 Score Unscored** with the default limit of 50. Wait for it to complete (typically 30–90 seconds for 25 leads).

When done, look at the Tier Distribution donut chart. A realistic first-pass distribution for a well-calibrated ICP is roughly **10–20% Tier A, 20–30% Tier B, 30–40% Tier C, 10–20% Tier D**. If every lead is Tier D or every lead is Tier A, the prompt needs work — see Part 5 for how to fix it.

Next, open 5–6 Tier A leads in **🔍 Lead Detail** and read the ICP Reasoning. If the reasoning doesn't match why _you_ would want to talk to this person, the prompt is off.

### 5. Get at least 5 Tier A leads with verified emails before sending anything

On the **📊 Pipeline** page, filter by Tier A. For each Tier A lead without a ✅ in the Email column, click **🔬 Enrich Email** in the action panel. If enrichment fails (Hunter and PDL both draw a blank), move on — don't send to an unverified address.

**Do not begin outreach until you have at least 5 Tier A leads with verified emails.** Sending to unverified addresses burns your domain reputation and produces no signal. Quality beats velocity here.

---

## Part 2 — The Four Pages Explained

### 1. Pipeline — Your Daily Outreach Screen

**What it's for:** A live, filterable view of every lead in the pipeline with one-click actions for the most common moves.

**When to use it:** Open this every morning as your first action. Keep it open during outreach hours.

#### Step-by-step walkthrough

**Sidebar (left panel)**

The sidebar shows four live metrics that update every 30 seconds:
- **Total Leads** — every lead in the database
- **Tier A** — leads scored 80–100
- **Uncontacted A** — Tier A leads still in `identified` or `enriched` status (your primary daily target)
- **Overdue** — leads where the `Next Due` date has passed and they are not yet closed/archived

Below the metrics are filter controls:
- **Status** multiselect — filter to one or more pipeline stages
- **Tier** multiselect — filter to A, B, C, or D
- **Search name / company** — partial text match on name or company name
- **🗑 Clear Filters** — resets all filters and stage card selections

**Quick action row (top of main area)**

Three buttons before the pipeline grid:
- **🚀 Run Sourcing (1 page)** — triggers a single-page sourcing run using your ICP defaults; useful when you want a fast top-up without opening the Sourcing page
- **🤖 Score Unscored (50)** — scores up to 50 unscored leads with Claude; use this after a sourcing run
- **📊 Refresh** — clears the 30-second cache and reloads all data immediately

**Pipeline stage cards**

Below the quick actions is a row of clickable stage cards (Identified, Enriched, Contacted, …). Each card shows:
- The total count for that stage
- A 🔥 count of Tier A leads in that stage (shown for Identified and Enriched only)
- A ⚠️ prefix on the label if any lead in that stage has an overdue follow-up

Click a card to filter the table to that stage. Click it again to deselect.

**Lead table**

The table shows up to 200 leads with these columns:
- **ID** — internal database ID; use this to jump to Lead Detail
- **Name**, **Title**, **Company**, **Industry**, **Employees** — from sourcing data
- **Tier** — A (green), B (blue), C (grey), D (red)
- **Score** — 0–100 ICP score
- **Status** — current pipeline stage
- **Last Contacted** — date of most recent `email_sent` activity
- **Next Due** — date set as `next_action_due`
- **Email** — ✅ if verified, ❌ if email exists but unverified, blank if none
- **Hook** — 📝 if a personalized hook has been generated

Expand the **Tier legend** below the count line to see what each tier means and the recommended action.

**Clicking a row**

Click any row to open the action panel below the table. The action panel shows the lead's name, tier, company, status, and score in a header line, then seven action buttons:

| Button | What it does |
|--------|-------------|
| **✉️ Mark Contacted** | Asks for confirmation, then sets status → `contacted`, records `last_contacted_at` = now, sets `next_action_due` = 7 days from now, and logs an `email_sent` activity |
| **📞 Log Call** | Opens an inline notes form; on submit, logs a `call` activity with your notes |
| **✅ Move to Qualified** | Immediately sets status → `qualified` (skips confirmation) |
| **🔬 Enrich Email** | Runs the Hunter + provider waterfall to find and verify the lead's email |
| **🤖 Score / Rescore** | Runs Claude scoring on this lead and refreshes the row |
| **📝 View Detail** | Navigates to the Lead Detail page for this lead |
| **❌ Archive** | Asks for confirmation, then sets status → `archived` |

#### Common mistakes on Pipeline

1. **Using "Clear Filters" then reapplying a stage card and wondering why the multiselect doesn't match** — Stage card clicks override the multiselect. If you want multi-stage filtering, use the sidebar multiselect, not the stage cards.
2. **Clicking "Mark Contacted" without having actually sent anything** — This sets `last_contacted_at` to now and moves the lead to `contacted`. Only click it when you have actually sent an outreach message. If you're just drafting, use Lead Detail instead.
3. **Treating the table as the full database** — The table loads up to 200 leads. If the count line says "250 on server," you are not seeing all leads. Use stage-card or tier filters to narrow the view before taking bulk actions.

---

### 2. Lead Detail — Deep-Dive and Outreach Prep

**What it's for:** A full single-lead view with the ICP score gauge, AI-generated hook, email draft builder, activity timeline, and all status/follow-up controls.

**When to use it:** Before reaching out to any lead, and after any significant conversation to log the outcome and set a follow-up date.

#### Step-by-step walkthrough

**Getting to a lead**

Navigate here from the Pipeline page by clicking **📝 View Detail** in the action panel. You can also type a Lead ID in the sidebar's **Jump to Lead** field and click **Go →**, or type `?id=123` in the URL directly.

**Header (left column)**

Shows full name, job title, company, email (with ✅/❌ verification badge), LinkedIn link, and phone if available.

**ICP Score gauge and tier badge**

A colour-coded gauge (red 0–39, amber 40–59, blue 60–79, green 80–100) shows the ICP score at a glance. The tier badge (A/B/C/D) sits next to it. Below the gauge:
- **🤖 Rescore** — re-runs Claude scoring; use this if you have updated the ICP prompt or enriched new data
- **🔬 Enrich** — runs the email waterfall for this specific lead

**ICP Reasoning (expandable)**

Click **💡 ICP Reasoning** to read Claude's written explanation of why it assigned this score. This is the most important field to check before outreach — if the reasoning doesn't match your understanding of the account, override the tier manually (see Part 5 for how).

**Hard Disqualifiers**

If red ❌ boxes appear below the reasoning, Claude has flagged specific hard disqualifiers (e.g., "company is in the wrong industry"). A lead with hard disqualifiers should not receive personal outreach even if the numeric score is borderline.

**Personalized Hook**

Shown in a yellow box. This is a Claude-generated cold email opener tailored to the lead's title, company, and any signals in the data. Two buttons:
- **🔄 Regenerate Hook** — generates a fresh hook; use this if the current one is generic or wrong
- **📧 Draft Email** — opens the email draft panel (see below)

**Email Draft panel**

Click **📧 Draft Email** to expand a draft built from the template:
```
Hi {first_name},
{hook}
I'm reaching out because [explain your specific value prop for their company/role].
Would you be open to a quick 15-minute call this week to explore whether there's a fit?
```
You get an editable **Subject** and **Body** field, then a copyable full-email block below. Click the copy icon on the code block to copy the whole email to your clipboard. The draft does not auto-send — you copy it to your email client manually.

**Activity Timeline**

A chronological log (newest first) of all activity types:
- ✉️ `email_sent` — outbound email
- 📨 `email_received` — inbound reply
- 📞 `call` — phone or video call
- 🤝 `meeting` — in-person or demo
- 📝 `note` — internal annotation
- 💼 `linkedin` — LinkedIn outreach
- 🔄 `status_change` — automatic entry when pipeline stage changes

Each entry shows the type, channel, sentiment indicator (🟢/🟡/🔴), timestamp, and your notes.

**➕ Log New Activity (expandable)**

Expand this section to log an activity. Fill in:
- **Type** — select from the dropdown (email_sent, email_received, call, meeting, note, linkedin)
- **Channel** — optional free text (e.g., `email`, `phone`, `linkedin`)
- **Notes** — required; describe what happened
- **Sentiment** — positive, neutral, or negative (used for reporting later)

Click **📌 Log** to save.

**Right column: Company card**

Shows company name, domain (clickable link), industry, employee count, country, and funding stage/date. If no company is linked, this column shows "No company linked."

Two link buttons appear if data is available: **🌐 LinkedIn** (lead's profile) and **🏢 Website** (company domain).

**Tech Stack** chips and **Recent Signals** items appear if the provider returned that data.

**🎯 Status panel (right column)**

Shows the current stage and a dropdown with only the **valid next stages** for that lead. For example, from `contacted` you can move to `engaged`, `qualified`, `closed_lost`, or `archived` — you cannot jump directly to `meeting_held`. Click **▶ Update Status** to save.

**📅 Next Action Due**

A date picker. Set this whenever you commit to a follow-up action (call back in 3 days, send a follow-up email on Thursday). The Pipeline page's **Overdue** counter watches this field across all active leads.

Click **💾 Save Due Date** after picking a date — the date is not saved until you click the button.

**📓 Notes**

Free text notes field, saved per lead. Click **💾 Save Notes**. Use this for context that doesn't fit an activity (e.g., "met at conference in March, knows our mutual contact Sarah").

#### Common mistakes on Lead Detail

1. **Forgetting to click Save Due Date after picking a date** — The date picker does not auto-save. If you pick a date and navigate away without clicking **💾 Save Due Date**, the date is lost.
2. **Reading the hook without checking the reasoning** — A hook can sound plausible even if the reasoning reveals the company is outside your ICP. Always open **💡 ICP Reasoning** before using the hook in a real email.
3. **Drafting an email before logging "what you're about to do"** — Log the intended outreach as a `note` activity (e.g., "Sending intro email re: product fit") _before_ sending. This creates a timestamp record even if you forget to log it as `email_sent` afterward.

---

### 3. Sourcing — Lead Generation Control Panel

**What it's for:** Triggering sourcing runs, managing scoring, monitoring data completeness, and bulk-enriching Tier A leads.

**When to use it:** Once a week for the scheduled weekly sourcing run, or any time you want fresh leads outside the daily scheduler.

#### Step-by-step walkthrough

**Section 1: Run a Sourcing Job**

Expand **📋 Current ICP Settings** to confirm the titles, locations, and employee range that will be used by default.

The sourcing form has two columns:

_Left column:_
- **Job Titles** multiselect — pre-populated from `ICP_TITLES`. Deselect any title to exclude it for this run only. Use **Add a custom title** to append a one-off title.
- **Employee min / max** — overrides `ICP_EMPLOYEE_MIN` and `ICP_EMPLOYEE_MAX` for this run.

_Right column:_
- **Locations** multiselect — pre-populated from `ICP_LOCATIONS`. Same deselect/add logic as titles.
- **Pages to fetch** slider (1–5) — each page fetches up to 25 leads. Start with 1 page (25 leads) until you know the data quality is good.

Click **🚀 Start Sourcing Run** to begin. A live status box shows progress and reports `leads_found` (total from API) and `leads_new` (actually added to DB, skipping duplicates).

> ⚠️ **PDL credit guard:** Before the run starts, the system estimates credit consumption. If the estimate exceeds `PDL_MAX_CREDITS_PER_RUN` (default: 50), the run is **rejected** before it starts. Reduce the number of pages or raise `PDL_MAX_CREDITS_PER_RUN` in `.env` if you hit this limit legitimately.

**Section 2: Recent Sourcing Runs**

A table of the last 10 runs showing status (🟢 completed / 🟡 running / 🔴 failed), leads found, leads new, and duration. Failed runs expand to show the error message. Click **🔄 Refresh Runs** to reload.

**Section 3: Score Management**

- **Coverage bar** — shows what percentage of your total leads have been scored
- **Leads to score per run** input — how many unscored leads to process in one batch (default 50)
- **🤖 Score Unscored (N pending)** — sends up to N unscored leads to Claude Haiku for scoring; takes 30–120 seconds for 50 leads
- **Session Cost Tracker** — shows how many leads you have scored in the current browser session and the estimated Claude API cost (≈$0.003/lead for Haiku scoring)
- **🤖 Score 10 now** (right column) — quick button to score 10 leads without changing the limit input
- **Tier Distribution donut** — shows your A/B/C/D breakdown; refreshes after each score run

**Section 4: Data Health**

Eight metrics covering:
- Total leads, with/without email, verified email count
- Scored vs. unscored, leads with hooks, leads stale > 30 days
- Database size in MB

Two action buttons in the right column:
- **🔬 Enrich Tier A (no email)** — runs the Hunter + provider waterfall on up to 10 Tier A leads that have no verified email, in one click; consumes Hunter and PDL/Apollo credits
- **🤖 Score 10 now** — same as the Section 3 quick button

#### Common mistakes on Sourcing

1. **Running 5 pages on a narrow title list** — If your ICP_TITLES has 2 titles, 5 pages against a small addressable market will return duplicates and burn PDL credits on leads already in the DB. Start with 1–2 pages and check the `leads_new` count — if page 2 adds fewer than 5 new leads, stop.
2. **Scoring before sourcing is complete** — The "Score Unscored" button operates on whatever is in the DB at the moment you click. Running sourcing and scoring simultaneously works fine, but you may need to score again after sourcing finishes to catch the last batch.
3. **Ignoring the "Stale > 30d" metric** — Leads untouched for 30+ days in `contacted` status are a pipeline health warning. Use the Pipeline page to find and archive or re-engage them.

---

### 4. Settings — Configuration and Health-Check Screen

**What it's for:** Verifying API connections, viewing ICP configuration, understanding pipeline stages, and checking scoring stats. You cannot change configuration here — changes happen in `.env`.

**When to use it:** When setting up for the first time, when troubleshooting an API failure, or when you need to remind yourself what a pipeline stage means.

#### Step-by-step walkthrough

**Section 1: API Key Status**

An active provider banner shows which lead provider is active (`PDL` or `APOLLO`) with green/red dots for PDL, Apollo, and Hunter. Below that, two columns:

_Left column — Lead Providers:_
- **PeopleDataLabs (PDL)** — shows `✅ Configured` if `PDL_API_KEY` is set
- **Apollo.io** — shows `✅ Configured` if `APOLLO_API_KEY` is set
- **Test [PROVIDER] + Hunter Usage** button — calls the live API and shows your current credit usage and remaining balance

_Right column — Anthropic:_
- Shows config status and which Claude models are used for scoring (`claude-haiku-4-5-20251001`) and writing/hooks (`claude-sonnet-4-6`)
- **Test Anthropic** button — pings the scoring stats endpoint to confirm the backend can reach Anthropic

Below those, two more cards:
- **Hunter.io** — shows key status; click "Test [PROVIDER] + Hunter Usage" (left column) to see Hunter searches used/available
- **Slack** — shows whether `SLACK_WEBHOOK_URL` is set

> ✅ **What "all good" looks like:** Active provider has 🟢, Anthropic has ✅ Configured, Hunter has ✅ Configured. Slack is optional but recommended.

**Section 2: ICP Configuration**

Left sub-column shows the live values of `ICP_TITLES`, `ICP_LOCATIONS`, `ICP_INDUSTRIES`, and employee range. Instructions for updating are shown below.

Right sub-column shows the ICP scoring prompt (read-only). Click **View full prompt** to inspect the exact text Claude uses. Character and line count are shown.

**ICP Tier Reference table**

Below the two sub-columns, a four-row table shows what each tier means, the score range, the recommended action, and the typical reason a lead ends up there.

**Section 3: Pipeline Stage Reference**

Each of the 10 pipeline stages is an expandable row showing the stage code, a plain-English definition, entry criteria, and exit criteria. This is a reference — nothing can be edited here.

**Section 4: Quick Stats**

Three metric panels:
- **This Session** — leads scored and estimated LLM spend (shared with the Sourcing page session tracker)
- **Database** — total leads and SQLite DB file size
- **Scoring Coverage** — scored count, unscored count, average Tier A score

At the bottom: the backend URL, a reminder of how to restart the stack, and a link to the API documentation at `/api/docs`.

#### Common mistakes on Settings

1. **Expecting to change ICP settings from this page** — The Settings page is read-only. All changes go in `.env`. After editing `.env`, run `docker compose restart backend` for the new values to take effect.
2. **Thinking "✅ Configured" means the key is valid** — Configured only means the environment variable is set to a non-empty string. A key that's been revoked or has the wrong value will show ✅ Configured but fail when used. Use the **Test** buttons to confirm the actual API is reachable.
3. **Using the Anthropic test as a scoring test** — The Anthropic test button calls the scoring _stats_ endpoint (a database read), not a live Claude API call. It tests that the backend is alive, not that Anthropic accepts your key. To genuinely test Claude scoring, go to the Sourcing page and score one lead.

---

## Part 3 — The Recommended Daily Workflow

### Morning Routine (10–15 minutes)

**Step 1 — Read the sidebar numbers (30 seconds)**

Open **📊 Pipeline**. Look at the four sidebar metrics:
- **Uncontacted A > 0** ✅ — you have Tier A leads waiting for outreach. This is a healthy pipeline.
- **Uncontacted A = 0** ⚠️ — no Tier A leads waiting. Run a sourcing + score cycle before the week is out.
- **Overdue > 5** ⚠️ — follow-up discipline has slipped. Overdue leads need immediate attention before new outreach.
- **Overdue > 20** ❌ — pipeline hygiene problem. Block 30 minutes today to triage and close/archive stale leads.

**Step 2 — Review new Tier A leads added overnight (3–5 minutes)**

The scheduler sources new leads at 06:00 UTC and scores them at 07:00 UTC. By the time you open the app in the morning, overnight leads should already be scored. Click the **Identified** stage card, then filter by Tier A. Any lead in `identified` with Tier A that you have not seen before is a fresh priority.

For each one:
1. Click the row to open the action panel
2. Check the Email column — if ❌ or blank, click **🔬 Enrich Email** first
3. Click **📝 View Detail** to read the ICP reasoning before deciding to contact

**Step 3 — Identify overdue follow-ups (2–3 minutes)**

Click the **Contacted** stage card. Sort by **Next Due** (oldest first — look for past dates in the Next Due column). These are people you contacted but haven't followed up with yet.

Triage logic: if the lead is Tier A or B and the due date is less than 5 days overdue, send a follow-up today. If the lead is Tier C or overdue by more than 14 days with no reply, consider archiving.

**Step 4 — Build your contact list for today (2–3 minutes)**

Prioritise in this order:
1. Tier A in `identified` or `enriched` with a verified email — first outreach
2. Tier A in `contacted` with an overdue follow-up date
3. Tier B in `contacted` with an overdue follow-up date
4. Tier B in `identified` or `enriched` with a verified email — first outreach if capacity allows

Aim for 5–10 personalised outreach touches per day as a solo founder. Above that, quality starts to drop.

---

### Outreach Preparation (per lead, 5 minutes)

**Step 1 — Open Lead Detail**

From the Pipeline action panel, click **📝 View Detail**. The Lead Detail page loads all available data for this lead.

**Step 2 — Review the ICP score and reasoning**

Read the **💡 ICP Reasoning** expander. Ask yourself: _Does this reasoning reflect what I actually know about this buyer?_ If yes, proceed. If the reasoning references the wrong industry or wrong company size, click **🤖 Rescore** and see if it improves — or note the discrepancy and adjust the prompt later (see Part 5).

**When to trust the score vs. override it:**
- ✅ **Trust it** when the lead has a complete profile (title, company size, industry all populated) and the reasoning is specific to their actual situation
- ⚠️ **Question it** when the score is very high but the company is one you would never actually target (common with titles that cross-cut industries)
- ⚠️ **Override it** when you know the company personally and the AI has too little data to score it fairly (e.g., a stealth startup with no employee count on record)

To log an override: in the **➕ Log New Activity** section, log a `note` type with text like "Manual override: scoring as Tier A despite B score — know this company, strong fit based on their recent hire."

**Step 3 — Check the personalized hook**

The hook appears in the yellow box. A usable hook is:
- ✅ Specific to the lead (mentions their title, their company, or a real signal)
- ✅ Short (1–2 sentences)
- ✅ Leads naturally into your ask

A hook that needs regeneration:
- ❌ Generic ("I noticed you're in the software industry")
- ❌ References data that is wrong or outdated
- ❌ Too long to paste into an email opener naturally

Click **🔄 Regenerate Hook** to get a new one. If two attempts both produce generic output, the company data is too sparse — check whether the company card on the right has industry, employee count, and tech stack populated. Missing data = generic hooks.

**Step 4 — Use the email draft**

Click **📧 Draft Email**. Edit the **Subject** line (the default is `Quick question, {first_name}` — keep it unless you have a better one). In the **Body**, find the placeholder `[explain your specific value prop for their company/role]` and replace it with one specific sentence about why you are reaching out to _this person_ at _this company_. Leave the rest of the template as-is for your first email — you can iterate once you see reply rates.

Copy the full email using the copy icon on the code block at the bottom of the draft section.

**Step 5 — Log the activity before sending**

Before you switch to your email client to send: in the **➕ Log New Activity** expander, log a `note` type with `"Sending intro email — using hook about [X]"`. This creates a timestamp you can reference later.

After you send, come back (or do it immediately if your email client is open in another tab) and log an `email_sent` activity with the actual subject line as your notes. Logging `email_sent` automatically updates `last_contacted_at`.

> **Why log before sending:** If you get interrupted, you still have a record that outreach was in progress. "Note: sending" before + "email_sent: sent" after is better than no record at all.

**Step 6 — Set next_action_due before leaving the page**

In the right column, use the **📅 Next Action Due** date picker. Standard follow-up cadence:
- First email → set due in **5–7 days**
- Second follow-up → set due in **7–10 days**
- Final follow-up → set due in **14 days**

After picking the date, click **💾 Save Due Date** — the date is not saved automatically.

---

### Weekly Routine (30 minutes — recommended: Monday morning)

**Step 1 — Run a fresh sourcing batch**

Open **⚡ Sourcing → Section 1**. Set pages to 2–3 for a weekly top-up. Click **🚀 Start Sourcing Run**. Wait for it to complete.

**Step 2 — Score all unscored leads**

In **Section 3: Score Management**, set the limit to 100 and click **🤖 Score Unscored**. Repeat until the "pending" count reaches 0 (or acceptable levels).

**Step 3 — Review the tier distribution**

Look at the donut chart. A healthy distribution after 3–4 weeks of consistent sourcing is roughly:
- **Tier A: 10–20%** — if above 25%, your ICP prompt may be too permissive
- **Tier B: 20–30%**
- **Tier C: 30–40%**
- **Tier D: 10–20%** — if above 40%, your sourcing filters are not aligned with the ICP prompt

**Step 4 — Enrich emails for all Tier A leads without one**

In **Section 4: Data Health**, click **🔬 Enrich Tier A (no email)**. This enriches up to 10 Tier A leads in one operation. Repeat until the "No Email" count for Tier A drops to zero or Hunter credits run low.

**Step 5 — Archive leads that have been in "Contacted" for 30+ days with no reply**

On the **📊 Pipeline** page, filter by `contacted` status. Sort by **Last Contacted** ascending. Any lead with a `Last Contacted` date more than 30 days ago and no subsequent reply should be archived. In the action panel, click **❌ Archive** for each one.

**Step 6 — Review pipeline conversion rates**

Go to **📈 Analytics**. Look at the bar chart for pipeline stage counts. The biggest drop-off is almost always between **Contacted** and **Engaged** — this is the reply rate problem. If your Contacted count is growing but Engaged stays flat, the issue is either your message, your ICP targeting, or your email deliverability (verified email addresses matter).

---

## Part 4 — Pipeline Stage Reference

| Stage | What it means | How a lead gets here | What to do next | When to go backwards |
|-------|--------------|---------------------|-----------------|----------------------|
| **Identified** | Sourced from PDL or Apollo; no email enrichment or outreach yet | Automatic: any sourcing run | Score the lead; then enrich email if Tier A | From `enriched` → `identified` if enrichment is later found to be wrong |
| **Enriched** | A verified email address has been found | Manual: clicking Enrich Email; or automatic via weekly re-enrichment job | Send first outreach email | Rarely needed |
| **Contacted** | At least one outreach attempt logged (email, LinkedIn, or call) | Manual: clicking **✉️ Mark Contacted** or logging an `email_sent` activity | Follow up if no reply within 5–7 days | N/A |
| **Engaged** | Lead has responded positively — replied, accepted a connection, or booked a call | Manual: update status after logging the positive reply | Book a discovery call; move to Qualified | Back to `contacted` if the reply turns out to be "not interested yet" |
| **Qualified** | BANT criteria confirmed (Budget, Authority, Need, Timeline) | Manual: after qualification call | Schedule a demo or full discovery session | Back to `engaged` if one BANT dimension changes |
| **Meeting Held** | Full demo or discovery call completed | Manual: after logging the meeting activity | Send proposal or design-partner ask | Back to `qualified` if they want more time |
| **Design Partner** | Lead has agreed to participate as a design partner (paid or unpaid pilot) | Manual: after verbal or written confirmation of design partner agreement | Execute the pilot; get the contract signed | Back to `meeting_held` if the design partner agreement falls through |
| **Closed Won** | Contract signed, deal is live | Manual: after receiving signed contract | Move to customer success (outside this CRM) | Archive if the deal later falls apart |
| **Closed Lost** | Lead declined, churned, or went unresponsive after qualification | Manual: after explicit rejection or 3× no-reply | Re-engage to `identified` if circumstances change in 6+ months | N/A |
| **Archived** | Soft-deleted — excluded from active pipeline views | Manual (Archive action) or implicit (any D-tier lead you choose to exclude) | Restore to `identified` if relevant again | N/A |

### Stage Transition Rules

**Automatic transitions:**
- `identified` → `enriched` does **not** happen automatically. You must click Enrich Email. However, the weekly re-enrichment scheduler (Sunday 10:00 UTC) will attempt to enrich Tier A and B leads that still lack a verified email — but it updates the email field; it does not change the `status` field.
- `status_change` activity entries are logged automatically whenever you update the status through the UI.
- Every status change is recorded in the Activity Timeline with a 🔄 entry.

**Transitions that require a manual action:**
All stage progressions require a human action: clicking a button in the Pipeline action panel, selecting a status in Lead Detail's Status panel, or logging a specific activity type. Nothing moves forward on its own.

**"Archived" vs. "Closed Lost":**
- Use **Closed Lost** when the lead went through your pipeline (at least to `engaged`) and explicitly said no, or went silent after meaningful engagement. This preserves the sales history.
- Use **Archived** for leads that never engaged, turned out to be unqualified (wrong ICP after further review), or are Tier D leads you want to exclude from daily views. The Archive action via the **❌ Archive** button sets status to `archived` and logs nothing — it is a silent removal.

**Why you should never leave leads in "Contacted" more than 14 days without an update:**

A lead in `contacted` with no follow-up and an overdue `next_action_due` is a dead lead that looks alive. It pollutes the Overdue counter, distorts your pipeline conversion data, and means you're losing momentum on a relationship that may still be recoverable. After 14 days without a reply:
- Send one final follow-up (logged as `email_sent`)
- Set `next_action_due` to 7 days out
- If still no reply after the next 7 days: move to `closed_lost` (if they were engaged) or `archived` (if they never replied at all)

---

## Part 5 — ICP Scoring Guide

### Understanding Your Score

Every lead receives a score from 0 to 100 generated by Claude (Haiku model) against the prompt in `backend/prompts/icp_v1.md`. The score reflects how well this specific person, at this specific company, at this moment in time, matches your stated ideal customer profile.

The scoring rubric has five dimensions:
- **Industry fit** — 25 points
- **Company size and stage** — 20 points
- **Role seniority and relevance** — 25 points
- **Active buying signals** — 20 points
- **Data completeness and reachability** — 10 points

A lead can only score as high as the data available about them. A Tier D score does not always mean "wrong person" — sometimes it means "not enough data to score them fairly."

**What each tier means for action:**

| Tier | Score | Action |
|------|-------|--------|
| **A** | 80–100 | Personal outreach within 24 hours. Your highest-priority leads. |
| **B** | 60–79 | Add to nurture sequence; manual review weekly. Worth contacting but lower urgency. |
| **C** | 40–59 | Hold for 90 days. Check back if your ICP expands or circumstances change. |
| **D** | 0–39 | Disqualify and archive. Hard disqualifier triggered, or too little data. |

**Tier B is not a failure.** A Tier B lead who replies is more valuable than a Tier A lead who doesn't. Use tier to prioritise _order_ of outreach, not to decide who is worth talking to.

---

### When to Trust the Score vs. Override It

**Situations where the AI systematically over-scores:**

- **Impressive title at an out-of-ICP company** — A VP of Engineering at a consumer gaming company may score Tier A if your prompt doesn't explicitly exclude consumer-facing companies. The role dimension scores well, but the industry dimension penalty may be missed.
- **Large company that looks ICP-sized** — If a company shows 200 employees on PDL but is actually a subsidiary of a 50,000-person enterprise, the headcount data misleads the model.
- **Recent funding that is old data** — "Active buying signals" gives credit for recent funding. If the funding date in the data is actually 3 years old, the signal isn't real.

**Situations where the AI under-scores:**

- **Stealth or young companies** — No employee count, no industry tag, no funding data. The model penalises missing data heavily. If you know this company personally and it's a perfect fit, override.
- **Niche but perfect-fit job titles** — If your prompt targets "VP of Engineering" but the right person has the title "Head of Platform," they may score Tier B or C because the title match is weak.
- **Companies you know have the problem** — If you saw a talk, met the founder, or know their tech stack from a conference and it's clearly a fit, the AI doesn't know that.

**How to log an override as an activity note:**

1. Open the lead in Lead Detail
2. In **➕ Log New Activity**, select type `note`
3. Write something like: `"Manual tier override: treating as Tier A despite score of 68. Company is clearly in our ICP — confirmed by direct conversation at [event]. Scoring prompt doesn't capture this edge case."`
4. Click **📌 Log**

This creates a permanent record for future calibration. When you review the ICP prompt monthly, these notes tell you where the model is consistently wrong.

---

### Improving Score Quality Over Time

**The feedback loop:**

1. After 30 outreach attempts to Tier A leads, note how many replied (check the `email_received` activities across those leads).
2. A reply rate below 25% on Tier A is a signal. It means either: (a) the ICP prompt is too permissive and Tier A leads aren't actually your ICP, or (b) your email copy is the problem (hook, value prop, call to action). Isolate which by checking if hooks are specific.
3. If the hooks are specific but the people still don't reply, the prompt is the issue. If hooks are generic, the data quality is the issue (enrich more, source differently).

**How to edit the ICP prompt:**

Open `backend/prompts/icp_v1.md` in any text editor. The file is mounted read-only into the container but lives on your host machine. Edit it directly, then reload the Settings page (click **🔄 Reload prompt** in Section 2) to verify the new content has been picked up.

> ⚠️ The prompt file is loaded fresh for each scoring call — you do not need to restart the container after editing it.

**How to re-score existing leads after a prompt update:**

On the Sourcing page (Section 3), the **Score Unscored** button only processes leads with no score yet. To re-score leads that already have a score, you currently need to use the **🤖 Rescore** button on the Lead Detail page for individual leads, or ask your technical contact to run a `tier_filter`-based rescore via the API.

---

## Part 6 — Data Provider & Credit Management

### Current Setup (PDL free tier + Hunter free tier)

**What PDL provides:**
- Full name, job title, seniority level, department
- LinkedIn URL
- Company name, domain, industry, employee count, HQ country
- Tech stack (sometimes) and recent signals (sometimes)

**What PDL does NOT provide on the free tier:**
- Work email address — this is why leads sourced via PDL almost always show blank or ❌ in the Email column after sourcing. PDL charges credits specifically for email lookups, which are not triggered during search. The email enrichment step (Hunter + provider) runs separately.

**What the Hunter waterfall does:**

When you click Enrich Email, the system runs three steps in order, stopping as soon as it finds an email:

1. **Hunter domain_search** — searches all emails Hunter knows about at the company's domain. If the lead's first/last name appears in the results, Hunter returns the email. This costs one Hunter search credit per domain (not per person), so it is the cheapest step.
2. **Provider enrich (PDL)** — asks PDL to look up the person's work email. PDL only charges a credit if they actually return an email.
3. **Hunter find_email** — asks Hunter to look up one specific person by name and domain. This consumes one Hunter search credit regardless of whether it finds anything.

If all three steps fail, the lead's email stays blank. This is common and expected — the free tiers have limited coverage.

**How to check remaining credits:**

Open **⚙️ Settings → Section 1**, find the active provider card, and click **Test [PROVIDER] + Hunter Usage**. The usage details expand showing credits used and remaining for both PDL and Hunter.

**What happens when you run out of PDL credits mid-month:**

Before each sourcing run, the system estimates how many credits it will use (based on `pages × 25` leads). If the estimate exceeds `PDL_MAX_CREDITS_PER_RUN` (default: `50` in `.env`), the run is **rejected with an error** before it starts. You will see an error message in the Sourcing page status box.

This is a safety cap, not a hard API limit. To run a larger batch (if you have credits available), raise `PDL_MAX_CREDITS_PER_RUN` in `.env` and restart the backend:

```bash
# In .env
PDL_MAX_CREDITS_PER_RUN=200

# Then restart
docker compose restart backend
```

---

### Switching to Apollo When Ready

Apollo's paid tier provides work emails directly at sourcing time, removing most of the enrichment waterfall. All your existing scored leads, activities, and pipeline state are preserved — only new sourcing runs use Apollo.

**Exact steps:**

1. Sign up for Apollo Basic at apollo.io
2. Generate an API key in Apollo → Settings → Integrations → API
3. Open your `.env` file and add:
   ```
   APOLLO_API_KEY=your_key_here
   ```
4. Change the active provider:
   ```
   ACTIVE_LEAD_PROVIDER=apollo
   ```
5. Restart the backend:
   ```bash
   docker compose restart backend
   ```
6. Open **⚙️ Settings** and confirm the active provider banner shows `APOLLO` with a 🟢 dot
7. Run a test sourcing run (1 page) on the Sourcing page and check that leads appear with emails already populated

**What changes:**
- New sourcing runs use Apollo instead of PDL
- Apollo may return work emails at sourcing time, reducing how often you need to run the enrichment waterfall
- Credit management follows Apollo's plan limits instead of PDL's

**What stays the same:**
- All existing leads, scores, activities, pipeline stages, and notes remain unchanged
- Hunter is still used as a fallback in the email enrichment waterfall
- ICP scoring, hooks, and all pipeline logic work identically

---

## Part 7 — Troubleshooting

| Symptom | Likely cause | Fix |
|---------|-------------|-----|
| ❌ Sourcing run returns 0 leads | `ICP_TITLES` or `ICP_LOCATIONS` not set in `.env`, or the API key is wrong | Check Settings → API Key Status; confirm ICP_TITLES/ICP_LOCATIONS are set via Settings → ICP Config; test the provider API with the Test button |
| ❌ All leads score as Tier D | `ANTHROPIC_API_KEY` missing or invalid; or ICP prompt is very restrictive / references wrong buyer type | Verify Anthropic key on Settings page; open `backend/prompts/icp_v1.md` and ensure it describes your actual buyer |
| ❌ Email enrichment always fails | `HUNTER_API_KEY` not set, Hunter monthly searches exhausted, or the PDL/Apollo enrich call finds no email (common on free tier) | Check Hunter usage on Settings; if exhausted, wait until the monthly reset or upgrade plan; for PDL free tier, low email coverage is expected |
| ⚠️ Slack notifications not arriving | `SLACK_WEBHOOK_URL` not configured, or the Slack app was removed from the workspace | Check Settings → Slack; verify the webhook URL is still active in your Slack app settings; set the URL in `.env` and restart backend |
| ⚠️ Pipeline page loads slowly | Large lead count (>500 leads) combined with an expired 30-second cache | Use stage-card or tier filters to reduce the result set; the table limit is 200 — filtered views load faster |
| ⚠️ Score reasoning seems wrong or irrelevant | ICP prompt is too generic, or the lead's data is sparse (no industry, no company size) | Check Data Health on Sourcing page for "No Email"/"Unscored" counts; edit the prompt to be more specific; enrich company data if possible |
| ❌ Lead detail page shows no company data | Company was not linked during sourcing (rare), or the provider returned no company information for this lead | Open the lead in Lead Detail; if company fields are blank, the company card will show "No company linked" — this is a data quality issue from the source provider |
| ❌ Scheduler not running daily jobs | Backend container crashed or was restarted without the scheduler starting; or a previous job is stuck | Run `docker compose logs backend \| grep scheduler` to check; run `docker compose restart backend` to restart; the scheduler starts automatically when the container starts |
| ❌ Settings page shows all APIs as disconnected | Backend is not reachable; `.env` not loaded into the container | Check `docker compose ps` to confirm the backend container is running and healthy; confirm `.env` exists and has the correct values; run `docker compose up -d` to start if needed |
| ❌ Frontend shows "Backend not reachable" | Backend container is down, or `BACKEND_URL` in the frontend container points to the wrong address | Run `docker compose ps` and ensure `backend` is healthy; check `docker compose logs frontend` for the `BACKEND_URL` value; the default inside Docker is `http://backend:8000` |

---

## Appendix A — Keyboard Shortcuts & Tips

### Streamlit Keyboard Shortcuts

| Key / Combo | Effect |
|-------------|--------|
| `Enter` | Submits the active form (works in any `st.form`) |
| `Ctrl+R` / `Cmd+R` | Full browser reload — clears all Streamlit session state and filters |
| Arrow keys | Navigate rows in a selected dataframe |
| `Tab` | Move between input fields in a form |

### Power-User Tips

1. **Jump directly to a lead by URL.** Add `?id=123` to the Lead Detail page URL to load that lead immediately, bypassing the sidebar jump field. Example: `http://localhost:8501/lead_detail?id=42`.

2. **The Pipeline table row click is sticky.** Once you select a row, the action panel stays open even if you scroll the page or the data refreshes in 30 seconds. Click a different row to switch, or click the same row again to deselect.

3. **Use the session cost tracker on the Sourcing page.** The "Session scoring cost" in the sidebar and Section 3 tracks exactly how much Claude API spend you've incurred this browser session (≈$0.003/lead). If you accidentally score 500 leads, the tracker shows you the damage before you check your Anthropic bill.

4. **Stage card ⚠️ warnings are early overdue signals.** If a stage card shows ⚠️, at least one lead in that stage has a `next_action_due` in the past. Click the stage card to filter to that stage, then sort by **Next Due** to see who is most overdue.

5. **The daily Slack digest is your morning briefing.** If Slack is configured, the scheduler sends a digest at 08:00 UTC listing all Tier A leads still in `identified` or `enriched` status. If you set Slack up, you can use that message as your morning triage list without opening the app.

6. **Regenerating a hook does not affect the score.** The hook and the ICP score are stored separately. You can regenerate a hook as many times as you want without touching the score. Rescoring and regenerating a hook are independent operations.

7. **Archive ≠ Delete.** Archiving a lead sets `status = archived` — all their data, activities, and notes remain in the database. You can restore a lead to `identified` from the Lead Detail Status panel if you archive one by mistake.

8. **The scheduler runs on UTC time.** Sourcing runs at 06:00 UTC, scoring at 07:00 UTC, and the Slack digest at 08:00 UTC. If you are in UTC+3 (Israel), leads scored overnight are ready by 10:00 your local time. If you are in UTC-5 (US East Coast), they are ready by 03:00 local time.

9. **"Leads found" vs "leads new" in sourcing results.** `leads_found` is the total count returned by the provider API. `leads_new` is how many were actually inserted into the database (duplicates based on provider ID are skipped). A run showing `found: 25, new: 3` means you have already ingested 22 of those leads from a previous run — this is normal and not an error.

10. **Failed sourcing runs don't corrupt data.** If a sourcing run fails mid-page, the run record is marked `failed` and any leads already fetched before the failure remain in the database. The error message is visible in the Sourcing page under "Failed Run Details." Fix the underlying issue and run again — duplicates are skipped automatically.

---

## Appendix B — Glossary

**ICP (Ideal Customer Profile)**
The precise definition of who your best-fit customer is — job title, company size, industry, seniority level, buying signals. The ICP is encoded in `backend/prompts/icp_v1.md` and is what Claude uses to score every lead.

**Tier A / B / C / D**
A letter grade assigned by Claude after scoring. A = 80–100 (immediate outreach), B = 60–79 (nurture), C = 40–59 (hold 90 days), D = 0–39 (disqualify/archive).

**Enrichment**
The process of finding and verifying a lead's work email address after they have been sourced. Sourcing brings in name, title, and company data; enrichment adds the email needed for outreach.

**Waterfall enrichment**
A multi-step email lookup strategy: (1) Hunter domain search → (2) Provider enrich (PDL or Apollo) → (3) Hunter find_email. Each step is tried in order; the process stops as soon as an email is found. Using multiple sources in order of cost is the "waterfall."

**Sourcing run**
One execution of the lead search API (PDL or Apollo) that searches for people matching your ICP filters and adds new leads to the database. A run covers one or more pages at 25 leads per page. The result shows `leads_found` (from API) and `leads_new` (added to DB, duplicates excluded).

**PDL credits**
The unit of consumption for the PeopleDataLabs API. Each person returned in a search uses credits. PDL only charges for email enrichment when an email is actually found. Credits reset monthly. The free tier has a limited monthly budget; `PDL_MAX_CREDITS_PER_RUN` in `.env` prevents any single run from consuming too many.

**scroll_token**
A PDL API concept for cursor-based pagination. When PDL returns a page of results, it may also return a scroll token that lets the API know where to start the next page. This is handled internally by the PDL client — you never see or manage scroll tokens in the UI.

**Personalized hook**
A Claude-generated 1–2 sentence cold email opener tailored to the specific lead's role, company, and any available signals. It appears in the yellow box on the Lead Detail page and is used as the opening paragraph of the email draft.

**Pipeline stage**
The current position of a lead in your sales funnel, represented by the `status` field. There are 10 stages: `identified`, `enriched`, `contacted`, `engaged`, `qualified`, `meeting_held`, `design_partner`, `closed_won`, `closed_lost`, `archived`.

**Activity log**
The timestamped record of everything that has happened with a lead — emails sent, calls made, meetings held, notes added, and status changes. Visible in the Activity Timeline on the Lead Detail page. Used by the follow-up reminder scheduler to identify overdue leads.

**Design partner**
An early-stage commercial relationship where a prospective customer agrees to use (and give feedback on) your product in exchange for early access, discounted pricing, or influence over the roadmap. In this CRM, `design_partner` is a pipeline stage between `meeting_held` and `closed_won`.

---

## Appendix C — Monthly Maintenance Checklist

Run this on the 1st of each month. Takes approximately 15–20 minutes.

- [ ] **Credit usage review** — Open Settings → API Key Status, click **Test [PROVIDER] + Hunter Usage**, and note credits used vs. remaining. If you are at >80% usage by the 1st, reduce `PDL_MAX_CREDITS_PER_RUN` or plan to upgrade.
- [ ] **DB backup verification** — The SQLite database lives at `./data/crm.db`. Copy this file to a backup location (cloud storage, external drive) and verify the copy is readable. The database contains all your leads, scores, activities, and notes — it has no automatic backup.
- [ ] **Stale lead cleanup** — On the Sourcing page, check the **Stale > 30d** metric in Data Health. On the Pipeline page, filter to `contacted` and `enriched` stages, sort by Last Contacted ascending, and archive anything that has been dormant for 30+ days with no meaningful interaction.
- [ ] **ICP prompt review** — Review your override notes logged as activities during the month. If you see a pattern (e.g., three times you noted "model over-scores companies in industry X"), edit `backend/prompts/icp_v1.md` accordingly. After editing, rescore a sample of leads from that segment to verify the change has the intended effect.
- [ ] **Docker image updates** — Run `docker compose pull` to check for updated base images, then `docker compose up -d --build` to rebuild with the latest patches. This is a zero-downtime operation for a local setup. Verify the frontend is accessible at `http://localhost:8501` after the rebuild.
