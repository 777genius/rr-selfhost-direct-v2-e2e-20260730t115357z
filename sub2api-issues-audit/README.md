# Offline issues adoption audit

Owned directory: `sub2api-issues-audit/` only. No network, credentials, Git writes, upstream edits or engine execution are needed. Python standard library, Python 3.10+.

From repository root:

```sh
python3 sub2api-issues-audit/analyze.py
python3 sub2api-issues-audit/verify.py
```

The CLI can also run from another directory; default inputs resolve relative to this file. `--inputs PATH --output PATH` selects staged input/output. `--cutoff ISO_UTC` changes the analytical reference (must not precede observed events); default is the maximum supplied issue event timestamp, **not** an asserted capture timestamp. `--expect-count` defaults to the contracted 3935 and supports a deliberately different census. Invalid numbers/PR markers/URLs/states fail before reports are written. No dependency install required.

Artifacts:

- `analyze.py`: full-corpus reproducible aggregation; raw titles/bodies/comment text/author identities/configs are never exported.
- `findings.json`: detailed safe metrics, 52 authored reviews, exact issue/comment/source citations, source hashes, limitations and recommendations.
- `dashboard.json`: concise dashboard summary; use `textContent`/escaped templates, not `innerHTML`. JSON metacharacters are escaped for safe embedding; no raw user HTML exists in reports.
- `AUDIT.md`: concise Russian decision and detailed appendix, generated from the same data.
- `TEST-PLAN.md`: concrete proposals for the implementation worker's native transport/lifecycle matrix, all NOT RUN by this lane.
- `reviews.json`, `source-notes.json`, `comment-notes.json`: authored reasoning inputs; distinguish reporter assertion, source mitigation, release claim and missing proof.
- `NEEDED-COMMENTS.json`: prioritized coordinator request, 52 numbers, at most 60. Original 48 were staged and all 66 comments inspected; four additional tool-ID/session cases requested afterward. This file is a request, not a live job handle.
- `VERIFY-REGRESSIONS.md`, `verify.py`, `verification.json`: observable regressions stated before authoring checks, actual complete-corpus CLI verification and artifact fingerprints. These are audit-pipeline PASS results, never Sub2API engine PASS.

Comment staging supports the coordinator's existing envelope:

```json
{
  "fetched_at": "2026-09-30T19:52:15Z",
  "issues": [
    {
      "number": 7633,
      "complete": true,
      "comments": [
        {"id": 5864591789, "html_url": "https://github.com/Wei-Shaw/sub2api/issues/7633#issuecomment-5864591789", "created_at": "2026-09-28T00:00:00Z", "author_association": "NONE", "body": "not exported"}
      ]
    }
  ]
}
```

The example is **schema illustration**, not a receipt or claimed creation timestamp. `complete` is an optional explicit stager assertion; count agreement is separately reconciled against snapshot counts. Numeric-key comment mappings and flat `issue_number` lists can produce metadata, but authored comment-note association currently uses the established `issues` envelope. Association CONTRIBUTOR is not automatically maintainer; OWNER/MEMBER/COLLABORATOR are only metadata hints, not automatic fix verdicts. Raw comments must be interpreted manually into `comment-notes.json` when new evidence arrives. Automated regeneration never declares a fix from closure, keywords or comments alone.

Verification writes scratch copies inside the owned directory and deletes them after subprocess execution; source worktrees stay unchanged. Hostile text uses synthetic sentinels only. Verify after each generation; it independently recomputes counts/date partitions, resolves citations and source hashes, compares CLI outputs, exercises malformed complete datasets, and checks no false live proof. `verification.json` fingerprints generated artifacts, so rerun it after modifying report generation.

Handoff: no commits/push/staging. Git lock preflight tried once; linked-worktree `.git` is a file and index.lock unavailable. No bypass. Coordinator exports owned files and performs mechanical integration using authorized identity. Bifrost evidence and other worker files were preserved. Source pin provenance remains operator-supplied because Git metadata cannot be authenticated here. Each authored source observation now stores the SHA-256 of the bytes actually inspected; regeneration rejects changed or missing source before publication. A changed comment snapshot is marked unreviewed and prior authored comment citations are withheld until manual interpretation is updated. Live receipts/test OAuth identity and four supplementary comment pages are explicit pending inputs, not invented proof.

Continuation validation: a scratch replacement of the inspected OAuth helper originally produced reports with exit code 0. The evidence-freshness regression now rejects that change before publication. Seven verification checks pass; this strengthens audit provenance and does not add engine/runtime proof.
