# Public artifact review and hash inventory

Publication branch: `codex/ar03-material-01-public`. It was rebuilt from the trusted Base, not derived from the original candidate commit chain.

Original candidate reviewed: `codex/ar03-material-01@505597bd0592c66639e10084456a3836edb72516`; `55` changed paths across 4 commits.

The scan found no external API credentials, bearer tokens, cloud/GitHub tokens, JWTs, email addresses, private IPv4 addresses, cookie/auth headers, user-profile paths, or binary/browser/database/environment artifacts. It found only a synthetic local TestClient password echo in five raw pytest logs (11 total occurrences). The test source uses synthetic credentials solely for in-process authentication. The publication logs replace that exact echoed fixture value; all other bytes and exit codes are preserved. The original raw logs remain byte-for-byte in the local original candidate worktree.

The `raw_sha256` values below identify the original log bytes. `published_sha256` identifies the corresponding public sanitized copy.

| Published log | Raw SHA-256 | Published SHA-256 | Redacted fixture echoes |
|---|---|---|---|
| `docs/evidence/ar-03/material-01/runs/debug-bound-01.log` | `0368a773efaa28084b2ebc45b236a723ddc086be4c3102e19c8d3fc4182f9e10` | `0368a773efaa28084b2ebc45b236a723ddc086be4c3102e19c8d3fc4182f9e10` | 0 |
| `docs/evidence/ar-03/material-01/runs/debug-bound-02.log` | `228ecf838a555415ee63eb00424e3c1fabb136097f4353c3c38aefc1ff38de6c` | `6ff727f61f672a6d40e6fa780c634b64b9613b9246ded75c1a9451b7b259e6eb` | 2 |
| `docs/evidence/ar-03/material-01/runs/green-01-focused.log` | `6176fcff0118f804bfaac89f77433ce7201de50d14db5a8207c7cbaa98504083` | `6176fcff0118f804bfaac89f77433ce7201de50d14db5a8207c7cbaa98504083` | 0 |
| `docs/evidence/ar-03/material-01/runs/green-02-focused.log` | `33205be9b963413f9250b5241436f0f2ce0f7e8185eaf9958f15ed8896b41a53` | `33205be9b963413f9250b5241436f0f2ce0f7e8185eaf9958f15ed8896b41a53` | 0 |
| `docs/evidence/ar-03/material-01/runs/green-03-focused.log` | `b7cfc61c45fc7adaedc591badbc1709ebb4f6a8f2b5f9bd15f097f63793d8521` | `b7cfc61c45fc7adaedc591badbc1709ebb4f6a8f2b5f9bd15f097f63793d8521` | 0 |
| `docs/evidence/ar-03/material-01/runs/green-04-material-full.log` | `64975e69acd9ed2af95085fba02feef559bdf7fc7cc250c1ab1c0ebef7f4e79b` | `6dc1605b291e6c02b66d2d9a0247d2a90d1c5da081c1d754c5a0dd87b87f05b3` | 3 |
| `docs/evidence/ar-03/material-01/runs/green-05-material-full.log` | `ac7b638151ad2b3f5cd403e316d01a84793f8ad9311b224c670e7f1929e817d2` | `c027479cb35797141ffde88ce655ecd00ff9000c7cba58ec9735a149f60f65cf` | 2 |
| `docs/evidence/ar-03/material-01/runs/green-06-material-full.log` | `2c6e9213d49c7967c99b43d14aef505210191d21a028c81e65bfdba44c34f13e` | `2c6e9213d49c7967c99b43d14aef505210191d21a028c81e65bfdba44c34f13e` | 0 |
| `docs/evidence/ar-03/material-01/runs/green-07-material-full.log` | `215b5453913efb506bc9fd5ce922ea15391d742f7444ab1c565c3ef57bb407df` | `215b5453913efb506bc9fd5ce922ea15391d742f7444ab1c565c3ef57bb407df` | 0 |
| `docs/evidence/ar-03/material-01/runs/green-08-material-final.log` | `50a64bf31042da98760082dd9f045415c8c005f424da9db5486377d17092025a` | `50a64bf31042da98760082dd9f045415c8c005f424da9db5486377d17092025a` | 0 |
| `docs/evidence/ar-03/material-01/runs/green-09-material-final.log` | `1d644c96734416019903954c9bae47c021c6c9f2063e86ba35f84ce27735e75f` | `759b53cc6e5d791065b8e95213d53421fcb756678fe3583794c36b5d01fe9caa` | 1 |
| `docs/evidence/ar-03/material-01/runs/green-10-material-final.log` | `cf5156da3949ded116498dd7ef0dbab60ff2ebd27cb7cea9aedff62f27bedaf7` | `cf5156da3949ded116498dd7ef0dbab60ff2ebd27cb7cea9aedff62f27bedaf7` | 0 |
| `docs/evidence/ar-03/material-01/runs/green-11-material-final.log` | `491cda49194bed42172a7d3691af83ad9e8198526b531727b80f830b54e8e163` | `491cda49194bed42172a7d3691af83ad9e8198526b531727b80f830b54e8e163` | 0 |
| `docs/evidence/ar-03/material-01/runs/green-12-material-final.log` | `6d86e2da09fddc13dfd3f0fc0120cd0979270eaba2181363faf223ed9a0a4a5f` | `6d86e2da09fddc13dfd3f0fc0120cd0979270eaba2181363faf223ed9a0a4a5f` | 0 |
| `docs/evidence/ar-03/material-01/runs/red-01.log` | `7a2252128ad6b272291945c29d53359f5ce1c93eb2e67a6e81feec670d187ef9` | `83bcc7330497a57797bb710902904ef254a2e9212ce1c0fdeda9a31b78289217` | 3 |
| `docs/evidence/ar-03/material-01/runs/red-02.log` | `5e98a01a1f7970b51849ea59100ba9f5b9b9740e7356fbfef1df1957197ea975` | `5e98a01a1f7970b51849ea59100ba9f5b9b9740e7356fbfef1df1957197ea975` | 0 |
| `docs/evidence/ar-03/material-01/runs/red-03.log` | `fb2100f3aa374f8a5811d01b0e6416cedfd0646cf9103eeacf2597cb08f96883` | `fb2100f3aa374f8a5811d01b0e6416cedfd0646cf9103eeacf2597cb08f96883` | 0 |
| `docs/evidence/ar-03/material-01/runs/regression-01-protocol-assistant.log` | `d344b99d16be27dbfb1f23f3878b84d2f24fcb4728f19c6256378f802f9fc5e0` | `d344b99d16be27dbfb1f23f3878b84d2f24fcb4728f19c6256378f802f9fc5e0` | 0 |
| `docs/evidence/ar-03/material-01/runs/regression-02-full-pytest.log` | `80e9e968c3573097d5bb262b63cd61a23ad61f76c81af5f04933110e256224e0` | `80e9e968c3573097d5bb262b63cd61a23ad61f76c81af5f04933110e256224e0` | 0 |
| `docs/evidence/ar-03/material-01/runs/regression-03-protocol-assistant-final.log` | `f375bfc77e8aa2c4fdfdd35af8cb896a4ed51b3be760eccb0b02e4b48df094a1` | `f375bfc77e8aa2c4fdfdd35af8cb896a4ed51b3be760eccb0b02e4b48df094a1` | 0 |

No screenshot, browser state, SQLite database, LangGraph Checkpoint, `.env`, certificate, or private key is part of this publication candidate.
