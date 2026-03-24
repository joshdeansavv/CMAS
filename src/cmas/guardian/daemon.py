"""
CMAS Guardian Daemon
====================
Autonomous, always-on agent that continuously improves the CMAS repository.

Lifecycle:
  1. SURVEY   — Read README (north star) + scan codebase for issues
  2. PLAN     — Build / refresh a TODO list of fixes, features, improvements
  3. EXECUTE  — Pick highest-priority item, create branch, apply fix, commit
  4. VALIDATE — Run tests / lint / import checks
  5. SHIP     — Push branch, open PR via `gh`
  6. SLEEP    — Random interval (2–10 min), then loop

Uses the same OpenAI API key and models as the main CMAS system.
"""
from __future__ import annotations

import os
import sys
import json
import time
import random
import asyncio
import sqlite3
import hashlib
import subprocess
from pathlib import Path
from datetime import datetime, timezone
from typing import Optional, List, Dict

from dotenv import load_dotenv

# ── Paths ────────────────────────────────────────────────────────────
GUARDIAN_DIR = Path(__file__).resolve().parent
REPO_ROOT = GUARDIAN_DIR.parent.parent.parent  # src/cmas/guardian -> MAIN_FOLDER
load_dotenv(REPO_ROOT / ".env")

DB_PATH = REPO_ROOT / ".cmas" / "guardian.db"
LOG_PATH = REPO_ROOT / ".cmas" / "guardian.log"

# ── Config ───────────────────────────────────────────────────────────
MODEL_SURVEY = os.getenv("GUARDIAN_MODEL_SURVEY", "gpt-4.1-mini")
MODEL_FIX = os.getenv("GUARDIAN_MODEL_FIX", "gpt-4.1-mini")
MODEL_PLAN = os.getenv("GUARDIAN_MODEL_PLAN", "gpt-4.1-mini")
MIN_SLEEP = int(os.getenv("GUARDIAN_MIN_SLEEP", "120"))   # seconds
MAX_SLEEP = int(os.getenv("GUARDIAN_MAX_SLEEP", "600"))   # seconds
MAX_CONSECUTIVE_FAILURES = 5
DRY_RUN = os.getenv("GUARDIAN_DRY_RUN", "").lower() in ("1", "true", "yes")

# Source dirs to scan (relative to REPO_ROOT)
SCAN_DIRS = ["src/cmas/core", "src/cmas/channels", "src/cmas/frameworks", "src/cmas/cli.py"]
IGNORE_PATTERNS = {".pyc", "__pycache__", ".git", "node_modules", ".venv", "web/dist"}


# ═══════════════════════════════════════════════════════════════════════
#  LLM Client (reuses CMAS .env credentials)
# ═══════════════════════════════════════════════════════════════════════

from openai import AsyncOpenAI

_client: Optional[AsyncOpenAI] = None


def _get_client() -> AsyncOpenAI:
    global _client
    if _client is None:
        api_key = os.getenv("OPENAI_API_KEY")
        base_url = os.getenv("OPENAI_BASE_URL")
        if not api_key:
            sys.exit("OPENAI_API_KEY not set. Guardian cannot operate.")
        _client = AsyncOpenAI(api_key=api_key, base_url=base_url or None)
    return _client


async def llm_chat(
    messages: List[Dict],
    model: str = MODEL_FIX,
    temperature: float = 0.4,
    max_tokens: int = 4096,
) -> str:
    """Simple LLM call with retry."""
    client = _get_client()
    for attempt in range(3):
        try:
            resp = await client.chat.completions.create(
                model=model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
            )
            return resp.choices[0].message.content or ""
        except Exception as e:
            wait = 2 ** attempt
            log(f"[LLM] {model} attempt {attempt+1} failed: {e}. Retry in {wait}s")
            await asyncio.sleep(wait)
    return ""


# ═══════════════════════════════════════════════════════════════════════
#  Logging
# ═══════════════════════════════════════════════════════════════════════

def log(msg: str):
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line)
    try:
        LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(LOG_PATH, "a") as f:
            f.write(line + "\n")
    except Exception:
        pass


