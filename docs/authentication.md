# Password login

Install the dependency before starting SelfOS:

    python -m pip install -r requirements.txt
    python serve.py

SelfOS is a single-user local application. A genuinely empty installation can set its password
in the login page. An existing vault, including nonempty Markdown templates/manual notes, is
conservatively treated as existing data: initialize or recover the password in the local terminal:

    python selfos_auth.py reset

Type RESET and enter/confirm the new password through the hidden terminal prompts. Do not put
passwords in command arguments. The command preserves knowledge and invalidates existing
sessions. No browser reset endpoint is provided. Run it under the same OS account as the server.

## Storage and sessions

- Windows: LOCALAPPDATA/SelfOS/auth.json
- macOS: ~/Library/Application Support/SelfOS/auth.json
- Linux: XDG_DATA_HOME/selfos/auth.json, defaulting to ~/.local/share/selfos/auth.json

The file contains an Argon2id hash string with its random salt and parameters, never the plaintext
password. Current hashing parameters: 64 MiB memory, 3 iterations, parallelism 1, 16-byte salt and
32-byte output. Passwords must contain 12–1024 characters. POSIX directory/file permissions are
700/600; Windows removes inherited permissions and grants the current user access through ACLs.

Instances under one OS account share credentials. Each server keeps independent random sessions
in memory, with only token digests stored and a 12-hour absolute expiry. Restarts require login.
Cookies are HttpOnly, SameSite=Strict and path-scoped. The supported server is HTTP on loopback;
the cookie is not marked Secure for that transport. Remote deployment/TLS is outside this change.

Logout revokes the current session. Password changes/local resets invalidate all sessions through
credential fingerprint checks. Changing the password requires the current password. Five failed
logins within a minute trigger a temporary lockout. GET/POST/OPTIONS endpoints remain subject to
the existing loopback and same-origin restrictions as well as authentication.

## Fail-closed recovery

The project marker .selfos-auth-required and the private directory's .initialized marker record
established authentication. Missing or malformed credentials keep access locked when either
marker or existing knowledge is present. Markers contain no password and the project marker is
ignored by Git. Existing Markdown is never silently treated as an empty installation.

A valid hash replaced by someone who controls your OS account cannot reliably be recognized as
malicious; changed credentials still revoke sessions. Login protects the web/API access path,
not direct filesystem access, file encryption or against an administrator controlling the host.
Keep credentials and private state out of normal exports and source control.

Active progress streams check session validity on output/heartbeat. Session expiry or logout
closes access; the existing disconnect behavior cooperatively stops knowledge work while retaining
checkpoints. Log in again to view status and resume. Completed HTTP requests already in progress
may finish; authentication does not undo committed operations.

Authentication text lives in locales/en/auth.json and locales/zh-CN/auth.json. English is the
default/fallback, and saved language/theme preferences apply to login. No external assets or model
calls are required to log in.
