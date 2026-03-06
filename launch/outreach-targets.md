# Evalcraft Design Partner Outreach Targets

> 15 agent builders to DM for design partnership. Prioritized by likelihood to convert (indie/small team builders with active agent projects but no testing infrastructure).

---

## Tier 1: High-Priority Indie Builders (Active agent code, no testing, reachable)

### 1. Yashwanth Sai (@theyashwanthsai)
- **Platform:** GitHub, Twitter/X
- **What they build:** [Devyan](https://github.com/theyashwanthsai/Devyan) — multi-agent software dev team (architect, programmer, tester, reviewer agents) using OpenAI GPT
- **Why evalcraft fits:** Building a multi-agent system with a "tester agent" but no actual test infrastructure — evalcraft would give their tester agent deterministic replay and assertions
- **Opening line:** "Saw Devyan — love the architect→programmer→tester agent flow. Curious: how do you test the tester? We built a cassette-based replay tool that could lock down your agent pipeline for $0/run."

### 2. Dex Horthy (@dexhorthy)
- **Platform:** GitHub, Twitter/X
- **What they build:** [Mailcrew](https://github.com/dexhorthy/mailcrew) — CrewAI email agent that integrates with Stripe + Coinbase APIs
- **Why evalcraft fits:** Financial API interactions via agents are high-stakes and need deterministic testing — evalcraft cassettes would let them replay Stripe/Coinbase flows without hitting real APIs
- **Opening line:** "Mailcrew is a great use case for agent testing — Stripe + Coinbase calls you can't afford to get wrong. We built evalcraft to record those agent runs as cassettes and replay them deterministically in CI."

### 3. Tony Kipkemboi (@tonykipkemboi)
- **Platform:** Twitter/X, GitHub
- **What they build:** [crewai-gmail-automation](https://github.com/tonykipkemboi/crewai-gmail-automation) — multi-agent Gmail manager + resume optimization crew. Senior DevRel at CrewAI.
- **Why evalcraft fits:** As CrewAI's DevRel, testing CrewAI agent flows is directly relevant — evalcraft could become a recommended testing pattern in CrewAI docs
- **Opening line:** "Your gmail automation crew is exactly the kind of multi-agent system that's painful to test. We built evalcraft (cassette-based replay for agents) — would love your take as someone who teaches CrewAI patterns daily."

### 4. Lakshya Kumar (@lakshyakumar)
- **Platform:** GitHub
- **What they build:** [crewAI-projects](https://github.com/lakshyakumar/crewAI-projects) — collection of CrewAI agents (news, poems, meeting minutes, PDF chat, business reports)
- **Why evalcraft fits:** Multiple diverse agent projects but no shared testing approach — evalcraft could unify testing across all their CrewAI crews
- **Opening line:** "Nice collection of CrewAI projects! Do you have a testing strategy across all those crews? We built evalcraft to record agent runs as cassettes — one `pytest` command replays them all for free."

### 5. Shuyib (@Shuyib)
- **Platform:** GitHub
- **What they build:** [BlogPostEditor](https://github.com/Shuyib) — dual-agent blog post improvement tool with Streamlit UI, listed on awesome-crewai
- **Why evalcraft fits:** Agent pair that edits content needs regression testing when prompts change — evalcraft cassettes would catch output drift
- **Opening line:** "Saw BlogPostEditor on awesome-crewai — great idea pairing two agents for editing. Quick q: how do you catch regressions when you tweak prompts? Evalcraft records agent runs as cassettes for exactly this."

---

## Tier 2: Framework-Adjacent Builders (Larger reach, testing is core pain)

### 6. Dave Ebbelaar (@daborobot / @daborobot on X)
- **Platform:** Twitter/X, YouTube, GitHub
- **What they build:** AI cookbook, LangChain experiments, GenAI Launchpad (FastAPI + Celery + AI pipelines). 175k views on agent-building video. Founder of Datalumina.
- **Why evalcraft fits:** Teaches thousands of developers to build agents but doesn't cover testing — evalcraft fills the gap in his educational content
- **Opening line:** "Your 'build agents in pure Python' video was great — but I noticed the testing story is missing. We built evalcraft to be 'pytest for AI agents' with cassette replay. Would love to get it in front of your audience."

### 7. Ashish Patel (@ashishpatel26)
- **Platform:** GitHub, Twitter/X
- **What they build:** [500-AI-Agents-Projects](https://github.com/ashishpatel26/500-AI-Agents-Projects) — curated collection of 500+ AI agent use cases (21k+ stars)
- **Why evalcraft fits:** Curates the largest list of agent projects — adding evalcraft as the recommended testing tool would reach thousands of builders
- **Opening line:** "Your 500 AI Agents Projects repo is an incredible resource. One thing I notice across almost all agent projects: no testing infrastructure. We built evalcraft (cassette-based replay) to fix exactly this. Worth a listing?"

### 8. Slava Kurilyak (@slavakurilyak)
- **Platform:** GitHub, Twitter/X
- **What they build:** [awesome-ai-agents](https://github.com/slavakurilyak/awesome-ai-agents) — curated list of 300+ agentic AI resources. Runs Alpha Insights helping brands automate with agents.
- **Why evalcraft fits:** Maintains one of the most popular agent resource lists — adding evalcraft reaches his audience of agent builders who lack testing tools
- **Opening line:** "Your awesome-ai-agents list is a go-to resource for the community. Noticed there's no 'testing' category yet — we built evalcraft (open-source, cassette-based agent testing). Interested in adding a testing section?"

### 9. Alex Reibman (@AlexReibman)
- **Platform:** Twitter/X, GitHub (@areibman)
- **What they build:** [AgentOps](https://github.com/AgentOps-AI/agentops) — agent monitoring/observability SDK for CrewAI, OpenAI, LangChain, Autogen
- **Why evalcraft fits:** AgentOps handles observability (production); evalcraft handles testing (dev/CI). Complementary tools — not competitors. Integration opportunity.
- **Opening line:** "AgentOps nails the observability side. We built evalcraft for the other half — deterministic testing in dev/CI with cassette replay. Think VCR for agents. Could be a great complement to AgentOps."

### 10. Karan Vaidya (@KaranVaidya6)
- **Platform:** Twitter/X, GitHub
- **What they build:** [Composio](https://composio.dev) — tool/action layer for AI agents (200+ integrations, GitHub/Slack/Salesforce). Co-founder & CTO.
- **Why evalcraft fits:** Composio agents call hundreds of external tools — evalcraft cassettes would let developers test those tool-calling flows without hitting real APIs
- **Opening line:** "Composio's 200+ tool integrations are exactly where agent testing breaks down — too many external APIs to call in CI. Evalcraft records those flows as cassettes and replays them for $0. Would love to explore an integration."

---

## Tier 3: Thought Leaders & Framework Creators (Harder to reach, massive amplification potential)

### 11. Ashpreet Bedi (@ashpreetbedi)
- **Platform:** Twitter/X, LinkedIn, GitHub
- **What they build:** [Agno](https://github.com/agno-agi/agno) (formerly Phidata) — high-performance multi-agent framework. Founder & CEO.
- **Why evalcraft fits:** Agno focuses on speed (microsecond agent instantiation) but doesn't have a testing story — evalcraft's zero-cost replay aligns with their performance-first philosophy
- **Opening line:** "Love Agno's focus on performance — microsecond instantiation is impressive. What's the testing story look like? We built evalcraft for zero-cost agent replay in CI. Could be a natural fit for the Agno ecosystem."

### 12. Samuel Colvin (@samuel_colvin)
- **Platform:** Twitter/X, GitHub
- **What they build:** [Pydantic AI](https://github.com/pydantic/pydantic-ai) — GenAI agent framework with dependency injection for testing. Creator of Pydantic.
- **Why evalcraft fits:** Pydantic AI already has DI for testing — evalcraft's cassette approach is complementary, adding recording/replay on top of their mock capabilities
- **Opening line:** "Pydantic AI's dependency injection for agent testing is smart. We built evalcraft to add the recording layer — capture real agent runs as cassettes, replay in CI for $0. Think it'd pair well with your DI approach."

### 13. Joao Moura (@joaomdmoura)
- **Platform:** Twitter/X, GitHub, LinkedIn
- **What they build:** [CrewAI](https://github.com/crewAIInc/crewAI) — 44k+ star multi-agent orchestration framework. Founder & CEO.
- **Why evalcraft fits:** CrewAI has 100k+ developers but no built-in testing pattern — evalcraft could become the recommended way to test CrewAI crews
- **Opening line:** "CrewAI's growth is incredible — 44k stars and 100k+ devs. One gap I keep seeing in CrewAI projects: no testing infrastructure. We built evalcraft (cassette-based replay, pytest-native) specifically for this. Would love to chat about a recommended testing pattern."

### 14. Vasek Mlejnsky (E2B)
- **Platform:** Twitter/X, GitHub, LinkedIn
- **What they build:** [E2B](https://github.com/e2b-dev/E2B) — sandboxed cloud environments for AI agent code execution. Co-founder & CEO. Used by 88% of Fortune 100.
- **Why evalcraft fits:** E2B provides the sandbox runtime, evalcraft provides the test layer — complementary infrastructure for production agent deployment
- **Opening line:** "E2B solves the execution sandbox brilliantly. We built evalcraft for the testing layer — record agent runs, replay deterministically in CI. Sandbox + testing = production-ready agents. Interested in exploring this together?"

### 15. Matt Shumer (@mattshumer_)
- **Platform:** Twitter/X (massive audience after viral post with 20M+ views)
- **What they build:** HyperWrite — AI writing assistant with browser agents (Agent Trainer, Agent Studio). CEO of OthersideAI.
- **Why evalcraft fits:** HyperWrite builds browser agents that learn from user actions — testing those learned behaviors is exactly what cassette replay solves
- **Opening line:** "Your Agent Trainer is fascinating — agents that learn by watching users. How do you regression-test learned behaviors? We built evalcraft to record agent runs as cassettes and replay them in CI. Could be a fit for HyperWrite's QA."

---

## Summary by Platform

| Platform | Targets |
|----------|---------|
| **Twitter/X** | @theyashwanthsai, @dexhorthy, @tonykipkemboi, @daborobot, @ashishpatel26, @slavakurilyak, @AlexReibman, @KaranVaidya6, @ashpreetbedi, @samuel_colvin, @joaomdmoura, @mattshumer_ |
| **GitHub only** | @lakshyakumar, @Shuyib |
| **LinkedIn** | Vasek Mlejnsky (E2B) |

## Outreach Priority Order

1. Tier 1 first (indie builders = fastest to convert, most hands-on feedback)
2. Tier 2 next (curators/educators = distribution multiplier)
3. Tier 3 last (framework creators = hardest to reach but biggest impact)