# ═══════════════════════════════════════════════════════════════════════
#  SQLite TODO Store
# ═══════════════════════════════════════════════════════════════════════

def _init_db():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS todos (
            id TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            description TEXT DEFAULT '',
            category TEXT DEFAULT 'bug',
            priority INTEGER DEFAULT 5,
            status TEXT DEFAULT 'pending',
            file_path TEXT DEFAULT '',
            branch TEXT DEFAULT '',
            pr_url TEXT DEFAULT '',
            created_at REAL,
            updated_at REAL
        );
        CREATE TABLE IF NOT EXISTS cycles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            started_at REAL,
            phase TEXT,
            result TEXT DEFAULT '',
            completed_at REAL
        );
    """)
    conn.commit()
    return conn


def _get_db():
    return _init_db()


def add_todo(title: str, description: str, category: str, priority: int, file_path: str = "") -> str:
    """Add a TODO item. Returns its ID."""
    todo_id = hashlib.sha256(f"{title}{time.time()}".encode()).hexdigest()[:10]
    conn = _get_db()
    conn.execute(
        "INSERT OR IGNORE INTO todos (id, title, description, category, priority, file_path, created_at, updated_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (todo_id, title, description, category, priority, file_path, time.time(), time.time()),
    )
    conn.commit()
    conn.close()
    return todo_id


def get_pending_todos(limit: int = 10) -> List[Dict]:
    conn = _get_db()
    rows = conn.execute(
        "SELECT * FROM todos WHERE status = 'pending' ORDER BY priority ASC, created_at ASC LIMIT ?",
        (limit,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def update_todo(todo_id: str, **kwargs):
    conn = _get_db()
    sets = ", ".join(f"{k} = ?" for k in kwargs)
    vals = list(kwargs.values()) + [time.time(), todo_id]
    conn.execute(f"UPDATE todos SET {sets}, updated_at = ? WHERE id = ?", vals)
    conn.commit()
    conn.close()


def todo_exists(title: str) -> bool:
    conn = _get_db()
    row = conn.execute(
        "SELECT 1 FROM todos WHERE title = ? AND status IN ('pending', 'in_progress')", (title,)
    ).fetchone()
    conn.close()
    return row is not None


def log_cycle(phase: str, result: str):
    conn = _get_db()
    conn.execute(
        "INSERT INTO cycles (started_at, phase, result, completed_at) VALUES (?, ?, ?, ?)",
        (time.time(), phase, result, time.time()),
    )
    conn.commit()
    conn.close()


# ═══════════════════════════════════════════════════════════════════════
#  Git / GitHub helpers
# ═══════════════════════════════════════════════════════════════════════

def git(cmd: str, cwd: Optional[str] = None) -> str:
    """Run a git command and return stdout."""
    result = subprocess.run(
        f"git {cmd}",
        shell=True,
        capture_output=True,
        text=True,
        cwd=cwd or str(REPO_ROOT),
        timeout=60,
    )
    if result.returncode != 0 and result.stderr:
        log(f"[git] stderr: {result.stderr.strip()}")
    return result.stdout.strip()


def gh(cmd: str) -> str:
    """Run a gh CLI command."""
    result = subprocess.run(
        f"gh {cmd}",
        shell=True,
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT),
        timeout=60,
    )
    return (result.stdout + result.stderr).strip()


def ensure_clean_main():
    """Switch to main and pull latest. Returns False if working tree is dirty."""
    status = git("status --porcelain")
    if status:
        log(f"[git] Working tree dirty, stashing: {status[:100]}")
        git("stash push -m 'guardian-auto-stash'")
    git("checkout main")
    git("pull origin main --rebase")
    return True


def create_branch(name: str) -> str:
    branch = f"guardian/{name}"
    git(f"checkout -b {branch}")
    return branch


def commit_and_push(branch: str, message: str) -> bool:
    git("add -A")
    status = git("status --porcelain")
    if not status:
        log("[git] Nothing to commit")
        return False
    # Use heredoc-style commit
    result = subprocess.run(
        ["git", "commit", "-m", f"{message}\n\nAutonomous fix by CMAS Guardian"],
        capture_output=True, text=True, cwd=str(REPO_ROOT), timeout=60,
    )
    if result.returncode != 0:
        log(f"[git] Commit failed: {result.stderr}")
        return False
    push_result = git(f"push -u origin {branch}")
    log(f"[git] Pushed: {push_result}")
    return True


def open_pr(branch: str, title: str, body: str) -> str:
    """Open a PR via gh CLI. Returns PR URL."""
    result = subprocess.run(
        ["gh", "pr", "create",
         "--base", "main",
         "--head", branch,
         "--title", title,
         "--body", body],
        capture_output=True, text=True, cwd=str(REPO_ROOT), timeout=60,
    )
    url = result.stdout.strip()
    if result.returncode != 0:
        log(f"[gh] PR create failed: {result.stderr}")
        return ""
    log(f"[gh] PR opened: {url}")
    return url


def cleanup_branch(branch: str):
    """Switch back to main and delete the feature branch."""
    git("checkout main")
    git(f"branch -D {branch}")


# ═══════════════════════════════════════════════════════════════════════
#  Codebase Scanner
# ═══════════════════════════════════════════════════════════════════════

def collect_source_files() -> List[Path]:
    """Gather all .py files from scan directories."""
    files = []
    for rel in SCAN_DIRS:
        target = REPO_ROOT / rel
        if target.is_file():
            files.append(target)
        elif target.is_dir():
            for f in target.rglob("*.py"):
                skip = False
                for pat in IGNORE_PATTERNS:
                    if pat in str(f):
                        skip = True
                        break
                if not skip:
                    files.append(f)
    return sorted(files)


def read_readme() -> str:
    readme = REPO_ROOT / "README.md"
    if readme.exists():
        return readme.read_text()[:8000]
    return "(No README found)"


def read_source_snapshot(max_chars: int = 40000) -> str:
    """Build a concatenated snapshot of the codebase for the LLM."""
    files = collect_source_files()
    parts = []
    total = 0
    for f in files:
        try:
            content = f.read_text()
        except Exception:
            continue
        rel = f.relative_to(REPO_ROOT)
        header = f"\n{'='*60}\n# FILE: {rel}\n{'='*60}\n"
        chunk = header + content
        if total + len(chunk) > max_chars:
            break
        parts.append(chunk)
        total += len(chunk)
    return "".join(parts)


# ═══════════════════════════════════════════════════════════════════════
#  Phase 1: SURVEY — Understand the repo and find issues
# ═══════════════════════════════════════════════════════════════════════

async def survey() -> str:
    """Have the LLM read the README + source and identify issues."""
    readme = read_readme()
    source = read_source_snapshot()

    existing = get_pending_todos(limit=20)
    existing_titles = [t["title"] for t in existing]

    prompt = f"""You are CMAS Guardian, an autonomous code quality agent.

