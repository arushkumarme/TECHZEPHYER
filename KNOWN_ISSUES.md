# NetCoop AI — Known Issues and Open Questions

| ID | Since | Issue | Impact | Status |
|---|---|---|---|---|
| KI-01 | M0 | Generator `queue_drops` / `interface_errors` interval semantics (per-sample vs cumulative) unknown | Trend analysis on counters is interpretive; stated as a limitation | OPEN (cannot be resolved from the code) |
| KI-02 | M0 | Generator has no topology, wireless, DNS/DHCP, memory, throughput | Topology is team-authored synthetic; weak Wi-Fi not diagnosable; DNS/DHCP only via labelled probe input | ACCEPTED (ID-04, ID-06) |
| KI-03 | M0 | Two evaluation lists (doc 00 D-01) remain unresolved | Dashboard priority | OPEN — following SRC-1 |
| KI-04 | M0 | Thresholds tuned on the same generator that produces test data (circularity, doc 08 §8) | High scenario accuracy shows consistency, not real-world skill | OPEN — mitigated by team-authored variants, stated in README |
| KI-05 | M13 | No real LLM provider configured (decision D-07 open: provider, key, venue internet) | LLM features run only with the null/static providers; core unaffected (CD-1) | OPEN — owner decision; adding a provider = one class implementing `LLMProvider` |
