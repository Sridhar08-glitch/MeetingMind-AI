# MeetingMind AI — User Guide

Welcome to MeetingMind AI. This guide walks through everything you can do as a user, from
uploading your first recording to running a team of AI agents over your organisational knowledge.

> **Your data stays yours.** MeetingMind runs on local AI — recordings and transcripts are
> processed on your own machine. Everything you see is scoped to *your* account.

---

## Getting started

1. Open the app at **http://localhost:3000** and **register** or **log in**.
2. You land on the **Dashboard** — an overview of your meetings and workspace activity.
3. Use the left sidebar to move between Meetings, Workspace, Knowledge Hub, Executive, and the
   AI Agent Center.

## 1. Upload a meeting

1. Go to **Meetings → Upload**.
2. Choose an audio or video file (mp3, wav, m4a, aac, flac, ogg, mp4, mov, avi, mkv).
3. Optionally set a title, description, language and tags.
4. If you upload a file you've uploaded before, MeetingMind detects the duplicate (by checksum)
   and asks how to handle it: **reject**, **replace**, **keep both**, or **ignore**.
5. The file is validated (type, size, duration) and queued. You'll see a **validation report**
   and a live **processing status**.

**Supported limits:** up to 500 MB and 6 hours per file by default (an administrator can change
these).

## 2. Transcription

Once processing starts, MeetingMind extracts and normalises the audio and transcribes it locally:

- Watch progress on the meeting's **status** / timeline.
- When done, open the meeting to see the **transcript** — split into timestamped segments with
  a detected language and per-segment confidence.
- **Search** within the transcript, filter by speaker or time.
- **Edit** any segment inline to fix a word; the original is preserved so you can **restore** it.
- **Download** the transcript as TXT, SRT, VTT, PDF or DOCX.
- Need a different model or language? Use **Re-transcribe** to run STT again.

## 3. AI summaries & insights

After transcription, MeetingMind's local LLM analyses the meeting and produces, all grounded in
the transcript:

- **Executive / detailed / bullet summaries** and **meeting minutes**
- **Action items**, **decisions**, **risks**, **issues**, **follow-ups**, **deadlines**
- **Keywords**

Open the **AI Review Center** on the meeting page to review them. Every analysis is **versioned** —
regenerating never destroys the previous version, and you can browse the **history**.

## 4. Meeting Chat

Ask questions about a single meeting and get **cited** answers:

1. Open a meeting and start a **conversation** (or pick a **suggested question**).
2. Ask anything — "What did we decide about pricing?", "Who owns the follow-ups?".
3. Answers come **only** from the meeting. Each answer includes **citations**; click a citation's
   timestamp to jump straight to that moment in the transcript.
4. If the meeting doesn't contain the answer, MeetingMind tells you so rather than guessing.

## 5. Workspace (tasks & decisions)

The Workspace turns meeting outcomes into tracked work — with **you** in control.

- **AI Approvals:** MeetingMind *suggests* tasks, issues, decisions and risks with a confidence
  score and the exact quote/speaker/timestamp it came from. Nothing becomes "real" until you
  **approve** it (you can edit first). You can bulk approve/reject/archive.
- **Kanban board:** approved tasks appear on a board (To Do → In Progress → In Review → Done,
  plus Blocked/Cancelled). Drag cards to move them; open a card for its checklist, comments,
  activity, and links back to the source meeting.
- Track **issues**, **decisions**, **risks**, **follow-ups** and **notes** per project.
- Generate **reports** and email drafts (daily/weekly/sprint/executive/technical/customer/…).

## 6. Knowledge Hub

Everything MeetingMind learns is indexed into your **organisational memory**:

- **Search** across all meetings at once.
- **Cross-meeting chat:** ask questions that span many meetings/projects.
- **Time-travel:** "What did we know about X on a given date?"
- **Timelines:** how a topic or decision evolved over time.
- **Reliability & consensus:** how settled the organisation is on a topic, and where opinions
  changed.
- **Conflicts:** detected contradictions between decisions, which you can resolve.
- **Graphs:** knowledge and people/relationship graphs.

## 7. Executive Dashboard

A leadership-level view of health and trends:

- **Workspace health score** and status (excellent/good/warning/critical), plus analytics.
- **Recommendations** and **alerts** you can acknowledge/resolve.
- **Trends** (daily/weekly/monthly) and **predictions**.
- **"Why?"** explanations behind each metric.
- **Executive briefs** for the week or month.

## 8. AI Agent Center

Put specialised AI agents to work over your knowledge:

- **Agents:** 12 specialists (executive, project manager, technical architect, QA, risk analyst,
  business analyst, documentation, meeting analyst, knowledge, report generator, research,
  customer success). Run one directly with a request.
- **Planner:** describe a goal and let the Planner pick and orchestrate the right agents. Choose a
  policy to trade speed for depth: **Lowest Latency**, **Fast**, **Balanced** (default),
  **Highest Quality**, **Research**.
- **Collaboration:** run a multi-agent **workflow** — e.g. *Sprint Planning*, *Executive Review*,
  *Release Readiness*, *Risk Assessment*, *Architecture Review*, *Customer Feedback*,
  *Incident Postmortem* — where agents produce, hand off, review, debate and vote.
- Some plans/workflows pause for **your approval** before finalising.
- Every run shows its steps, evidence and quality scores, so you can see *how* the answer was
  reached.

## 9. Settings

- Update your **profile** (name) and **change your password** under Settings.
- Log out to blacklist your session's refresh token.

## Tips & troubleshooting

- **"Processing" seems stuck?** The first run downloads the Whisper model and warms up Ollama;
  subsequent runs are faster. Check the meeting timeline for the current stage.
- **An answer says "not found".** That's by design — MeetingMind won't invent an answer that
  isn't supported by your transcripts.
- **Something looks off in a transcript.** Edit the segment; your fix is preserved and feeds back
  into analysis when you regenerate.
- **Need real transcription/AI?** If the app is running in mock mode, ask your administrator to
  enable the local AI stack (see the Admin Guide).

For deeper questions see the [README](../README.md) and, for operators, the
[Admin Guide](ADMIN_GUIDE.md).
