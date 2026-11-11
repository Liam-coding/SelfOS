# Password Login Implementation Plan

Goal: implement issue #25 using the user-approved Argon2id, local credential storage and fail-closed recovery design.

Architecture: selfos_auth.py owns hashes, credentials and sessions; auth_ui.py uses independent locale resources; serve.py gates every route before dispatch. Existing knowledge tests isolate authentication; dedicated integration tests use the real gate.

Decisions: single user; credentials outside project/vault; 64 MiB/3 iterations Argon2id; 12-hour sessions; no web reset endpoint. Existing nonempty Markdown, including templates, requires local initialization to protect manual data. Loopback HTTP remains supported; vault encryption and remote deployment are separate work.

- [x] Write failing manager tests; implement private atomic credentials, markers, sessions, throttle, change and local reset.
- [x] Add integration tests and GET/POST/OPTIONS gate, including stream session checks.
- [x] Add English/Chinese login/setup/recovery and account controls.
- [x] Document dependency, storage, setup, transport scope and recovery.
- [x] Security review: fix Windows numeric SID ACLs, malformed credentials and failed logout feedback.
- [x] Verify: 605 full regression tests passed; 15 focused auth tests passed; browser setup/login/change/logout/failure recovery and mobile Chinese dark UI passed.
- [x] Install backed-up changes; protected local server on port 7150. Production credentials remain unset pending user terminal setup.

Validation uses temporary vaults and synthetic credentials only. Never set the user's password or run a production knowledge import.
