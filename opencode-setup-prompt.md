# OpenCode Global Professional Setup Prompt

> Copy everything between the START and END markers and paste it into a new OpenCode session.

---

## START PROMPT

You are an OpenCode environment administrator and AI tooling expert. Your task is to fully configure THIS machine for professional AI-assisted software engineering. Work globally, not per-project.

## GLOBAL INSTALL LOCATION

Install every compatible skill into the global OpenCode directory:

```
~/.config/opencode/skills/
```

Do NOT install into project folders. If a skill already exists at `~/.agents/skills/`, it is already discovered — do NOT duplicate it into `~/.config/opencode/skills/`. Only install NEW skills that don't already exist.

OpenCode discovers skills from these locations (no config needed):
- `~/.config/opencode/skills/*/SKILL.md`
- `~/.claude/skills/*/SKILL.md`
- `~/.agents/skills/*/SKILL.md`

If a skill already exists in any of these locations, update it. Don't duplicate.

## OFFICIAL REFERENCES

Read these docs before doing anything:
- OpenCode Skills: https://opencode.ai/en/docs/skills
- OpenCode MCP Servers: https://opencode.ai/en/docs/mcp-servers
- OpenCode Config: https://opencode.ai/en/docs/config/
- Context7 MCP: https://github.com/upstash/context7
- Firecrawl MCP: https://docs.firecrawl.dev/quickstarts/opencode
- Open Agent Skills: https://openagentskills.dev/docs/using-skills
- SkillsMD Registry: https://skillsmd.dev/
- OpenAgentSkill Rankings: https://www.openagentskill.com/rankings

## STEP 1: AUDIT CURRENT STATE

Before installing anything:
1. List all skills currently at `~/.agents/skills/`, `~/.claude/skills/`, and `~/.config/opencode/skills/`
2. Read `~/.config/opencode/opencode.jsonc`
3. Check what MCP servers are already configured
4. Check which Node.js / Python / system tools are available (node, npx, uvx, docker, git, etc.)
5. Report what's already installed vs what's missing

## STEP 2: INSTALL MCP SERVERS

Configure these MCP servers in `~/.config/opencode/opencode.jsonc`:

### Required MCP Servers

| MCP Server | Type | Install Command | Notes |
|---|---|---|---|
| **Context7** | remote | URL: `https://mcp.context7.com/mcp` | Up-to-date library docs. Optional: set `CONTEXT7_API_KEY` env var for higher rate limits |
| **GitHub** | local | `npx -y @modelcontextprotocol/server-github` | Requires `GITHUB_PERSONAL_ACCESS_TOKEN` env var. Pause and ask user for token |
| **Firecrawl** | local | `npx -y firecrawl-mcp` | Requires `FIRECRAWL_API_KEY`. Pause and ask user for key. Web scraping/crawling |
| **Filesystem** | local | `npx -y @modelcontextprotocol/server-filesystem` | Set allowed directories to `["/home"]` for broad access |
| **Playwright** | local | `npx -y @playwright/mcp@latest` | Browser automation and E2E testing |
| **Docker** | local | `npx -y @modelcontextprotocol/server-docker` | Docker container management |
| **PostgreSQL** | local | `npx -y @modelcontextprotocol/server-postgres` | Requires connection string. Pause and ask user for `DATABASE_URL` |

### Example opencode.jsonc MCP section

```jsonc
{
  "$schema": "https://opencode.ai/config.json",
  "mcp": {
    "context7": {
      "type": "remote",
      "url": "https://mcp.context7.com/mcp",
      "enabled": true
    },
    "github": {
      "type": "local",
      "command": ["npx", "-y", "@modelcontextprotocol/server-github"],
      "enabled": true,
      "environment": {
        "GITHUB_PERSONAL_ACCESS_TOKEN": "{env:GITHUB_PERSONAL_ACCESS_TOKEN}"
      }
    },
    "firecrawl": {
      "type": "local",
      "command": ["npx", "-y", "firecrawl-mcp"],
      "enabled": true,
      "environment": {
        "FIRECRAWL_API_KEY": "{env:FIRECRAWL_API_KEY}"
      }
    },
    "filesystem": {
      "type": "local",
      "command": ["npx", "-y", "@modelcontextprotocol/server-filesystem", "/home"],
      "enabled": true
    },
    "playwright": {
      "type": "local",
      "command": ["npx", "-y", "@playwright/mcp@latest"],
      "enabled": true
    },
    "docker": {
      "type": "local",
      "command": ["npx", "-y", "@modelcontextprotocol/server-docker"],
      "enabled": true
    },
    "postgres": {
      "type": "local",
      "command": ["npx", "-y", "@modelcontextprotocol/server-postgres"],
      "enabled": true,
      "environment": {
        "POSTGRES_CONNECTION_STRING": "{env:DATABASE_URL}"
      }
    }
  }
}
```

**IMPORTANT**: If any MCP server requires an API key or OAuth token, PAUSE and ask the user before proceeding. Never skip configuration silently.

## STEP 3: INSTALL PROFESSIONAL SKILLS

