# Collaborative development

Start with the [branch map](docs/BRANCHES.md) and [current development guide](docs/DEVELOPMENT_GUIDE.md). Both humans and AI agents should establish the current branch and working-tree state before editing. Agent-specific payment safeguards are in [AGENTS.md](AGENTS.md).

## Pick the right base

`master` contains the earlier retail checkout demo. `slice/1-persistent-workshop-checkout` is the user-accepted development base for `slice/2-group-coordination`, which adds only group coordination and remains a review candidate. Neither workshop branch is represented as merged into `master` or externally architecture-approved.

For an authorized Slice 1 correction, create an isolated branch from its remote tip:

```bash
git fetch origin
git switch -c fix/slice1-describe-the-problem origin/slice/1-persistent-workshop-checkout
```

Use an approved base for later work; update `docs/BRANCHES.md` whenever a new slice is delivered or acceptance changes. The current user authorized Slice 3 integration, a guided UI redesign and optional on-device AI; see README and Aarya_changes.md for current scope. Preserve unfinished work before switching branches; never discard someone else's changes to get a clean checkout.

## Keep changes reviewable

- One branch addresses one concrete outcome. Split unrelated payment, SDK migration, UI and product changes.
- Use commits such as `feat(checkout): persist workshop purchases`, `fix(checkout): preserve unresolved attempts`, `docs(collaboration): clarify branch scope`, or `test(checkout): cover expired unapproved orders`.
- Follow the PR template: problem/result, branch/base, scope boundaries, verification and evidence provenance, storage/migration effects, limitations and review status.
- For parallel contributors, agree on file ownership before editing. Shared schema/payment orchestration changes need a single integration owner and explicit integration review.
- Do not force-push shared branches without an explicit team decision. Push one named branch; never `git push --all`, especially with `original-history-backup` present locally.

## Validate before handoff

Use the README's pinned dependency setup and run:

```bash
python -m unittest discover -s tests -v
python -m pip check
git diff --check
git status --short
git diff --cached --stat
```

Use `.venv\Scripts\python.exe` on Windows if the environment is not activated. Stage intentional paths; inspect staged files, because unstaged `git diff --stat` omits untracked files. Confirm `.env`, databases and local artifacts are ignored and unstaged.

GitHub CI installs pinned dependencies and runs mocked tests without PayPal credentials. A passing CI run does not prove Sandbox settlement, browser behavior or hosted PostgreSQL compatibility. Keep manual user-observed results distinct from independent verification.

## Review and integration

Opening/publishing a branch is not acceptance. The user accepted Slice 1 as a development base; Slice 2 still requires review. An authorized maintainer separately decides whether to merge a reviewed change. Do not alter the GitHub default branch or branch protection as part of a normal contribution. No hosting service, secret configuration or automatic deployment is provided by this workflow.

The repository still needs a team-selected license before any submission requiring an open-source license. This guide does not choose a license or claim the complete hackathon product is shipped.
