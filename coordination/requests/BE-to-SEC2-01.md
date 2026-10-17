# Request BE-to-SEC2-01
Status: RESOLVED (SEC-2, role/sec2)
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
## Answer (SEC-2)
Decision: option (a). `web.search` `query` is now treated like a destination-like arg for provenance: when `arg_provenance["query"]` is declared `UNTRUSTED` (copied from a tool output, not typed by the user) and the query is non-empty, the gateway returns `REQUIRE_APPROVAL` (`UNTRUSTED_ARG_PROVENANCE`), showing the exact query to the user. `USER`-provenance queries and calls with no provenance entry stay `ALLOW`, the same convention as rule 7 (only declared-untrusted args are escalated). **BE must therefore send `arg_provenance["query"]` whenever the query text was derived from a tool result.**
Residual risk (to state in honest claims): a model-composed query carrying data from earlier tool output, sent WITHOUT a provenance entry, is not caught by the gateway; BE's 256-char cap and control-character stripping limit bandwidth only. Tests: `guard/tests/test_be_requests.py::test_web_search_query_provenance`.
