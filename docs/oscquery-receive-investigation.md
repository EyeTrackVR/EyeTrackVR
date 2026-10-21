# OSCQuery for the OSC receive side: investigation

Status: implemented on 2026-10-21 with Plan B (in-house responder, no zeroconf). The
investigation below, from 2026-10-20, is kept for the reasoning and sources.

## Implementation (2026-10-21)

Maintainers chose not to ship LGPL code, so the advertiser is all standard library:
`EyeTrackApp/osc/oscquery.py`.

- **Setting:** "Auto port (OSCQuery)" next to "Receive" (`gui_osc_oscquery`, default
  off). It is greyed out while Receive is off. Translated in all five languages.
- **Receiver:** in Auto mode `OSCReceiver` binds `127.0.0.1:0` and advertises it. If
  the advertiser cannot start (for example port 5353 cannot be bound) it logs a
  warning and binds the fixed Receiver Port as before. Fixed mode is unchanged.
  Toggling the setting restarts the receiver.
- **HTTP:** `ThreadingHTTPServer` on `127.0.0.1:0` serves `?HOST_INFO`, the tree,
  `?ATTRIBUTE` queries (204 if absent) and 404 for unknown paths. The tree lists
  `/avatar/change` plus every registered listener address. The first request is
  logged as "VRChat can now find the OSC receiver".
- **mDNS responder:** one UDP socket on `0.0.0.0:5353` with address reuse, joined to
  224.0.0.251 on loopback, the default interface and each local IPv4 address. It
  answers PTR, SRV, TXT, A and ANY questions for `<instance>._oscjson._tcp.local`
  and `<instance>._osc._udp.local` (plus the `_services._dns-sd` meta query), always
  with A 127.0.0.1. It announces twice on start (RFC 6762 §8.3), sends goodbyes
  (TTL 0) on stop, sends legacy unicast replies to one-shot queriers, honours the
  QU bit, and rate-limits multicast answers to once per second per question.
  Malformed packets, including name-pointer loops, are ignored.
- **pyvrcft:** `/avatar/change` received by ETVR is forwarded to
  `VRCFTClient.notify_avatar_change`, fixing stale parameters after an avatar
  switch while Receive is on (fixed or Auto mode). pyvrcft's VRChat lookup now
  re-sends its query about 1.1 s and 2.2 s in, so the once-per-second responder
  limit can't make it miss.
- **Tests:** `tests/test_oscquery.py` covers the tree, answers, goodbyes, malformed
  packets, HTTP, loopback-only binding, receiver wiring, fallback, avatar
  forwarding, and a real multicast round trip (skipped where CI has no multicast).

Still unverified: discovery by a real VRChat client, firewall prompt behaviour, and
Linux. The receiver's fixed mode still binds the *send* address (`gui_osc_address`),
so Receive with a Quest's IP as the send address likely fails. That is a separate fix.

## TL;DR

- **Recommendation: do it.** Add an "Auto (OSCQuery)" receive mode. The receiver binds `127.0.0.1:0` (an OS-assigned port), serves a small OSCQuery JSON tree over a loopback-only stdlib HTTP server, and advertises `_oscjson._tcp` and `_osc._udp` over mDNS. VRChat (2023.3.1 or later) finds the service and sends `/avatar/*` traffic to that port. Port 9001 is no longer needed, so we stop colliding with VRCFT, our own pyvrcft mode, and other OSC apps.
- Keep today's fixed-port receiver as the fallback (OSCQuery off, or mDNS fails to start).
- **Dependency:** `zeroconf` 0.151.5 (LGPL-2.1-or-later, one dependency: `ifaddr`, MIT). It has cp314 Windows and manylinux wheels and works in a PyInstaller 6.20 onefile build with no hooks (verified). It is **not** in `poetry.lock` today. LGPL in a onefile build needs a maintainer or legal sign-off. Plan B is a stdlib response-only responder, which is what VRCFT does, built on the existing `pyvrcft/mdns.py`.
- **Effort:** about 2 to 3 dev days with zeroconf, or about 3 to 4 with an in-house responder, plus an in-headset test pass with VRChat. **Risk:** low to medium. It is additive and has a fallback. The main unknowns are firewall prompts and in-game behaviour that can only be checked with a real VRChat client.
- **The spike worked end to end on this machine,** both from source and from a PyInstaller exe. Details in section 5.

---

## 1. What OSCQuery buys us for receive, and its limits