Use `npx skills add <owner/repo> -g` for global install, or manually create `~/.config/opencode/skills/<name>/SKILL.md` files.

Install the best-maintained versions. Avoid abandoned repositories. Prefer repos with 1000+ stars or official organization maintainers.

### High-Priority Skills to Install

#### From obra/superpowers (244K stars)
The gold standard agentic skills framework. Install these individually:
```bash
npx skills add obra/superpowers -g
```
This provides: systematic-debugging, test-driven-development, writing-plans, executing-plans, requesting-code-review, receiving-code-review, finishing-a-development-branch, verifying-before-completion, subagent-driven-development, dispatching-parallel-agents, using-git-worktrees, brainstorming, diagnosing-bugs

#### From anthropic-skills (official Anthropic)
```bash
npx skills add anthropics/skills -g
```
This provides: algorithmic-art, brand-guidelines, canvas-design, claude-api, doc-coauthoring, docx, frontend-design, internal-comms, pdf, pptx, skill-creator, slack-gif-creator, theme-factory, web-artifacts-builder, webapp-testing, xlsx

#### From cortex-ai-skills
```bash
npx skills add cortex-ai/cortex-ai-skills -g
```
This provides: csharp, dotnet-core, documentation, humanize-text, javascript, legacy-modernization, nestjs, nextjs, python, react, spec-mining, testing, typescript

#### From cloudflare-skills
```bash
npx skills add cloudflare/cloudflare-skills -g
```
This provides: agents-sdk, cloudflare, cloudflare-email-service, cloudflare-one, durable-objects, sandbox-sdk, skills, turnstile-spin, web-perf, workers-best-practices, wrangler

#### From vercel-react-best-practices
```bash
npx skills add vercel-labs/vercel-react-best-practices -g
```
This provides: composition-patterns, react-native-skills, react-view-transitions, writing-guidelines

### Skills to Install by Category

#### Architecture & Design
- `architecture-diagram-generator` — System design diagrams as HTML+SVG
- `codebase-design` — Deep module design vocabulary
- `domain-modeling` — DDD ubiquitous language
- `improve-codebase-architecture` — Architecture review + visual report
- `design-an-interface` — Parallel interface design exploration

#### Planning & Workflow
- `writing-plans` — Implementation plans from specs (from superpowers)
- `executing-plans` — Plan execution with checkpoints (from superpowers)
- `prd-to-plan` — PRD to phased implementation plan
- `prd-to-issues` — PRD to GitHub issues
- `to-spec` — Conversation to spec
- `to-tickets` — Spec to tracer-bullet tickets
- `implement` — Execute implementation from spec
- `wayfinder` — Multi-session work planning

#### Code Quality & Review
- `code-review` — Multi-dimension code review
- `caveman-review` — Ultra-compressed PR review
- `requesting-code-review` — Pre-merge verification (from superpowers)
- `receiving-code-review` — Process review feedback (from superpowers)
- `verifying-before-completion` — Pre-commit verification (from superpowers)

#### Debugging & Investigation
- `systematic-debugging` — Structured bug investigation (from superpowers)
- `diagnosing-bugs` — Hard bug diagnosis loop
- `triage` — Bug triage and root cause
- `qa` — Conversational QA session

#### Git & Version Control
- `contextual-commits` — Contextual commit messages
- `caveman-commit` — Ultra-compressed commits
- `finishing-a-development-branch` — Branch completion (from superpowers)
- `resolving-merge-conflicts` — Merge conflict resolution
- `git-guardrails-claude-code` — Block dangerous git commands
- `using-git-worktrees` — Git worktree isolation (from superpowers)

#### Testing
- `test-driven-development` — TDD workflow (from superpowers)
- `tdd` — TDD with coverage enforcement
- `playwright-pro` — Playwright testing toolkit
- `e2e` — End-to-end testing
- `generate` — Test generation
- `review` — Test quality review
- `fix` — Fix flaky tests

#### Python & Django
- `python` — Python 3.11+ conventions, type hints, pytest
- `django-orm` (search for Django skills)
- FastAPI patterns (from python skill)

#### Frontend
- `react` — React 18+ patterns, hooks, Server Components
- `nextjs` — Next.js 14+ App Router
- `vue` (search for Vue 3 skills)
- `typescript` — TypeScript conventions
- `javascript` — Modern JS conventions
- `vercel-react-best-practices` — React performance

#### DevOps & Infrastructure
- `deploy` — CI/CD and deployment
- `sre` — Site reliability engineering
- `devops-engineer` — DevOps practices
- `cloud-security` — Cloud security assessment
- `docker` (from docker MCP or dedicated skill)

#### Documentation
- `documentation` — API docs, OpenAPI, docstrings
- `docs` — Codemaps and README maintenance
- `doc-maintenance` — Doc drift detection
- `doc-updater` — Sync docs with code
- `technical-writing` (search for tech writing skills)

#### Security
- `security` — Security intelligence bundle
- `cybersecurity` — Offensive security audit
- `cloud-security` — AWS/Azure/GCP security
- `gdpr-compliance` — GDPR implementation

