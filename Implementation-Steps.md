Here’s a **step‑by‑step weekly planner** in checkbox format so you can track progress clearly:

---

## ✅ Week 1–2: Setup
- [x] Create basic project skeleton (backend + CI pipeline)
- [x] Register GitHub App & configure OAuth
- [x] Set up webhook listener for PR events
- [x] Verify connectivity with GitHub API (test PR event reception)

---

## ✅ Week 3–4: Static Analysis
- [x] Integrate linters (ESLint, Pylint, Checkstyle)
- [x] Add bug‑pattern detection (Bandit, SpotBugs)
- [x] Build modular analysis pipeline (language‑agnostic)
- [x] Validate findings on sample repositories

---

## ✅ Week 5–6: Refactor Suggestions
- [ ] Connect AI/LLM for code smell detection
- [ ] Map raw analysis → actionable refactor hints
- [ ] Implement severity levels (critical, warning, suggestion)
- [ ] Test refactor suggestions on real PRs

---

## ✅ Week 7–8: Test Generation
- [ ] Integrate test frameworks (PyTest, Jest, JUnit)
- [ ] Implement AI‑based test case generation
- [ ] Ensure generated tests run in CI/CD pipeline
- [ ] Validate coverage improvement metrics

---

## ✅ Week 9–10: Feedback System
- [ ] Build natural language formatter for findings
- [ ] Structure feedback into GitHub review comments
- [ ] Implement configurable verbosity (short vs detailed)
- [ ] Test posting reviews on live PRs

---

## ✅ Week 11–12: Polish & Deploy
- [ ] Set up CI/CD pipeline for deployment
- [ ] Add logging, monitoring, error handling
- [ ] Write documentation & onboarding guide
- [ ] Deploy GitHub App / Action for team use

---

## ✅ Web Dashboard & Repository Management
- [x] Build a proper login page (form-based, handles GitHub OAuth login flow)
- [x] Show a list of linked repositories
- [x] Show a list of unlinked repositories available to be linked
- [x] Build a commit heatmap for linked repositories (per-repo commit activity)

---

## 🚀 Stretch Goals (Optional)
- [ ] Add multi‑language support
- [ ] Implement reinforcement learning from team feedback
- [ ] Build analytics dashboard (bug/refactor trends)
- [ ] Integrate Slack/Teams notifications

---

## 🌐 Web-Based IDE (Design Agreed — Turn-by-Turn)

### Layout
- Three panes: **file tree** (left) · **Monaco editor** (right) · **problems console** (bottom)
- Desktop-first; fixed three-pane grid; dark theme

### Decisions locked in
- **Editor:** Monaco (self-hosted, pinned version via npm build step → served from `app/static`)
- **Read-only** for now — browse + inspect problems; no save/commit path yet
- **Modes (toggleable):** *Branch* (repo default branch, on-demand lint) · *PR #n* (that PR's changed files + stored review findings)
- **Entry:** Dashboard repo cards get an "Open IDE" button → `/ide/<owner>/<repo>`; PR list per linked repo on the dashboard; topbar switcher (repo/PR) in the IDE
- **Data fetch:** GitHub App installation token (per-request mint + in-memory cache, 1h expiry handled); git tree API (recursive) with junk dirs hidden (node_modules, .git, dist/build, venv, __pycache__); git blobs API for files >1MB raw limit
- **Problems source:** linter findings on-demand per open file (lazy, cached in-memory w/ TTL) **+** stored PR review findings (new: persist PR reports to SQLite at webhook time); AI suggestions appear for line-linked findings (PR mode + manual per-file "Refactor" button)
- **Click problem →** auto-open file tab if needed, scroll to line, red/orange/yellow/green squiggle per severity (map our 4 severities), flash highlight
- **Console:** group by file across all open tabs; severity filter chips; counts header; minimal list otherwise
- **On load:** auto-open first lintable file; re-lint on open + manual "Lint" button; restore last session (repo + tabs) via localStorage
- **AI in branch mode:** NOT auto-run per file (cost); linters only on-demand, AI via PR mode or manual Refactor
- **Monaco chrome:** VS Code defaults (minimap, line numbers, word wrap off, file path top bar)

### Implementation steps
1. [x] Add npm build step: `package.json` with pinned `monaco-editor`, script to copy monaco dist → `app/static/vendor/monaco`; wire into Render build + local dev
2. [x] Add SQLite store for PR findings: `app/store.py` — table `pr_findings` (repo, pr_number, head_sha, file, line, severity, rule, message, linter, created_at); webhook writes report after review; on-demand "Run analysis" for unreviewed PRs
3. [x] Add `app/ide.py` — backend: install-token-cached fetch of git tree (with junk filter), file content (raw < 1MB else blobs API), on-demand lint of a single file (reuse `analyze_files` on a temp copy), cached per (repo, sha, path) w/ TTL, manual Refactor (AI) endpoint, stored-PR-findings endpoint
4. [x] Add `/ide/<owner>/<repo>` + `/ide/<owner>/<repo>/pr/<number>` routes in `app/routes.py` (auth required; passes token + repo meta into template); topbar switcher + PR list data
5. [x] Build `app/templates/ide.html` — three-pane layout, file tree panel, tab bar, problems console with filter chips
6. [x] Build `app/static/js/ide.js` — Monaco init (dark theme, VS Code defaults, read-only, markers/squiggles), tree render + navigation, tab management, console render + grouping, click-to-jump + flash, localStorage session restore, mode switch, Lint/Refactor buttons
7. [x] Extend `app/static/css/style.css` with IDE layout styles (panes, resizer, tree, tabs, console)
8. [x] Dashboard: "Open IDE" button per repo card + open-PRs list per linked repo
9. [x] Tests: `tests/test_ide.py` (tree fetch filter, content fetch, single-file lint, PR-findings read/write, route rendering), `tests/test_store.py` (SQLite PR findings)
10. [x] Run full suite; commit; deploy (merge develop → main for Render)

> **Status:** 72 passed, 2 skipped (jar-dependent). Uncommitted working tree — commit + merge to `main` to deploy.

---

Would you like me to also **reformat this into a Kanban board view** (Backlog → In Progress → Done) so you can track tasks visually, or keep it strictly as a weekly checklist?
