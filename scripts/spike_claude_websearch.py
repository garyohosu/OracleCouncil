"""Spike (X-2, hikitsugi.md §4-4): can Claude Code's built-in WebSearch tool
become a SearchProvider (X-1) candidate?

This does NOT touch the main adapter code. It is a standalone, throwaway
probe that spends exactly one live Claude call and reports findings so a
human can decide whether to build CliSearchProvider for real.

Checks (per the reviewer's spec):
  1. Does the CLI accept "WebSearch" as a --tools value?
  2. Does the isolated working directory stay empty (no file writes / shell
     execution happened, even though only WebSearch was allowed)?
  3. Can the model return structured url/title/snippet JSON?
  4. Can each reported URL actually be re-fetched by SafeHttpFetcher (the
     same boundary the real EvidenceProvider must cross, S-1)?
  5. Unreachable URLs are reported as such, never silently treated as
     fetchable/verified (SPEC §10.1: Oracle Council must independently
     access a document before it counts as evidence).

Usage:
    python scripts/spike_claude_websearch.py
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

# Windows consoles default stdout to cp932, which cannot encode characters
# common in real web snippets (em dashes, curly quotes, etc.). A crash here
# would lose an already-completed live call's results, so results are also
# written to a file (below) before this is ever attempted.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

REPO_ROOT = Path(__file__).resolve().parent.parent
OUTPUT_PATH = REPO_ROOT / "spike_claude_websearch_result.json"
sys.path.insert(0, str(REPO_ROOT / "src"))

from oracle_council.adapters.claude import _extract_json_object  # noqa: E402
from oracle_council.evidence import EvidenceFetchError, SafeHttpFetcher  # noqa: E402

PROMPT = (
    "Search the web for sources supporting this claim: "
    '"Python\'s built-in container types include list and dict, and both are mutable."\n\n'
    "Respond with ONLY a single valid JSON object, no markdown code fences, no other "
    "text, matching this shape: "
    '{"sources": [{"url": "<string>", "title": "<string>", "snippet": "<string>"}]}. '
    "Include 1 to 3 sources with real URLs found via search."
)


def run_spike() -> dict:
    findings: dict = {}
    with tempfile.TemporaryDirectory() as workdir:
        workdir_path = Path(workdir)
        before = set(workdir_path.iterdir())

        cmd = [
            "claude", "-p", PROMPT,
            "--tools", "WebSearch",
            "--output-format", "json",
            "--no-session-persistence",
            "--safe-mode",
        ]
        result = subprocess.run(
            cmd, capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=180, cwd=workdir, stdin=subprocess.DEVNULL, shell=False,
        )

        after = set(workdir_path.iterdir())
        findings["files_created_or_modified"] = sorted(p.name for p in (after - before))
        findings["cwd_stayed_clean"] = not findings["files_created_or_modified"]
        findings["returncode"] = result.returncode

        combined_lower = (result.stdout + result.stderr).lower()
        tool_rejected = any(
            phrase in combined_lower
            for phrase in ("unknown tool", "invalid tool", "not a valid tool", "unrecognized tool")
        )
        findings["tool_name_rejected"] = tool_rejected
        if tool_rejected:
            findings["raw_stdout_head"] = result.stdout[:500]
            findings["raw_stderr_head"] = result.stderr[:500]
            return findings

        try:
            envelope = json.loads(result.stdout.strip())
        except json.JSONDecodeError:
            findings["envelope_parse_error"] = True
            findings["raw_stdout_head"] = result.stdout[:1000]
            findings["raw_stderr_head"] = result.stderr[:500]
            return findings

        findings["envelope_is_error"] = envelope.get("is_error") if isinstance(envelope, dict) else None
        result_text = envelope.get("result", "") if isinstance(envelope, dict) else result.stdout

        try:
            payload = _extract_json_object(result_text)
            sources = payload.get("sources", [])
        except json.JSONDecodeError as exc:
            findings["structured_output_error"] = str(exc)
            findings["raw_result_text_head"] = result_text[:1000]
            return findings

        findings["structured_output_ok"] = bool(sources)
        findings["source_count"] = len(sources)

        # Re-fetch every reported URL through the exact same boundary the
        # real EvidenceProvider is required to use (S-1). A URL the model
        # names but Oracle Council cannot independently retrieve must show
        # up as unfetchable here, never silently as verified (SPEC §10.1).
        fetcher = SafeHttpFetcher()
        fetch_results = []
        for source in sources:
            url = source.get("url", "")
            entry = {"url": url, "title": source.get("title", "")}
            try:
                document = fetcher.fetch(url)
                entry["fetchable"] = True
                entry["content_type"] = document.content_type
                entry["content_length"] = len(document.content)
            except EvidenceFetchError as exc:
                entry["fetchable"] = False
                entry["fetch_error"] = exc.code
            fetch_results.append(entry)
        findings["fetch_results"] = fetch_results
        findings["fetchable_count"] = sum(1 for r in fetch_results if r.get("fetchable"))

    return findings


if __name__ == "__main__":
    outcome = run_spike()
    # Durable copy first: a live call already spent quota to produce this
    # data, so it must survive even if stdout printing itself fails.
    OUTPUT_PATH.write_text(json.dumps(outcome, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Results written to {OUTPUT_PATH}", file=sys.stderr)
    print(json.dumps(outcome, indent=2, ensure_ascii=False))
