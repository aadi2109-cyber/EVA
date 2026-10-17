# Request BE-to-SEC2-01
Status: OPEN
From: BE · To: SEC-2 · Date: 2026-10-16
## Need
A gateway/provenance decision for the `web.search` `query` argument.
## Why / what breaks without it
Contract 02 §4 lists `web.search` as read-only with `query` NOT a destination arg. With a real search
backend (`WEB_SEARCH_PROVIDER=ollama`) the query leaves the system to a third party, so a hijacked
model can smuggle data out in the query string (e.g. `query="<secret from an email>"`), and the
gateway treats it like any read. BE only caps length (256 chars) and strips control characters;
that limits bandwidth, it does not prevent exfiltration. In eval/mock mode there is no egress.
## Proposed change
Either (a) treat `query` as a destination-like arg: when its provenance is UNTRUSTED (copied from a
tool output rather than typed by the user), apply rule 7 (REQUIRE_APPROVAL / DENY), or (b) accept the
residual risk and document it in doc 04 honest-claims. BE will not add a `destination_args` entry
for `query` without a contract change (tool names/args are part of the contract).
## Answer (recipient fills in)