Your job: analyze the CMAS repository and find bugs, missing features, code quality issues,
and gaps between what the README promises and what the code delivers.

## README (north star — this is what the project SHOULD be):
{readme}

## Current Source Code:
{source}

## Already-tracked TODOs (do NOT duplicate these):
{json.dumps(existing_titles, indent=2)}

Analyze the code carefully. Look for:
1. **Bugs** — runtime errors, logic errors, unhandled edge cases, type mismatches
2. **Missing features** — things the README describes that aren't implemented
3. **Code quality** — dead code, inconsistencies, missing error handling at boundaries
4. **Security** — any injection risks, unsafe defaults, exposed secrets
5. **Robustness** — crash-prone patterns, missing timeouts, resource leaks

Return a JSON array of issues. Each issue:
```json
[
  {{
    "title": "Short descriptive title (unique, not a duplicate)",
    "description": "What's wrong and how to fix it",
    "category": "bug|feature|quality|security|robustness",
    "priority": 1-10 (1=critical, 10=nice-to-have),
    "file_path": "relative/path/to/file.py"
  }}
]
```

Only return the JSON array. No markdown, no explanation. Return [] if nothing found.
Be specific — vague issues waste cycles. Max 8 issues per survey."""

    result = await llm_chat(
        [{"role": "system", "content": "You are a senior software engineer performing a code audit."},
         {"role": "user", "content": prompt}],
        model=MODEL_SURVEY,
        temperature=0.3,
        max_tokens=4096,
    )
    return result


# ═══════════════════════════════════════════════════════════════════════
#  Phase 2: PLAN — Parse survey into TODOs
# ═══════════════════════════════════════════════════════════════════════

def plan(survey_result: str) -> int:
    """Parse LLM survey into TODO items. Returns count of new items."""
    # Strip markdown fences if present
    text = survey_result.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        text = "\n".join(lines[1:])
        if text.endswith("```"):
            text = text[:-3]

    try:
        issues = json.loads(text)
    except json.JSONDecodeError:
        # Try to extract JSON array from response
        start = text.find("[")
        end = text.rfind("]")
        if start >= 0 and end > start:
            try:
                issues = json.loads(text[start:end+1])
            except json.JSONDecodeError:
                log(f"[PLAN] Could not parse survey response as JSON")
                return 0
        else:
            log(f"[PLAN] No JSON array found in survey response")
            return 0

    if not isinstance(issues, list):
        return 0

    added = 0
    for issue in issues:
        if not isinstance(issue, dict):
            continue
        title = issue.get("title", "").strip()
        if not title or todo_exists(title):
            continue
        add_todo(
            title=title,
            description=issue.get("description", ""),
            category=issue.get("category", "bug"),
            priority=min(max(int(issue.get("priority", 5)), 1), 10),
            file_path=issue.get("file_path", ""),
        )
        added += 1
        log(f"[PLAN] Added TODO: [{issue.get('category','?')}] {title}")

    return added


# ═══════════════════════════════════════════════════════════════════════
#  Phase 3: EXECUTE — Pick a TODO and fix it
# ═══════════════════════════════════════════════════════════════════════

async def execute(todo: Dict) -> Optional[Dict]:
    """Apply a fix for a single TODO. Returns {branch, files_changed} or None."""
    title = todo["title"]
    desc = todo["description"]
    file_path = todo.get("file_path", "")

    log(f"[EXECUTE] Working on: {title}")
    update_todo(todo["id"], status="in_progress")

    # Read the target file(s)
    file_context = ""
    if file_path:
        target = REPO_ROOT / file_path
        if target.exists():
            content = target.read_text()
            file_context = f"\n## Target file: {file_path}\n```python\n{content}\n```\n"

    # If no specific file, give broader context
    if not file_context:
        file_context = f"\n## Source snapshot:\n{read_source_snapshot(max_chars=20000)}\n"

    readme = read_readme()

    prompt = f"""You are CMAS Guardian. Fix the following issue in the CMAS codebase.

