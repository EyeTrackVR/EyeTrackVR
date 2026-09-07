"""VRCFTClient sends face and eye tracking to VRChat using VRCFT's
Unified Expressions parameter namespace, without the VRCFT app.

    ft = VRCFTClient()
    ft.start()
    ft.set("EyeLeftX", -0.2)   # resolves to e.g. /avatar/parameters/FT/v2/EyeLeftX
    ft.set("JawOpen", 0.4)     # float / bool / binary bits, per the avatar
    ...
    ft.stop()

Behavior mirrors VRCFT:
  * sends only changed values, packed into OSC bundles, ~100 Hz to :9000
  * listens on :9001 for /avatar/change and re-resolves parameters
  * avatar params come from VRChat's OSCQuery endpoint (mDNS-discovered)
    or, failing that, VRChat's avatar config JSON on disk
  * honors /vrcft/settings/forceRelevant
"""

from __future__ import annotations

import logging
import socket
import threading
import time

from . import mdns, osc
from .avatar import AvatarInfo, fetch_avatar_oscquery, load_avatar_config
from .expressions import (
    UnifiedTrackingData,
    compute_legacy_outputs,
    compute_outputs,
    native_eyelids_relevant,
    native_gaze_relevant,
)
from .params import DEFAULT_PREFIX, FloatSlot, OutputSlot, resolve_slots, suffix_regex

logger = logging.getLogger("pyvrcft")

V2_PREFIX = "v2/"


class _DirectSlot(OutputSlot):
    """Fixed-address, always-relevant message (VRChat native endpoints
    like /tracking/eye/LeftRightPitchYaw). Value may be a tuple."""

    __slots__ = ("pending",)

    def __init__(self, address: str):
        super().__init__(address)
        self.pending = None

    def encode(self, value):
        return value


class _RawBoolSlot(OutputSlot):
    """Bool sent as-is (VRCFT's plain BaseParam<bool>, e.g. EyeTrackingActive
    unlike the EParam bool variant, with no threshold inversion)."""

    def encode(self, value):
        return bool(value)


