# Methodology

Prefer minimal GarageBand projects where one property changes at a time. Compare corresponding ZIP members after decompression, record added/removed members, and compare structured plists before interpreting raw offsets. For binary payloads, record length and changed ranges, then test candidate integer/float interpretations against several controlled values. Serialized fields can shift, so byte offsets alone are not evidence of a stable field.

Use IDA MCP to inspect raw bytes and related binary components when useful. Reproduce each format claim with Python where practical. IDA database annotations are temporary research aids; parser behavior and findings must be reproducible from the repository.

Do not infer region or note timing from summary duration, cache images, or resource lists. Preserve unknown payload bytes and report unsupported structures.
