# Evalcraft DM Templates

> 3 templates for Twitter DMs (under 280 chars each) + longer versions for LinkedIn/email.

---

## Template 1: Cold Outreach (Never Interacted)

### Twitter DM (279 chars)

```
Hey! Saw your [PROJECT] — really cool agent work. We built evalcraft, an open-source tool that records agent runs as cassettes and replays them in CI for $0. Think "pytest for AI agents." Would you be open to trying it as a design partner? https://github.com/beyhangl/evalcraft
```

### LinkedIn / Email (longer version)

**Subject:** Your agent project + a testing tool that might save you hours

```
Hey [NAME],

Saw [PROJECT] on [GitHub/Twitter] — really impressive work, especially [SPECIFIC DETAIL].

One thing I notice across almost every agent project: testing is either
nonexistent or painfully expensive. We built evalcraft to fix this.

What it does:
- Records agent runs (LLM calls, tool calls) as JSON cassettes
- Replays them deterministically in CI — zero API calls, $0 cost
- Works with OpenAI, LangChain, LangGraph out of the box
- pytest-native: `pytest --evalcraft` and you're done

We're looking for 10 design partners to shape the roadmap. You'd get:
- Hands-on setup help (we'll pair with you)
- Direct Slack access to maintainers
- Your use cases drive what we build next

Interested? Happy to jump on a quick call or just try it:
pip install evalcraft

GitHub: https://github.com/beyhangl/evalcraft
Apply: https://beyhangl.github.io/evalcraft/#pricing

— Beyhan
```

---

## Template 2: Warm Outreach (Replied to Tweet / Starred Repo)

### Twitter DM (276 chars)

```
Thanks for [starring evalcraft / engaging with our post]! Since you're building [THEIR THING], I think you'd be a great design partner — we're looking for 10 teams to shape the roadmap. You'd get hands-on setup help + direct Slack access. Interested?
```

### LinkedIn / Email (longer version)

**Subject:** Following up — evalcraft design partnership

```
Hey [NAME],

Thanks for [starring the repo / replying to our tweet about agent testing].
Really appreciate the support!

Since you're actively building [PROJECT], I wanted to reach out directly.
We're selecting 10 design partners for evalcraft, and your work on
[SPECIFIC DETAIL] is exactly the kind of use case we're building for.

What design partners get:
- Hands-on setup — we'll help you get evalcraft into your CI pipeline
- Direct Slack channel with the maintainers
- Your feedback directly shapes the roadmap (features, integrations, API)

We're especially interested in how evalcraft handles [THEIR FRAMEWORK]
workflows, since that's a gap we want to nail.

Would a 15-min call work this week? Or if you prefer async, just:
pip install evalcraft && evalcraft init

Happy to answer any questions right here too.

— Beyhan
```

---

## Template 3: Follow-Up (No Response After 3-5 Days)

### Twitter DM (268 chars)

```
Hey, just bumping this — totally understand if the timing's off. We just shipped [NEW FEATURE] that's relevant to your [PROJECT]. Happy to send a quick demo or just share the changelog. No pressure either way!
```

### LinkedIn / Email (longer version)

**Subject:** Quick follow-up + new feature you might like

```
Hey [NAME],

Just following up on my earlier message about evalcraft. Totally understand
if timing isn't right — agent testing might not be top of mind yet.

Quick update: we just shipped [NEW FEATURE], which is directly relevant
to [THEIR PROJECT/FRAMEWORK]:

- [Feature 1 — e.g., "LangGraph adapter for auto-recording graph nodes"]
- [Feature 2 — e.g., "MockTool sequential responses for multi-step flows"]

If you're curious but short on time, here's a 60-second path:
  pip install evalcraft
  evalcraft init
  pytest --evalcraft

Creates a sample cassette, records it, and replays it — no API key needed.

Either way, I'm a fan of what you're building with [PROJECT]. Keep shipping!

— Beyhan
```

---

## Quick Reference: Personalization Variables

| Variable | What to fill in |
|----------|----------------|
| `[NAME]` | First name |
| `[PROJECT]` | Their specific project/repo name |
| `[SPECIFIC DETAIL]` | Something specific about their work (architecture choice, feature, framework) |
| `[THEIR THING]` | Brief description of what they build |
| `[THEIR FRAMEWORK]` | CrewAI / LangGraph / OpenAI / etc. |
| `[NEW FEATURE]` | Latest evalcraft feature relevant to their stack |

## Tips

- **Send Twitter DMs between 9am-12pm PST** (highest response rates for dev tools)
- **Personalize the opening line** using the specific lines from `outreach-targets.md`
- **Don't pitch in the first message** if possible — lead with genuine interest in their project
- **Follow up once** after 3-5 days, then stop. Respect the no-response.
- **If they engage**, move to Slack/call quickly — DMs are for opening doors, not closing deals
