# Methodology

Prefer minimal GarageBand projects where one property changes at a time. Compare corresponding ZIP members after decompression, record added/removed members, and compare structured plists before interpreting raw offsets. For binary payloads, record length and changed ranges, then test candidate integer/float interpretations against several controlled values. Serialized fields can shift, so byte offsets alone are not evidence of a stable field.

Use IDA MCP to inspect raw bytes and related binary components when useful. Reproduce each format claim with Python where practical. IDA database annotations are temporary research aids; parser behavior and findings must be reproducible from the repository.

`research/scripts/binary_diff.py` compares raw files or a uniquely selected member from two ZIP packages. It reports common prefix/suffix lengths, changed byte runs, and candidate integer/float interpretations at each changed-run start. The report explicitly uses absolute offsets; insertion or deletion can shift later structures, so the output is a triage aid rather than a structure-aware conclusion.

`python -m research.scripts.projectdata_diff before.band after.band` compares decompressed logic-song chunks after validating each package through the parser. It pairs chunks by tag, candidate group value, and ordinal within that pair, then reports changed header/payload ranges and added/removed pairs. This alignment is a hypothesis for organizing comparisons, not a semantic record identity: inserting a same-type chunk can shift later ordinals. Review diffs against controlled fixtures and the raw chunk order before identifying fields.

`python -m research.scripts.auco_probe project.band` checks the candidate `AuCO` header marker and fixed-offset record structure described in TRK-002. It validates the padded printable-name shape without including names in its report. Its counts are structural observations; the script does not assign GarageBand track semantics.

Do not infer region or note timing from summary duration, cache images, or resource lists. Preserve unknown payload bytes and report unsupported structures.
