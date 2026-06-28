"""Application Agent — Playwright browser automation with evidence capture.

Safety model:
  - URL is SSRF-guarded (also blocks LinkedIn) before any navigation.
  - Default mode is PREPARE-ONLY: navigate, best-effort fill, upload resume,
    and screenshot — but DO NOT click submit. Submission happens only when the
    caller explicitly passes submit=True (after human approval).
  - Every run captures screenshots + the exact payload as auditable evidence.

Uses the Playwright SYNC API, which is safe inside FastAPI's threadpool (sync
endpoints run without a running event loop).
"""
from __future__ import annotations

from pathlib import Path

from app.config import settings
from app.security import assert_safe_url

# Best-effort selectors for common application fields.
_FIELD_SELECTORS = {
    "email": ["input[type=email]", "input[name*=email i]", "input[id*=email i]"],
    "name": ["input[name*=name i]", "input[id*=name i]", "input[placeholder*=name i]"],
    "phone": ["input[type=tel]", "input[name*=phone i]", "input[id*=phone i]"],
}


def _fill_first(page, selectors: list[str], value: str) -> bool:
    for sel in selectors:
        try:
            el = page.query_selector(sel)
            if el and el.is_visible():
                el.fill(value)
                return True
        except Exception:  # noqa: BLE001 - best effort, never fatal
            continue
    return False


def apply(
    *,
    application_id: int,
    job_url: str,
    resume_file_path: str | None,
    applicant: dict,
    submit: bool = False,
) -> dict:
    """Drive the browser. Returns {events, evidence, submitted, payload}."""
    assert_safe_url(job_url)  # raises UnsafeURLError on internal/loopback/LinkedIn

    settings.ensure_dirs()
    evidence_dir = Path(settings.evidence_dir)
    events: list[str] = []
    evidence: list[dict] = []

    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context()
        page = context.new_page()
        try:
            page.goto(job_url, timeout=45000, wait_until="domcontentloaded")
            events.append(f"navigated to {job_url}")

            landing = evidence_dir / f"app{application_id}_1_landing.png"
            page.screenshot(path=str(landing), full_page=True)
            evidence.append({"kind": "screenshot", "file_path": str(landing)})

            # best-effort field fill
            for field, selectors in _FIELD_SELECTORS.items():
                val = applicant.get(field)
                if val and _fill_first(page, selectors, val):
                    events.append(f"filled {field}")

            # resume upload (best effort)
            if resume_file_path and Path(resume_file_path).exists():
                try:
                    file_input = page.query_selector("input[type=file]")
                    if file_input:
                        file_input.set_input_files(resume_file_path)
                        events.append("uploaded resume file")
                except Exception:  # noqa: BLE001
                    events.append("resume upload skipped (no file input found)")

            filled = evidence_dir / f"app{application_id}_2_filled.png"
            page.screenshot(path=str(filled), full_page=True)
            evidence.append({"kind": "screenshot", "file_path": str(filled)})

            submitted = False
            if submit:
                btn = (
                    page.query_selector("button[type=submit]")
                    or page.query_selector("input[type=submit]")
                    or page.get_by_role("button", name="Submit").first
                    or page.get_by_role("button", name="Apply").first
                )
                if btn:
                    btn.click()
                    page.wait_for_timeout(2500)
                    submitted = True
                    events.append("clicked submit")
                    confirm = evidence_dir / f"app{application_id}_3_submitted.png"
                    page.screenshot(path=str(confirm), full_page=True)
                    evidence.append({"kind": "screenshot", "file_path": str(confirm)})
                else:
                    events.append("submit requested but no submit button found")
        finally:
            context.close()
            browser.close()

    return {
        "events": events,
        "evidence": evidence,
        "submitted": submitted if submit else False,
        "payload": applicant,
    }
