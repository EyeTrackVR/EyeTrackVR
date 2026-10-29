# In-app contributions

Open Contribute data in EyeTrackVR. Capture and upload now share one reusable
window: Setup → Capture → Agreement → Upload. The flow opens and connects only when
the user chooses to contribute.

Users enter their HMD, follow the existing guided VR capture and then review the
agreement. The capture engine automatically attaches only the archive from that
successfully completed session. There is no archive picker, file-path field or
drag-and-drop upload route. Failed, stopped or restarted captures clear any prior
attachment. Preparing the same recording twice is blocked; existing prepared
submissions resume through Your contributions. Nothing uploads automatically.

The manager fetches the current notice from the configured HTTPS service. The only
dataset fields are HMD free text and two separate, unchecked consent controls:
the agreement (18+/self-contribution) and explicit consent for possibly biometric
or health-related eye images and the US transfer. Their labels are the notice's own
numbered statements, so the recorded notice version and hash cover them. Bug
reports have the same pair (agreement, US transfer). It packages allowlisted captures, removes incidental archive metadata,
encrypts locally using pyrage's age-compatible streaming API and uploads encrypted
chunks through the quota-enforcing Worker. No storage credentials or private
decryption keys ship with the app. No private backend package dependency is needed.

Verification opens an EyeTrackVR-owned embedded window, not an external browser.
The webview uses the service's /challenge?embedded=1 page, with a narrow token-only
loopback IPC channel. It has no app/filesystem JS API. External browser links,
downloads and file URLs are disabled. Windows uses WebView2, Linux uses Qt through
PySide6, and macOS uses WKWebView. Dependencies are included in pyproject.toml and
the supported Windows/Linux bundle specs. Windows needs the WebView2 runtime;
verification errors never fall back to an external browser. macOS/Linux native
verification still needs platform QA; the real native staging test ran on Windows.

Preparing, verifying and transferring run outside Tk's event loop. The UI reports
transmitted bytes and acknowledged chunks. Pause retains the exact ciphertext;
resume asks the server which chunks it has and never re-encrypts that session.
For an existing session, verification is not repeated. Updated terms must be
explicitly accepted before an uncreated session can be granted. Expired or exhausted
server sessions require a fresh, explicitly reviewed contribution.

Private receipts, encrypted resume files and temporary preparation files live in
the user's local application-data directory (EyeTrackVR/contributions), outside
Git. Windows restricts directory inheritance to the current user and SYSTEM;
POSIX uses mode 0700. A process lock prevents simultaneous upload/withdrawal from
multiple app instances. Closing the manager while busy pauses it before closing.

Save receipt creates a private backup for withdrawal. Restore receipt accepts only
the configured service origin and validates the manifest. A receipt backup alone
does not contain resume ciphertext: interrupted upload resume needs the original
encrypted payload on the original computer. Never share a receipt publicly.
Withdrawal retains the capability, deletes local resume data only after the server
confirms withdrawal (or confirms a never-created preparation is absent), and the
service blocks hosted downloads while scheduled deletion runs. User-selected source
ZIPs are never deleted by the contribution manager.

The default service targets staging, now publicly reachable with uploads enabled at the operator's request.
The upload wizard separates recording selection, a full readable agreement, and transfer.
A bundled public notice is readable offline; live terms are checked before any upload grant.
Resume and withdrawal controls live in a separate Your contributions tab. The staging hostname is allowed in Turnstile. Keep processor agreements and privacy operations current. The Worker must retain its 200-submission / 5 GiB
staging lifetime limits and other abuse controls. This is an aggregate upload
budget, not a Cloudflare account-wide spending cap.

bundles.py is the reviewed contributor packaging implementation shared with
ETVR-Dataset-Sync; protocol changes should be tested in both repositories. No
maintainer/admin implementation or account credentials are copied into the app.


Security review (2026-10-18): Windows receipt writes and backups now use protected
owner/SYSTEM DACLs on the underlying file before secrets are written. The contributor
CLI uses the matching private_files.py helper; keep these implementations synchronized.
Malformed local verification IPC is ignored. urllib3 is constrained to >=2.8.0,<3.
The detailed review, cross-owner tests, live audit and residual risks are recorded in
ETVR-Dataset-Sync/docs/SECURITY_REVIEW_2026-10-18.md. Old copies of a leaked receipt
remain capabilities until explicitly revoked; moving a backup does not rotate it.


Credential split and release checks (2026-10-20): contributor clients still contain
no maintainer credentials. The optional local Worker integration now downloads with
the independent read-only sync fixture token. The dataset-sync repository documents
upload/review/pull/withdrawal and deployment in docs/OPERATIONS.md and records the
live test in docs/SECURITY_REVIEW_2026-10-20.md. Windows packaging was rebuilt and
its frozen native helper tested with tests/contributions/packaged_smoke.py. The
Python projects require certifi >=2026.10.19 alongside urllib3 >=2.8.0. Linux/macOS
native verification still requires platform QA.


Protocol 3 (2026-10-20): uploads are end to end encrypted to the maintainer recipients
pinned in client.py (PINNED_RECIPIENTS); the service's advertised list must match or
uploads stop with an update message. HMD text is cleaned (bidi/control characters
removed) and travels only inside the ciphertext with a submission.json binding the
ID and agreed terms. prepare() runs bundles.inspect_bundle on its own output, the same
check maintainers apply after decryption. Schema 2 receipts can still withdraw and
resume existing sessions. Keep PINNED_RECIPIENTS in step with ETVR-Dataset-Sync
src/etvr_sync/core.py and worker/collection.json.


Bug reports (2026-10-24): Having Issues? → Report a bug opens report_window.py. The user
writes a description and may attach the tail (last 3 MiB) of this session's log, the
previous session's log, and a short app-details block (version, OS, tracker/model
settings). issue_bundle redacts home paths, IPs, emails and tokens; the bundle is the
service's separate "issue" kind with its own notice, 90-day retention and quotas, and
receipts live in issue_home() (EyeTrackVR/issue-reports), never in Your contributions.
Encryption, verification and upload reuse the dataset path. A failed send keeps the exact
ciphertext and a retry of the unchanged report resumes it; an edited report replaces it.
Maintainers pull reports with `etvr-dataset sync --kind issue --pending` (quarantine/issue/).