class VRCFTClient:
    def __init__(
        self,
        send_host: str = "127.0.0.1",
        send_port: int = 9000,
        recv_port: int = 9001,
        rate: float = 100.0,
        use_oscquery: bool = True,
        force_relevant: bool = False,
        bool_threshold: float = 0.5,
    ):
        self.send_host = send_host
        self.send_port = send_port
        self.recv_port = recv_port
        self.interval = 1.0 / rate
        self.use_oscquery = use_oscquery
        self.force_relevant = force_relevant
        self.bool_threshold = bool_threshold

        # Callbacks (assign your own)
        self.on_avatar_change = None  # fn(AvatarInfo)
        self.on_message = None  # fn(address, args) for every received OSC message

        self.avatar: AvatarInfo | None = None

        self._values: dict[str, float] = {}  # logical name -> value
        self._slots: dict[str, list[OutputSlot]] = {}  # logical name -> outputs
        self._bool_values: dict[str, bool] = {}  # raw-bool params (see set_bool)
        self._bool_slots: dict[str, list[OutputSlot]] = {}
        self._force_slots: dict[str, OutputSlot] = {}  # forceRelevant defaults
        self._direct: dict[str, _DirectSlot] = {}  # raw address -> slot
        # Native /tracking/eye/* endpoints default to relevant until an
        # avatar config says the avatar has its own FT eye params.
        self._native_gaze_ok = True
        self._native_lids_ok = True
        self._lock = threading.Lock()

        self._oscquery_endpoint = None  # (host, port) of VRChat's HTTP server
        self._running = False
        self._threads: list[threading.Thread] = []
        self._send_sock: socket.socket | None = None
        self._recv_sock: socket.socket | None = None

    # ------------------------------------------------------------- public API

    def set(self, name: str, value: float, v2: bool = True) -> None:
        """Set a VRCFT parameter by its Unified Expressions name.

        "JawOpen" -> logical param "v2/JawOpen" (pass v2=False for legacy
        v1 names like "LeftEyeLidExpandedSqueeze"). The library resolves the
        avatar's actual address/encoding; unsupported params are just held.
        """
        key = name if (not v2 or name.startswith(V2_PREFIX)) else V2_PREFIX + name
        with self._lock:
            new = key not in self._values
            self._values[key] = float(value)
            if new:
                self._resolve_one(key)

    def set_many(self, values: dict, v2: bool = True) -> None:
        """Set several UE params at once: ft.set_many({"JawOpen": 0.3, ...})"""
        for name, value in values.items():
            self.set(name, value, v2=v2)

    def set_bool(self, name: str, value: bool) -> None:
        """Set a plain bool param sent as-is (e.g. "EyeTrackingActive").
        Unlike set(), no v2/ prefix and no threshold conversion."""
        with self._lock:
            new = name not in self._bool_values
            self._bool_values[name] = bool(value)
            if new:
                self._resolve_one_bool(name)

    def update_tracking(self, data: UnifiedTrackingData) -> None:
        """Feed one frame of raw tracking data through VRCFT's full
        expression pipeline: computes every v2 base/simple/combined/head
        parameter, the legacy v1 (SRanipal-era) eye parameters for older
        avatars, the native /tracking/eye/* endpoints (only when the avatar
        has no FT eye params, like VRCFT), and the *TrackingActive status
        bools.

        The v2, v1, and native outputs are all emitted every frame; the client
        resolves each against the current avatar and only what the avatar
        declares reaches the wire, so a v2 avatar, a legacy v1 avatar, and an
        avatar with no FT params at all (native eye tracking) are each driven
        correctly from the same tracking frame."""
        params, native = compute_outputs(data)
        self.set_many(params)
        # Legacy v1 eye params (bare names, no "v2/" prefix) for older avatars.
        self.set_many(compute_legacy_outputs(data), v2=False)
        if self._native_gaze_ok:
            self.send_direct("/tracking/eye/LeftRightPitchYaw", *native["/tracking/eye/LeftRightPitchYaw"])
        if self._native_lids_ok:
            self.send_direct("/tracking/eye/EyesClosedAmount", *native["/tracking/eye/EyesClosedAmount"])
        if data.eye_tracking_active is not None:
            self.set_bool("EyeTrackingActive", data.eye_tracking_active)
        if data.expression_tracking_active is not None:
            self.set_bool("ExpressionTrackingActive", data.expression_tracking_active)
            self.set_bool("LipTrackingActive", data.expression_tracking_active)

    def send_direct(self, address: str, *values) -> None:
        """Queue a message to an absolute OSC address, always sent (deduped).
        e.g. ft.send_direct("/tracking/eye/EyesClosedAmount", 0.1)"""
        with self._lock:
            slot = self._direct.get(address)
            if slot is None:
                slot = self._direct[address] = _DirectSlot(address)
            slot.pending = tuple(values) if len(values) != 1 else values[0]

    def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._send_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

        try:
            self._recv_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self._recv_sock.bind(("127.0.0.1", self.recv_port))
            self._recv_sock.settimeout(0.5)
        except OSError:
            logger.warning(
                "Could not bind OSC receive port %d (is VRCFT or another OSC app "
                "running?). Avatar-change detection is disabled; relying on "
                "OSCQuery polling / force_relevant.",
                self.recv_port,
            )
            self._recv_sock = None

        self._threads = [threading.Thread(target=self._send_loop, daemon=True, name="pyvrcft-send")]
        if self._recv_sock is not None:
            self._threads.append(
                threading.Thread(target=self._recv_loop, daemon=True, name="pyvrcft-recv")
            )
        if self.use_oscquery:
            self._threads.append(
                threading.Thread(target=self._discover_loop, daemon=True, name="pyvrcft-mdns")
            )
        for t in self._threads:
            t.start()

    def stop(self) -> None:
        self._running = False
        for t in self._threads:
            t.join(timeout=2.0)
        self._threads = []
        for sock in (self._send_sock, self._recv_sock):
            if sock is not None:
                sock.close()
        self._send_sock = self._recv_sock = None

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, *exc):
        self.stop()

    # ---------------------------------------------------------- avatar config

    def _resolve_avatar(self, avatar_id: str = "") -> None:
        """Fetch the current avatar's parameter list and rebuild all slots."""
        info = None
        if self._oscquery_endpoint is not None:
            info = fetch_avatar_oscquery(*self._oscquery_endpoint)
        if (info is None or not info.parameters) and avatar_id:
            info = load_avatar_config(avatar_id)
        if info is None:
            logger.warning(
                "Could not resolve avatar config for %r (no OSCQuery endpoint "
                "and no disk config). Parameters stay unresolved.",
                avatar_id or "<unknown>",
            )
            return
        if avatar_id and not info.id:
            info.id = avatar_id

        with self._lock:
            self.avatar = info
            self._slots.clear()
            for name in self._values:
                self._resolve_one(name)
            self._bool_slots.clear()
            for name in self._bool_values:
                self._resolve_one_bool(name)
            self._native_gaze_ok = native_gaze_relevant(info.parameters)
            self._native_lids_ok = native_eyelids_relevant(info.parameters)
            resolved = sum(1 for s in self._slots.values() if s)

        logger.info(
            "Avatar %s (%s): %d avatar params, %d/%d VRCFT params matched",
            info.id or "?",
            info.name or "?",
            len(info.parameters),
            resolved,
            len(self._values),
        )
        if self.on_avatar_change:
            try:
                self.on_avatar_change(info)
            except Exception:
                logger.exception("on_avatar_change callback failed")

    def _resolve_one(self, name: str) -> None:
        """Build output slots for one logical param (caller holds the lock)."""
        if self.avatar is not None:
            self._slots[name] = resolve_slots(
                name, self.avatar.parameters, self.bool_threshold
            )
        else:
            self._slots[name] = []

    def _resolve_one_bool(self, name: str) -> None:
        """Build slots for one raw-bool param (caller holds the lock)."""
        slots = []
        if self.avatar is not None:
            pattern = suffix_regex(name)
            slots = [
                _RawBoolSlot(p.address)
                for p in self.avatar.parameters
                if p.type is bool and pattern.search(p.address)
            ]
        self._bool_slots[name] = slots

    # ---------------------------------------------------------------- threads

    def _send_loop(self) -> None:
        while self._running:
            start = time.monotonic()
            messages = []
            with self._lock:
                force = self.force_relevant
                for name, value in self._values.items():
                    if force:
                        # VRCFT's forceRelevant: default address, raw float
                        slot = self._force_slots.get(name)
                        if slot is None:
                            slot = self._force_slots[name] = FloatSlot(DEFAULT_PREFIX + name)
                        slots = (slot,)
                    else:
                        slots = self._slots.get(name, ())
                    for slot in slots:
                        wire = slot.update(value)
                        if wire is not None:
                            messages.append(osc.encode_message(slot.address, [wire]))
                for name, value in self._bool_values.items():
                    if force:
                        slot = self._force_slots.get(name)
                        if slot is None:
                            slot = self._force_slots[name] = _RawBoolSlot(DEFAULT_PREFIX + name)
                        slots = (slot,)
                    else:
                        slots = self._bool_slots.get(name, ())
                    for slot in slots:
                        wire = slot.update(value)
                        if wire is not None:
                            messages.append(osc.encode_message(slot.address, [wire]))
                for slot in self._direct.values():
                    if slot.pending is None:
                        continue
                    wire = slot.update(slot.pending)
                    if wire is not None:
                        args = wire if isinstance(wire, tuple) else (wire,)
                        messages.append(osc.encode_message(slot.address, list(args)))

            if messages and self._send_sock is not None:
                try:
                    for bundle in osc.pack_bundles(messages):
                        self._send_sock.sendto(bundle, (self.send_host, self.send_port))
                except OSError:
                    logger.exception("OSC send failed")

            elapsed = time.monotonic() - start
            time.sleep(max(0.0, self.interval - elapsed))

    def _recv_loop(self) -> None:
        while self._running:
            try:
                data, _ = self._recv_sock.recvfrom(4096)
            except socket.timeout:
                continue
            except OSError:
                return
            for address, args in osc.parse(data):
                self._dispatch(address, args)

    def _dispatch(self, address: str, args: list) -> None:
        if address == "/avatar/change" and args and isinstance(args[0], str):
            self._resolve_avatar(args[0])
        elif address == "/vrcft/settings/forceRelevant" and args and isinstance(args[0], bool):
            self.force_relevant = args[0]
        if self.on_message:
            try:
                self.on_message(address, args)
            except Exception:
                logger.exception("on_message callback failed")

    def _discover_loop(self) -> None:
        """Find VRChat's OSCQuery server so we can resolve the avatar even if
        we started after it loaded (no /avatar/change to catch)."""
        while self._running and self._oscquery_endpoint is None:
            endpoint = mdns.discover_vrchat_oscquery(timeout=3.0)
            if endpoint is not None:
                self._oscquery_endpoint = endpoint
                logger.info("Found VRChat OSCQuery at http://%s:%d", *endpoint)
                if self.avatar is None:
                    self._resolve_avatar()
                return
            # VRChat may not be running yet; retry quietly.
            for _ in range(10):
                if not self._running:
                    return
                time.sleep(1.0)
