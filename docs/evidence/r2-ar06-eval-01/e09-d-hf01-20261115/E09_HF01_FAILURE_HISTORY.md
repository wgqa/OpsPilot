# E09 HF01 failure history

- **Base reproduction:** The fixture answered turn 1 with configuration facts from turn 2. It also attached a repeated configuration claim to a later review message rather than the original material message. Details and v3 source IDs are in `E09_HF01_RED_LOG.txt`.
- **Pytest environment:** The first test invocation could not create pytest's default AppData temp directory. Subsequent runs used newly checked, isolated `--basetemp` directories and completed.
- **Intermediate assertion:** A post-change integration run failed because the old Task-bound assertion required the complete raw first-turn body. The recorded failure is in `E09_HF01_INITIAL_ASSERTION_FAILURE_LOG.txt`. The assertion was aligned with the contract by checking the latest pre-binding goal/source review and HTTP 202 in current Task-bound context, while keeping the separate assertion that Taskless Summary IDs and bodies are absent from that request.
- **Test authoring corrections:** The first direct correction test expected only the correction sequence. It was corrected to require both the original claim source and the correction source (`[3, 9]`), with the `corrections` entry referencing sequence 9. The response assertion uses the English `unverified assertions` marker so terminal code-page rendering cannot affect the check.

No production Context/Memory behavior was changed to make these tests pass. The only source change is the E09 test Fixture Model and its assertions.