### How VRChat uses it

- VRChat has implemented OSCQuery since **release 2023.3.1** ([VRChat docs: OSCQuery](https://docs.vrchat.com/docs/oscquery), [community wiki: OSCQuery](https://github.com/vrchat-community/osc/wiki/OSCQuery)).
- Apps advertise two mDNS/DNS-SD services:
  - `<name>._oscjson._tcp.local.`: the HTTP port of the OSCQuery JSON server.
  - `<name>._osc._udp.local.`: the UDP port the app receives OSC on.

  The service type constants are defined in [vrc-oscquery-lib `Attributes.cs`](https://github.com/vrchat-community/vrc-oscquery-lib/blob/main/vrc-oscquery-lib/Attributes.cs), and [`OSCQueryService.cs`](https://github.com/vrchat-community/vrc-oscquery-lib/blob/main/vrc-oscquery-lib/OSCQueryService.cs) advertises one record of each kind. VRCFaceTracking ([`Services/OscQueryService.cs`](https://github.com/benaclejames/VRCFaceTracking/blob/master/VRCFaceTracking.Core/Services/OscQueryService.cs)) and [galister/VrcAdvert](https://github.com/galister/VrcAdvert) both advertise both records with an A record of `127.0.0.1`.
- VRChat fetches the app's root tree (`GET /`) and `GET /?HOST_INFO`. Per the wiki, it sends to apps whose tree contains:
  - **`/avatar`**, which receives `/avatar/change` and the avatar parameter messages;
  - or **`/tracking/vrsystem`**, which receives head and wrist poses and needs an extra in-game consent.

  VRChat shows a HUD notice naming the app the first time it starts sending to it.
- **Which parameters VRChat routes:** the documented trigger is the presence of an `/avatar` subtree, not a per-parameter subscription. VRCFT advertises only `/avatar/change` ([`HttpHandler.cs`](https://github.com/benaclejames/VRCFaceTracking/blob/master/VRCFaceTracking.Core/OSC/Query/HttpHandler.cs)). VrcAdvert advertises only `/avatar/parameters` and says VRChat "will send OSC avatar parameters to this port". Neither the wiki nor the libraries describe any per-address filtering, so **expect to receive every avatar parameter change, not only the paths we list**. Our default handler just does a dict lookup, so this is cheap. We should still advertise our exact addresses so the tree is self-describing. Confirm in game whether advertising narrow paths changes anything (expected: no).
- **HOST_INFO shape:** `NAME`, `EXTENSIONS` (attribute to bool), `OSC_IP`, `OSC_PORT`, `OSC_TRANSPORT` (`"UDP"`). The defaults come from [vrc-oscquery-lib `HostInfo.cs`](https://github.com/vrchat-community/vrc-oscquery-lib/blob/main/vrc-oscquery-lib/HostInfo.cs). The spec says every key is optional and `OSC_PORT` defaults to the HTTP port, so **always send `OSC_PORT` explicitly** ([Vidvox OSCQueryProposal](https://github.com/Vidvox/OSCQueryProposal)).
- Tree nodes use `FULL_PATH`, `CONTENTS` (containers), `TYPE` (OSC type tags), `ACCESS` (0 = none, 1 = read, 2 = write, 3 = read/write) and optionally `VALUE` and `DESCRIPTION`. Unknown paths return 404 (spec).

### What we gain

1. **No fixed port.** ETVR binds an ephemeral UDP port and tells VRChat about it. Port 9001 stays free for VRCFT or anything else.
2. **Coexistence.** VRChat "can now detect destinations and send OSC messages to multiple receivers" (wiki). VRCFT already works this way. Once it sees VRChat's OSCQuery service it binds a random receive port and advertises `VRCFT-XXXXXX` (see `FirstClientDiscovered` in VRCFT's `OscQueryService.cs`). ETVR and VRCFT can then both receive `/avatar/*` without fighting over 9001.
3. **It fixes a latent pyvrcft issue.** With **Receive** (`gui_ROSC`) on, `PyVRCFTSender.start` gives the embedded VRCFT port `recv_port=0`. Nobody sends to that ephemeral port, and `VRCFTClient._discover_loop` resolves the avatar once and then exits, so **pyvrcft never sees `/avatar/change` and keeps stale parameter slots after an avatar switch**. A shared OSCQuery receiver that forwards `/avatar/change` to pyvrcft fixes this (see section 4).
4. **Less setup for users.** "Receive" just works with the VRChat defaults.

### Limitations and risks

- **VRChat version:** 2023.3.1 or later. OSC must be enabled in the action menu. vrc-oscquery-lib notes that the OSC toggle may need re-enabling each launch.
- **VRChat still sends to its own configured out port,** 9001 by default. The wiki says a user-specified `--osc` port still gets everything. In OSCQuery mode we must not also listen on 9001, or we get duplicates.
- **Known VRChat OSCQuery bugs, mostly on the "query VRChat" side we already use in pyvrcft:**
  - VRChat advertises its own OSCQuery service with A = 127.0.0.1, so it can't be reached from other machines ([feedback](https://feedback.vrchat.com/bug-reports/p/vrchat-client-advertises-loopback-address-as-oscquery-service-endpoint)).
  - HOST_INFO still reports 9000 after `--osc` changes the port ([feedback](https://feedback.vrchat.com/bug-reports/p/oscquery-vrchat-reports-the-incorrect-listening-port-for-osc-when-changing-it-vi)).
  - Parameters that never change after avatar load are reported as false or 0 ([feedback](https://feedback.vrchat.com/bug-reports/p/oscquery-broadcasts-wrong-parameter-values)).

  None of these block the receive direction.
- **Windows mDNS:**
  - UDP 5353 is shared. The Windows DNS Client service, Bonjour if installed, VRChat (MeaMod.DNS), VRCFT and pyvrcft's `mdns.py` all bind it with `SO_REUSEADDR`. In the spike, zeroconf and a raw stdlib socket coexisted on 5353 without problems.
  - Same-machine multicast was looped back. Responses arrived from `127.0.0.1:5353`, so discovery should not depend on a LAN NIC being up. That is only verified on this machine.
- **Firewall:**
  - The HTTP server and OSC receiver bind `127.0.0.1`, so they cause no Windows Defender prompt.
  - The mDNS socket binds `0.0.0.0:5353` (zeroconf and our own `pyvrcft/mdns.py` both do), which can trigger the first-run "Allow access" prompt for `EyeTrackApp.exe`. pyvrcft-mode users already see this today.
  - Loopback traffic isn't filtered, so declining the prompt should still allow same-PC discovery. That is not verified on a clean machine.
  - Option: restrict zeroconf to `interfaces=["127.0.0.1"]` for PC-only use and test whether VRChat's MeaMod still finds us. VRCFT deliberately joins on non-loopback NICs, so this is a real risk.
- **Quest standalone (VRChat on Android):**
  - The wiki says Android VRChat can discover OSCQuery apps anywhere on the LAN. To receive from it we would need to advertise the PC's LAN IP (not 127.0.0.1) and bind the receiver on that NIC or `0.0.0.0`. That brings firewall prompts and multi-NIC IP selection.
  - **Recommend PC-only (loopback) in v1, with the fixed-port fallback for Quest.**
  - Separate existing bug: `OSCReceiver` binds `(gui_osc_address, gui_osc_receiver_port)`. `gui_osc_address` is the *send target*, so a Quest IP there makes the bind fail with `WSAEADDRNOTAVAIL`. Receive likely doesn't work for Quest-standalone users today regardless of OSCQuery.
- **No mDNS available** (no NICs, mDNS blocked by a VPN or security suite): we can't detect that VRChat found us except by observing an HTTP `GET` from it. Expose that as a status indicator and let users switch to fixed port.
- **ChilloutVR** also advertises OSCQuery (VRCFT's mDNS code matches `ChilloutVR-GameClient`), so this likely helps there too. Untested.

## 2. Current receive path and pyvrcft

### ETVR receiver

The receiver is `EyeTrackApp/osc/osc.py`.

- **`OSCManager.setup_receiver()`** runs only if `settings.gui_ROSC` is set. It starts `OSCReceiver` on a thread. `update()` restarts the receiver when `gui_ROSC`, `gui_osc_receiver_port` or `gui_osc_address` change; the signature is in `_receiver_signature()`.
- **`OSCReceiver`** is a python-osc `OSCUDPServer` bound to `(gui_osc_address, gui_osc_receiver_port)`, which defaults to `127.0.0.1:9001` (`config.py`). Its default handler dispatches by exact address to `listeners[address]`. Every value is wrapped as `OSCMessage(EYE_INFO, data=value)`.
- **Addresses handled today.** They are registered once at startup in `eyetrackapp.py` via `osc_manager.register_listeners`:

  | Setting | Default address | Handler |
  |---|---|---|
  | `gui_osc_recenter_address` | `/avatar/parameters/etvr_recenter` | `eyes[0/1].osc_recenter_eyes` |
  | `gui_osc_recalibrate_address` | `/avatar/parameters/etvr_recalibrate` | `_osc_recalibrate` (needs bool `True`) |

  Nothing else is consumed. Note that because listeners are keyed by the address at startup, editing either address needs an app restart. This is pre-existing behaviour.
- **UI:** the "Receive" checkbox is in `settings/modules/OSCSettingsModule.py` (`gui_ROSC`, default **False**). "Receiver Port" is in `settings/modules/AdvancedOSCSettingsModule.py`.

### pyvrcft (vendored PY-VRCFT port)

pyvrcft is **an OSCQuery/mDNS *client* only, not a server/advertiser.**

- `pyvrcft/mdns.py` is a ~130-line stdlib one-shot querier. It sends a PTR query for `_oscjson._tcp.local`, parses SRV records, matches the `VRChat-Client` instance prefix, and returns `("127.0.0.1", port)`.
- `pyvrcft/avatar.py::fetch_avatar_oscquery` does `GET /avatar` on VRChat's OSCQuery server to get the avatar's parameter list.
- `pyvrcft/client.py::VRCFTClient`:
  - binds `127.0.0.1:recv_port`, which is 9001 by default, to catch `/avatar/change` and `/vrcft/settings/forceRelevant`;
  - logs a warning and continues if the bind fails;
  - runs `_discover_loop` until it finds VRChat once.
- `osc/PyVRCFTSender.start` passes `recv_port=0` when `gui_ROSC` is on. That is the stale-avatar issue described in section 1.
- The spike found a quirk in `discover_vrchat_oscquery`. It sends **one** query and never retransmits. RFC 6762 §6 responders (zeroconf, and probably MeaMod) suppress a repeat multicast answer within about 1 s of the last one. So a back-to-back query can get no reply:
  - The spike reproduced it as found, then **None**, then found, across three consecutive calls.
  - The 10 s retry loop hides this today.
  - Sending the query 2 to 3 times with a ~250 ms spacing, or setting the QU (unicast-response) bit, would make it robust.

### How OSCQuery fits

- **Advertised addresses.** Advertise `/avatar/change` (`s`, write-only) plus the current `listeners` keys, each with `TYPE` `T`/`F` (bool) and `ACCESS` 2. With defaults that is `/avatar/change`, `/avatar/parameters/etvr_recenter` and `/avatar/parameters/etvr_recalibrate`. Addresses outside `/avatar` can be listed too, but VRChat will only ever send `/avatar/*` and `/tracking/vrsystem/*`.
- **Port selection.** In OSCQuery mode, bind UDP `127.0.0.1:0` and read back `server.server_address[1]`. Bind HTTP on `127.0.0.1:0` too. Don't persist either port; they're re-advertised every start.
- **Lifecycle.** The advertiser is owned by `OSCManager` and started and stopped together with the receiver (`setup_receiver` / `stop_receiver`), so it follows `gui_ROSC` and settings changes. On stop, unregister the services so goodbye packets (TTL 0) go out and VRChat drops us promptly; then close zeroconf, shut down HTTP, then OSC. Add the new flag to `_receiver_signature()`.
- **Fallback.** If OSCQuery is off, or zeroconf fails to start (any exception), fall back to today's behaviour: bind `gui_osc_receiver_port` and log why.

## 3. Dependency choice

| Option | License | Status | Notes |
|---|---|---|---|
| **python-zeroconf** 0.151.5 ([PyPI](https://pypi.org/project/zeroconf/), [repo](https://github.com/python-zeroconf/python-zeroconf)) | **LGPL-2.1-or-later** | Very active; 0.151.5 uploaded 2026-09-28; used by Home Assistant | Needs Python 3.10 or later. Only dependency is `ifaddr` 0.2.0 (MIT). Has cp314 wheels for win_amd64/win32, manylinux x86_64/aarch64, and macOS arm64. Cython-accelerated, with a pure-Python fallback. **Not in `poetry.lock`** (only `python-osc` 1.10.2 and `pyinstaller` 6.20.0 are). |
| [cyberkitsune/tinyoscquery](https://github.com/cyberkitsune/tinyoscquery) | MIT | Work in progress, not on PyPI (`pip install ./`), about 41 commits | Uses zeroconf plus `http.server`. Self-described as "just the bare minimum to advertise that a server exists"; node advertising is still a to-do item. Binds HTTP on `''` (all interfaces). Not worth a dependency. |
| [fraklein/python-oscquery](https://github.com/fraklein/python-oscquery) 0.4.0 ([PyPI](https://pypi.org/project/python-oscquery/)) | MIT | Early (0 stars, last release 2026-04-07) | Depends on zeroconf, requests and python-osc. Fuller tree model, no websocket. Still pulls in zeroconf, and adds an API we don't need. |
| VRChat's [vrc-oscquery-lib](https://github.com/vrchat-community/vrc-oscquery-lib) | MIT | Reference only (C#) | Use it as the behaviour spec. |
| **In-house:** extend `pyvrcft/mdns.py` into a response-only responder plus a stdlib HTTP server | ours | n/a | Exactly VRCFT's approach (`mDNS/MulticastDnsService.cs`): answer PTR queries for our two service types with PTR + SRV + TXT `txtvers=1` + A 127.0.0.1, and never announce. About 150 to 250 extra lines. Avoids LGPL and a new binary dependency, but leaves us to handle multi-NIC sockets, goodbye packets and rate limiting. |

### PyInstaller

The spike was built with the project's own Poetry venv (`pyinstaller` 6.20.0, `pyinstaller-hooks-contrib` 2026.5, which has no zeroconf hook) as `--onefile` with no hidden imports. All 18+ zeroconf `.cp314-win_amd64.pyd` extensions were collected automatically, and the frozen exe passed the full verification in section 5. If a later zeroconf version breaks analysis, add `collect_submodules('zeroconf')` to `hiddenimports` in both `eyetrackapp.spec` and `eyetrackapp_linux.spec`. The Linux build (WSL Ubuntu-22.04, manylinux wheel) is not yet verified.

### LGPL note

The Windows build is a PyInstaller **onefile** exe (`eyetrackapp.spec` has `EXE` with no `COLLECT`), under the Babble Software Distribution License. LGPL-2.1 §6 expects users to be able to swap in a modified library. That is easy with the Linux onedir build and murkier with onefile.

- If maintainers don't want to take that on: go in-house (Plan B), or load zeroconf from a side folder next to the exe.
- If they're comfortable (unmodified library, license text shipped, source link in the about/licenses page): use zeroconf.

## 4. Design sketch

New module `EyeTrackApp/osc/oscquery.py`, all stdlib plus zeroconf:

```python
def build_tree(endpoints: dict[str, tuple[str, int, str]]) -> dict
    # full_path -> (TYPE, ACCESS, DESCRIPTION) -> nested CONTENTS/FULL_PATH dict

class _Handler(BaseHTTPRequestHandler)
    # GET ?HOST_INFO -> host_info; GET /path[?ATTR] -> node / attr; 404 unknown
    # on any request: advertiser.mark_seen(client_ip)  (status: "VRChat connected")

class OSCQueryAdvertiser:
    def __init__(self, app_name: str = "EyeTrackVR"): ...
    def start(self, osc_port: int, endpoints: dict) -> None
        # name = f"{app_name}-{6 random chars}"   (unique per run, like VRCFT)
        # ThreadingHTTPServer(("127.0.0.1", 0)) on daemon thread "oscquery-http"
        # Zeroconf(ip_version=V4Only); register ServiceInfo for
        #   _oscjson._tcp.local. (http port) and _osc._udp.local. (osc_port),
        #   addresses=[127.0.0.1], properties={"txtvers": "1"}
    def stop(self) -> None   # unregister (goodbyes) -> zc.close -> http.shutdown
    @property
    def discovered(self) -> bool   # True after the first HTTP hit
```

Hooks into the existing code:

- **`config.py`:** new `gui_osc_oscquery: bool = True`. Default on, or off for one release as "experimental", matching how `gui_pyvrcft` was introduced.
- **`OSCReceiver.__init__`:** if `gui_osc_oscquery`, bind `("127.0.0.1", 0)`, otherwise `(gui_osc_address, gui_osc_receiver_port)` as today. Expose `self.port`. Consider binding `127.0.0.1` in fixed mode too, which fixes the Quest-IP bind failure; LAN receive would then need `0.0.0.0` as an explicit option.
- **`OSCReceiver.run`:** after `serve_forever` starts, `self.advertiser = OSCQueryAdvertiser(); self.advertiser.start(self.port, endpoints_from(self.listeners) | {"/avatar/change": ("s", 2, ...)})`. Wrap this in try/except. On failure, log it, tear down, and rebind the fixed port (fallback). Stop the advertiser in `shutdown()` *before* `server.shutdown()`.
- **`OSCManager._receiver_signature` / `update`:** add `gui_osc_oscquery`.
- **pyvrcft (optional, recommended):** when ETVR's receiver is running, register an `/avatar/change` listener that calls `pyvrcft_sender.client._dispatch("/avatar/change", [id])`. This would become a small public method such as `VRCFTClient.notify_avatar_change(avatar_id)`. It fixes the stale-avatar issue, and pyvrcft keeps `recv_port=0`. Alternatively, have pyvrcft advertise its own receiver, but one advertiser per app is simpler and gives one HUD notice.
- **UI:**
  - A "Port: Auto (OSCQuery) / Fixed" control next to "Receive".
  - Grey out "Receiver Port" when Auto is selected.
  - Show status: "Waiting for VRChat…" / "VRChat connected" from `advertiser.discovered`.
  - New strings go in `lang/en.toml`, `_TEMPLATE.toml` and the 5 translations.
- **Threads:** one HTTP thread plus zeroconf's internal asyncio thread, in addition to the existing receiver threads. Nothing touches the tracking hot path.
- **Tests:** unit tests for `build_tree` and the handler (HOST_INFO, root, `?TYPE`, 404) on a loopback port, plus an opt-in integration test like the spike's `verify.py`. Multicast in CI can be flaky, so mark it skip-able.

### Effort and risk

| Item | Estimate |
|---|---|
| `oscquery.py` + receiver/manager wiring + fallback | 0.5–1 d |
| Config flag, UI, 6 language files | 0.5 d |
| pyvrcft `/avatar/change` forwarding | 0.25 d |
| Tests + Windows onefile + Linux tarball build checks | 0.5 d |
| In-headset validation with VRChat (+ VRCFT running alongside) | 0.5 d, needs a person with a headset |
| **Total (zeroconf)** | **≈2–3 d** |
| Plan B in-house responder instead of zeroconf | +1 d, plus more edge-case risk |

**Risk: low to medium.** The change is additive and isolated to the receiver, with the fixed-port path kept as fallback. Open questions that only a live VRChat test can close:

1. Does VRChat pick us up when the advertisement precedes VRChat start, and when it follows? VRCFT is response-only and works, so both are expected to work.
2. Confirm that every `/avatar/*` message is delivered regardless of the paths we list.
3. Does a declined firewall prompt break same-PC discovery? Expected: no.
4. If we restrict zeroconf to loopback: does VRChat's MeaMod still find us?

## 5. Spike

The spike lives in the scratch area, not the repo:
`C:\Users\beaul\AppData\Local\Temp\claude\C--Users-beaul-Documents-GitHub-EyeTrackVR\649ecb1e-246c-4a58-956f-92fa3cb3dcd1\scratchpad\oscquery\`

- `oscquery_service.py`:
  - python-osc `ThreadingOSCUDPServer` on `127.0.0.1:0`;
  - stdlib `ThreadingHTTPServer` on `127.0.0.1:0` serving HOST_INFO and a nested root tree (`/avatar/change`, `/avatar/parameters/etvr_recenter`, `/avatar/parameters/etvr_recalibrate`);
  - zeroconf `ServiceInfo` registrations for `ETVR-XXXXXX._oscjson._tcp.local.` and `ETVR-XXXXXX._osc._udp.local.` with A 127.0.0.1 and TXT `txtvers=1`;
  - a clean unregister on exit.
- `verify.py`, run as a separate process:
  - zeroconf `ServiceBrowser` and `get_service_info`;
  - HTTP GETs;
  - an OSC send to `HOST_INFO.OSC_PORT`;
  - a cross-check with the repo's `pyvrcft/mdns.py`, loaded read-only by path.
- `raw_query_debug.py`: dumps the raw mDNS responses to a PTR query.
- Dependencies (`zeroconf==0.151.5`, `python-osc==1.10.2`, `ifaddr`) were installed into `_deps/` with `pip --target`. Everything ran with `py -3.14 -I` (Python 3.14 on Windows 11).

Verified, on loopback only:

1. **Discovery:** the browser found both `ETVR-…._oscjson._tcp.local.` and `ETVR-…._osc._udp.local.` in about 1.3 s. SRV and A resolved to `127.0.0.1:<http_port>` and `127.0.0.1:<osc_port>`, with TXT `txtvers=1`.
2. **HOST_INFO:** `GET /?HOST_INFO` returned 200 with `{"NAME":"ETVR-…","EXTENSIONS":{…},"OSC_IP":"127.0.0.1","OSC_PORT":<osc_port>,"OSC_TRANSPORT":"UDP"}`. `OSC_PORT` matched the `_osc._udp` SRV port.
3. **Root tree:** `GET /` returned 200 with `CONTENTS.avatar.CONTENTS = {change, parameters}` and `parameters.CONTENTS = {etvr_recalibrate, etvr_recenter}`.
4. **Attribute queries and errors:** `GET /avatar/parameters/etvr_recenter?TYPE` returned `{"TYPE":"T"}`, and `GET /nope` returned 404.
5. **OSC delivery:** OSC sent to the advertised port arrived. The service printed `RECEIVED /avatar/parameters/etvr_recenter [True]` and `RECEIVED /avatar/change ['avtr_spike-test']`.
6. **Raw stdlib query:** pyvrcft's raw querier also found the zeroconf-advertised service, with responses arriving from `127.0.0.1:5353` and coexisting on port 5353. A back-to-back repeat query got no answer, which is the RFC 6762 1 s suppression described in section 2.
7. **Frozen build:** a **PyInstaller 6.20.0 `--onefile` build** (no hooks or hidden imports, 11 MB) passed checks 1 to 5 identically, and all zeroconf `.pyd` extensions were bundled.

Not verified:

- discovery by a real VRChat client, and in-game HUD notice or traffic;
- behaviour on a machine where the firewall prompt was declined;
- the Linux build;
- Quest/LAN.

## Sources

- VRChat docs, OSCQuery: https://docs.vrchat.com/docs/oscquery
- VRChat community wiki, OSCQuery: https://github.com/vrchat-community/osc/wiki/OSCQuery
- VRChat docs, OSC avatar parameters (`/avatar/change`): https://docs.vrchat.com/docs/osc-avatar-parameters
- vrc-oscquery-lib (MIT): https://github.com/vrchat-community/vrc-oscquery-lib ([OSCQueryService.cs](https://github.com/vrchat-community/vrc-oscquery-lib/blob/main/vrc-oscquery-lib/OSCQueryService.cs), [HostInfo.cs](https://github.com/vrchat-community/vrc-oscquery-lib/blob/main/vrc-oscquery-lib/HostInfo.cs), [Attributes.cs](https://github.com/vrchat-community/vrc-oscquery-lib/blob/main/vrc-oscquery-lib/Attributes.cs))
- Vidvox OSCQuery proposal: https://github.com/Vidvox/OSCQueryProposal
- VRCFaceTracking OSCQuery receive implementation: https://github.com/benaclejames/VRCFaceTracking/blob/master/VRCFaceTracking.Core/Services/OscQueryService.cs, https://github.com/benaclejames/VRCFaceTracking/blob/master/VRCFaceTracking.Core/OSC/Query/HttpHandler.cs, https://github.com/benaclejames/VRCFaceTracking/blob/master/VRCFaceTracking.Core/mDNS/MulticastDnsService.cs
- galister/VrcAdvert (Unlicense): https://github.com/galister/VrcAdvert
- python-zeroconf: https://pypi.org/project/zeroconf/ and https://github.com/python-zeroconf/python-zeroconf
- tinyoscquery (MIT): https://github.com/cyberkitsune/tinyoscquery
- python-oscquery (MIT): https://github.com/fraklein/python-oscquery
- VRChat feedback, loopback advertisement: https://feedback.vrchat.com/bug-reports/p/vrchat-client-advertises-loopback-address-as-oscquery-service-endpoint
- VRChat feedback, wrong advertised port with `--osc`: https://feedback.vrchat.com/bug-reports/p/oscquery-vrchat-reports-the-incorrect-listening-port-for-osc-when-changing-it-vi
- VRChat feedback, wrong initial values: https://feedback.vrchat.com/bug-reports/p/oscquery-broadcasts-wrong-parameter-values
- RFC 6762 (mDNS) §6, response rate limiting: https://www.rfc-editor.org/rfc/rfc6762#section-6
