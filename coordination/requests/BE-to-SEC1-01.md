# Request BE-to-SEC1-01
Status: OPEN
From: BE · To: SEC-1 · Date: 2026-10-16

## Need
The detector must not sanitise a bare email address (e.g. the `from` field of an email).

## Why / what breaks without it
With the real DetPipeline merged (role/sec2 into role/backend), any scanned text that contains an
email address is replaced by `[CONTENT SANITISED]`. Repro through the Guard facade (`scan_tool_result`,
one field, `Trust.UNTRUSTED`, `SourceType.EMAIL`):

| field | text | result |
|---|---|---|
| `from` | `frank@corp.com` | removed=1, disposition=sanitized |
| `from` | `Frank <frank@corp.com>` | removed=1, disposition=sanitized |
| `body` | `frank@corp.com` | removed=1, disposition=sanitized |
| `date` | `2026-10-04T10:00:00Z` | pass |
| `body` | benign "Please pay by Friday ..." text | pass |

`gmail.read` always sends `from` as its own scan field, so EVERY email read loses its sender, and the
benign scenarios S10 ("Please pay by Friday") and S11 (benign doc that quotes an injection) fail
acceptance doc 04 ("not blocked" / "not over-blocked"). It also blanks `Dear Customer,` style greetings
in `msg-001.body` (a second false positive: `[CONTENT SANITISED]` replaces the first line).
Likely cause: an exfil-destination / "send to <address>" rule firing on any address, without an
instruction verb around it.

## Proposed change
Only flag an address when it is the object of an instruction (send/forward/email/cc ... to <addr>),
and never flag header-like fields (`from`, `to`, `cc`, `date`, `subject`) on their own. Add
`frank@corp.com`, `Dear Customer,` and the S10/S11 mailbox messages (`msg-023`, `msg-026`) to the benign
hard-negative set.

## Test
BE pins S10 and S11 as strict xfail in `agent/backend/tests/test_eval_hooks.py`
(`test_run_scenario_full_passes[S10|S11]`). When your fix lands they XPASS and fail the suite:
delete the xfail marks.
## Answer (recipient fills in)
