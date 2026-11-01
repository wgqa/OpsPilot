# Failures and stopping records

This file is append-only for this experiment. Historical AR-02 UNKNOWN records, real-journey-02 failure evidence, and frozen inputs are not edited here or elsewhere.

## Preparation

- The remote GitHub HEAD query was attempted before work and failed with a connection reset. Remote SHA is `UNVERIFIED`; local base was verified as `bc5484fe721bd2a54bc3a73326ff3c649fa1baa2`.
- After the preparation commit was pushed, a fresh `git ls-remote` succeeded and verified the remote main and candidate branch; see `PREFLIGHT.md`.
- No Provider request has been made for AR-02-REAL-JOURNEY-03 as of the initial freeze.
- The first focused offline command passed 5/5; the wider selected regression command passed 63/63. No current-task test failure has occurred.
