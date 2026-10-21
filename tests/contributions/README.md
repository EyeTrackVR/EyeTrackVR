# Desktop contribution checks

Run the focused checks without camera/model imports:

    poetry run pytest --confcutdir=tests/contributions tests/contributions

The tests cover actual age-compatible encryption/decryption, interrupted upload
recovery, byte progress, consent changes, receipt confinement, withdrawal,
verification cancellation, disabled external navigation, and real Tk UI state.
The Tk cases skip on hosts without a desktop display.

For the real local Worker integration, run the ETVR-Dataset-Sync Node suite with
ETVR_DESKTOP_PYTHON pointing to this app's Python interpreter and ETVR_DESKTOP_E2E
pointing to e2e_worker.py. That suite provisions isolated local D1/R2 resources,
generates an ephemeral age identity and checks encrypted partial upload, resume,
decryption and withdrawal. Its fixture Turnstile responses are confined to tests.

On 2026-10-17, a separate real staging smoke test also passed with the actual
Windows WebView2 window, real managed Turnstile and staging R2/D1. It used only
synthetic PNGs: 8,400,788 encrypted bytes, two chunks, an injected interruption
after chunk one, exact resume, byte-for-byte decryption, withdrawal and hosted
chunk cleanup. Only that synthetic record's five-minute deletion grace was
accelerated. Collection and public routes were disabled afterward and the
temporary loopback Turnstile domain permission was removed.

The real staging tests cumulatively consumed two submissions and 16,801,532 bytes
of the lifetime staging allowance. Cleanup intentionally does not refund them.


The unified-flow regression cases also exercise the actual DataCollectionWindow
controller with synthetic capture events: one shared window, automatic attachment,
capture failure/cancellation clearing stale data, consent gating, no archive picker,
and prevention of duplicate preparations. No cameras or real recordings are used.
