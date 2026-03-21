# Contributing to CMAS

Thank you for your interest in contributing. CMAS is a source-available project under the PolyForm Noncommercial License 1.0.0. By submitting a contribution, you agree that your work is licensed under the same terms.

---

## Before You Start

- Open an issue first for anything significant — a bug fix, new feature, refactor, or architectural change. This prevents duplicated effort and lets us align before you spend time writing code.
- For small fixes (typos, broken links, obvious bugs), a PR without a prior issue is fine.

## How to Contribute

1. Fork the repository.
2. Create a branch from `main` with a descriptive name:
   ```
   git checkout -b fix/gateway-rate-limit-edge-case
   git checkout -b feat/whatsapp-channel-improvements
   ```
3. Make your changes. Keep commits focused — one logical change per commit.
4. Test locally:
   ```bash
   ./setup.sh
   ./start.sh
   ```
5. Open a pull request against `main`. Fill out the PR template completely.

## What We Accept

- Bug fixes with a clear reproduction case
- Performance improvements with measurable impact
- Documentation improvements
- New channel integrations (Discord, Slack, etc.)
- Improvements to the Brain modules backed by reasoning or research
- Security fixes (see [SECURITY.md](.github/SECURITY.md) for reporting vulnerabilities)

## What We Will Not Merge

- Changes that add telemetry, analytics, or any form of data collection
- Changes that weaken the Gateway access controls or audit logging
- New dependencies without justification
- Code that significantly increases complexity without proportional benefit
- Anything that bypasses the cognitive loop or memory system for shortcuts
- Commercial integrations or features (this is a noncommercial project)

## Code Standards

- Match the existing style of the file you are editing — no reformatting unrelated code.
- No commented-out code, debug prints, or leftover TODOs in submitted work.
- No hardcoded secrets, API keys, file paths, or environment assumptions.
- If your change touches the Gateway, Memory, or Orchestrator, explain the architectural reasoning in the PR description.

## License Agreement

This project is **not open source** in the OSI sense. It is source-available under the PolyForm Noncommercial License 1.0.0.

By submitting a pull request, you:
- Confirm you have the right to submit the code under these terms
- Agree your contribution is licensed under the PolyForm Noncommercial License 1.0.0
- Understand that the project owner retains the right to use contributions in any future commercial license

If you are not comfortable with these terms, please do not submit a contribution.

---

Questions? Open a GitHub Discussion or reach out to the project owner directly.