#### Productivity & Communication
- `brainstorming` — Creative exploration (from superpowers)
- `grill-me` — Relentless interview
- `grill-with-docs` — Interview with doc creation
- `handoff` — Session handoff to fresh agent
- `claude-handoff` — Agent handoff
- `cavecrew` — Subagent delegation
- `caveman` — Token-efficient communication

#### Research & Analysis
- `research` — Structured research workflow
- `Deep-Research-skills` — Deep research pipeline
- `market-research` — Market analysis
- `financial-analyst` — Financial modeling

#### Specialized
- `graphify` — Knowledge graph from codebase (already installed at ~/.claude/skills/)
- `Understand-Anything` — Codebase analysis with knowledge graphs
- `stop-slop` — Remove AI writing patterns
- `humanize-text` — Make AI text sound natural
- `theme-factory` — Style artifacts with themes
- `json-canvas` — Obsidian canvas files
- `obsidian-vault` — Obsidian vault management

### Install Commands

Run these to install skill collections:

```bash
# Core agentic workflow (244K stars)
npx skills add obra/superpowers -g

# Anthropic official skills
npx skills add anthropics/skills -g

# Engineering skills bundle
npx skills add cortex-ai/cortex-ai-skills -g

# Cloudflare skills
npx skills add cloudflare/cloudflare-skills -g

# Vercel React best practices
npx skills add vercel-labs/vercel-react-best-practices -g

# Galyarder Framework (already installed at ~/.agents/skills/)
# npx skills add galyarder/galyarder-framework -g

# Architecture diagrams
# Check: https://github.com/architecture-diagram-generator (if exists)

# Research skills
npx skills add Deep-Research-skills/deep-research -g

# SuperPM product management
# Already installed at ~/.agents/skills/superPM

# Cloudflare specific
npx skills add cloudflare/cloudflare-skills -g
```

## STEP 4: DISCOVER AND INSTALL EXTRA SKILLS

Search these registries for high-quality skills:

1. **OpenAgentSkill Rankings**: https://www.openagentskill.com/rankings
   - Install any skill with 1000+ stars and quality score 90+
   
2. **SkillsMD Registry**: https://skillsmd.dev/
   - Browse trending skills, install OpenCode-compatible ones
   
3. **Open Agent Skills**: https://openagentskills.dev/
   - Browse by category, install relevant ones
   
4. **GitHub Search**: Search for `opencode skill SKILL.md` or `agent skill SKILL.md`
   - Install well-maintained repos with recent activity

For each discovered skill:
- Check stars, last commit date, and maintenance status
- Verify it has proper SKILL.md with frontmatter
- Skip archived, deprecated, or experimental repos
- Install if it covers a gap not already filled

## STEP 5: CONFIGURE PERMISSIONS

Add skill permissions to `~/.config/opencode/opencode.jsonc`:

```jsonc
{
  "permission": {
    "skill": {
      "*": "allow"
    }
  }
}
```

This allows all skills globally. If you need fine-grained control:
```jsonc
{
  "permission": {
    "skill": {
      "*": "allow",
      "experimental-*": "ask",
      "internal-*": "deny"
    }
  }
}
```

## STEP 6: VERIFY INSTALLATION

After all installations:
1. List all installed skills (count and names)
2. List all configured MCP servers
3. Verify each skill has valid frontmatter (name + description)
4. Check for duplicate skills across locations
5. Check for conflicting skills (same name, different content)
6. Verify MCP servers can start (run `opencode mcp list` if available)

## STEP 7: GENERATE REPORT

Output a comprehensive report with:

### Installed Skills
- Total count
- List grouped by category
- Source repository for each

### Installed MCP Servers
- Name, type, status
- Required environment variables (marked as SET or MISSING)

### Configuration Files Modified
- List every file that was created or modified

### Missing API Keys
- List every environment variable that needs to be set
- Provide exact export commands for each

### Recommended Improvements
- Skills that could be added for the user's tech stack
- MCP servers that would be useful
- Configuration optimizations

### Optional Skills
- Skills that are nice-to-have but not critical
- Skills for specific workflows the user might want

### Potential Conflicts
- Duplicate skills detected
- Conflicting skill definitions
- MCP server port conflicts

## RULES

- Do NOT install deprecated or archived skills
- Do NOT install experimental skills unless clearly marked stable
- Do NOT overwrite existing custom user skills without asking
- Do NOT install skills into project folders (use global only)
- Ask before removing anything
- Work carefully and verify every step
- If OAuth or API keys are required, PAUSE and ask the user
- Never skip configuration silently
- Prefer official skills over community forks
- Prefer skills with 1000+ GitHub stars
- Prefer skills with recent commits (within 6 months)

## EXECUTION ORDER

1. Audit current state (read-only)
2. Report audit findings to user
3. Wait for user confirmation
4. Install MCP servers (pause for API keys)
5. Install skill collections via `npx skills add`
6. Install individual skills for gaps
7. Configure permissions
8. Verify and generate report
9. Present report to user

BEGIN NOW. Start with Step 1: Audit current state.

## END PROMPT