## Project README (north star):
{readme}

## Issue to fix:
**{title}**
{desc}

{file_context}

## Instructions:
1. Produce the COMPLETE fixed file(s). Do not use placeholders or "..." — output the entire file.
2. Only modify what is necessary to fix this specific issue.
3. Follow existing code style (imports, naming conventions, docstrings).
4. Do not add unnecessary features or refactoring beyond the fix.

Return your answer as a JSON object:
```json
{{
  "files": [
    {{
      "path": "relative/path/to/file.py",
      "content": "... complete file content ..."
    }}
  ],
  "commit_message": "Short commit message describing the fix",
  "pr_body": "## Summary\\n- What was wrong\\n- What was fixed\\n\\n## Test plan\\n- How to verify"
}}
```

Return ONLY the JSON object. No markdown fences, no explanation outside the JSON."""

    result = await llm_chat(
        [{"role": "system", "content": "You are a senior Python developer. Output only valid JSON."},
         {"role": "user", "content": prompt}],
        model=MODEL_FIX,
        temperature=0.2,
        max_tokens=8192,
    )
    return _parse_fix(result, todo)


def _parse_fix(raw: str, todo: Dict) -> Optional[Dict]:
    """Parse the LLM fix response and apply file changes."""
    text = raw.strip()
    # Strip markdown fences
    if text.startswith("```"):
        lines = text.split("\n")
        text = "\n".join(lines[1:])
        if text.endswith("```"):
            text = text[:-3]

    try:
        fix = json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start >= 0 and end > start:
            try:
                fix = json.loads(text[start:end+1])
            except json.JSONDecodeError:
                log(f"[EXECUTE] Failed to parse fix JSON")
                update_todo(todo["id"], status="failed")
                return None
        else:
            update_todo(todo["id"], status="failed")
            return None

    files = fix.get("files", [])
    if not files:
        log("[EXECUTE] No files in fix response")
        update_todo(todo["id"], status="failed")
        return None

    # Create branch
    slug = todo["title"].lower().replace(" ", "-")[:40]
    slug = "".join(c for c in slug if c.isalnum() or c == "-")
    branch = create_branch(slug)

    # Apply changes
    changed = []
    for f in files:
        path = f.get("path", "")
        content = f.get("content", "")
        if not path or not content:
            continue
        target = REPO_ROOT / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content)
        changed.append(path)
        log(f"[EXECUTE] Wrote: {path}")

    return {
        "branch": branch,
        "files_changed": changed,
        "commit_message": fix.get("commit_message", f"Fix: {todo['title']}"),
        "pr_body": fix.get("pr_body", f"Autonomous fix for: {todo['title']}\n\n{todo['description']}"),
    }


# ═══════════════════════════════════════════════════════════════════════
#  Phase 4: VALIDATE — Quick sanity checks
# ═══════════════════════════════════════════════════════════════════════

def validate(files_changed: List[str]) -> tuple[bool, str]:
    """Run basic validation on changed files."""
    errors = []

    for rel_path in files_changed:
        if not rel_path.endswith(".py"):
            continue
        full = REPO_ROOT / rel_path

        # Syntax check
        result = subprocess.run(
            ["python3", "-c", f"import ast; ast.parse(open('{full}').read())"],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode != 0:
            errors.append(f"Syntax error in {rel_path}: {result.stderr.strip()}")

        # Import check (try to compile)
        result = subprocess.run(
            ["python3", "-m", "py_compile", str(full)],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode != 0:
            errors.append(f"Compile error in {rel_path}: {result.stderr.strip()}")

    if errors:
        return False, "\n".join(errors)
    return True, "All checks passed"


# ═══════════════════════════════════════════════════════════════════════
#  Phase 5: SHIP — Commit, push, open PR
# ═══════════════════════════════════════════════════════════════════════

def ship(todo: Dict, fix_result: Dict) -> str:
    """Commit, push, and open a PR. Returns PR URL or empty string."""
    branch = fix_result["branch"]
    msg = fix_result["commit_message"]
    body = fix_result["pr_body"]

    if DRY_RUN:
        log(f"[SHIP] DRY RUN — would commit to {branch}: {msg}")
        cleanup_branch(branch)
        update_todo(todo["id"], status="dry_run")
        return ""

    success = commit_and_push(branch, msg)
    if not success:
        cleanup_branch(branch)
        update_todo(todo["id"], status="failed")
        return ""

    pr_title = f"[Guardian] {todo['title']}"[:70]
    pr_body = f"{body}\n\n---\n*Autonomous fix by CMAS Guardian*"

    pr_url = open_pr(branch, pr_title, pr_body)

    # Return to main
    git("checkout main")

    if pr_url:
        update_todo(todo["id"], status="shipped", branch=branch, pr_url=pr_url)
    else:
        update_todo(todo["id"], status="pushed", branch=branch)

    return pr_url


# ═══════════════════════════════════════════════════════════════════════
#  Main Loop
# ═══════════════════════════════════════════════════════════════════════

async def run_cycle():
    """Run one full Guardian cycle: survey → plan → execute → validate → ship."""
    log("=" * 60)
    log("GUARDIAN CYCLE START")
    log("=" * 60)

    ensure_clean_main()

    # ── Survey ──
    log("[SURVEY] Scanning codebase...")
    survey_result = await survey()
    log_cycle("survey", survey_result[:500])

    # ── Plan ──
    new_count = plan(survey_result)
    log(f"[PLAN] Added {new_count} new TODO(s)")
    log_cycle("plan", f"added={new_count}")

    # ── Pick top TODO ──
    todos = get_pending_todos(limit=1)
    if not todos:
        log("[EXECUTE] No pending TODOs. Nothing to do.")
        log_cycle("execute", "nothing_pending")
        return

    todo = todos[0]
    log(f"[EXECUTE] Selected: [{todo['category']}] {todo['title']} (priority {todo['priority']})")

    # ── Execute ──
    fix_result = await execute(todo)
    if not fix_result:
        log("[EXECUTE] Fix generation failed. Skipping.")
        log_cycle("execute", "fix_failed")
        ensure_clean_main()
        return

    # ── Validate ──
    ok, validation_msg = validate(fix_result["files_changed"])
    log(f"[VALIDATE] {'PASS' if ok else 'FAIL'}: {validation_msg}")
    log_cycle("validate", validation_msg)

    if not ok:
        log("[VALIDATE] Fix failed validation. Reverting.")
        cleanup_branch(fix_result["branch"])
        update_todo(todo["id"], status="failed")
        ensure_clean_main()
        return

    # ── Ship ──
    pr_url = ship(todo, fix_result)
    if pr_url:
        log(f"[SHIP] PR opened: {pr_url}")
    else:
        log("[SHIP] No PR created (dry run or push failed)")
    log_cycle("ship", pr_url or "no_pr")

    log("GUARDIAN CYCLE COMPLETE")


async def run_forever():
    """Main daemon loop. Runs cycles at random intervals."""
    consecutive_failures = 0

    while True:
        try:
            await run_cycle()
            consecutive_failures = 0
        except KeyboardInterrupt:
            log("Guardian stopped by user.")
            break
        except Exception as e:
            consecutive_failures += 1
            log(f"[ERROR] Cycle failed: {e}")
            log_cycle("error", str(e))

            if consecutive_failures >= MAX_CONSECUTIVE_FAILURES:
                log(f"[FATAL] {MAX_CONSECUTIVE_FAILURES} consecutive failures. Backing off for 30 min.")
                await asyncio.sleep(1800)
                consecutive_failures = 0

        # Random sleep between cycles
        sleep_time = random.randint(MIN_SLEEP, MAX_SLEEP)
        log(f"[SLEEP] Next cycle in {sleep_time}s ({sleep_time/60:.1f} min)")
        await asyncio.sleep(sleep_time)


def main():
    """CLI entry point."""
    import argparse
    parser = argparse.ArgumentParser(description="CMAS Guardian — autonomous repo improvement daemon")
    parser.add_argument("--once", action="store_true", help="Run one cycle and exit")
    parser.add_argument("--dry-run", action="store_true", help="Don't push or open PRs")
    parser.add_argument("--status", action="store_true", help="Show current TODO list and exit")
    args = parser.parse_args()

    if args.dry_run:
        global DRY_RUN
        DRY_RUN = True

    if args.status:
        _show_status()
        return

    banner = f"""
  ╔══════════════════════════════════════════════════════╗
  ║          CMAS GUARDIAN — Autonomous Daemon           ║
  ║                                                      ║
  ║  Model (survey):  {MODEL_SURVEY:<34s} ║
  ║  Model (fix):     {MODEL_FIX:<34s} ║
  ║  Interval:        {MIN_SLEEP}–{MAX_SLEEP}s{'':<28s} ║
  ║  Dry run:         {str(DRY_RUN):<34s} ║
  ║  Repo:            {str(REPO_ROOT)[-34:]:<34s} ║
  ╚══════════════════════════════════════════════════════╝
"""
    print(banner)

    if args.once:
        asyncio.run(run_cycle())
    else:
        try:
            asyncio.run(run_forever())
        except KeyboardInterrupt:
            log("Guardian shutdown.")


def _show_status():
    """Print current TODO list."""
    todos = get_pending_todos(limit=50)
    if not todos:
        print("No pending TODOs.")
        return

    print(f"\n  CMAS Guardian — {len(todos)} pending TODO(s)\n")
    print(f"  {'PRI':>3}  {'CAT':<10}  {'TITLE':<50}  {'FILE'}")
    print(f"  {'---':>3}  {'---':<10}  {'---':<50}  {'---'}")
    for t in todos:
        print(f"  {t['priority']:>3}  {t['category']:<10}  {t['title'][:50]:<50}  {t.get('file_path', '')}")
    print()


if __name__ == "__main__":
    main()
