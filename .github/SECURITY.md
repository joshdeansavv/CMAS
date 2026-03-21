# Security Policy

## Reporting a Vulnerability

If you discover a security vulnerability in CMAS, do not open a public issue.

Report it privately by emailing the project owner directly (see the GitHub profile for contact information) or by using GitHub's private vulnerability reporting feature on this repository.

Please include:
- A clear description of the vulnerability
- Steps to reproduce
- Potential impact
- Any suggested fix if you have one

You will receive a response within 72 hours. We take security reports seriously and will work to address confirmed vulnerabilities promptly.

## Scope

Security reports are in scope for:
- The Python backend (`src/cmas/`)
- The setup and start scripts (`setup.sh`, `start.sh`)
- Anything that could expose API keys, execute unintended code, or allow unauthorized access

Out of scope:
- The web frontend (React/Vite app) for issues that only affect a locally-running instance
- Theoretical attacks requiring physical access to the machine running CMAS
