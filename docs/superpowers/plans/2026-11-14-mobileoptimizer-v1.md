# MobileOptimizer v1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a Windows/Linux desktop app that connects to an Android phone over USB with ADB and applies brand-specific, fully reversible performance/battery/cleanup profiles without root.

**Architecture:** A UI-free `core` package does all the work. It contains an ADB wrapper, device detection, the profile loader with a validator and blacklist, per-type action executors, a snapshot store with last-in-first-out undo, and a session runner. Profiles are YAML data. A PySide6 wizard UI sits on top and runs long operations in a worker thread. Tests run against an in-memory `FakeAdb`, so no phone is needed except for the manual verification steps.

**Tech Stack:** Python 3.11+, PySide6 6.7, PyYAML 6.0, pytest 8, pytest-qt 4, PyInstaller 6 (`--onedir`), Android platform-tools r35.0.2 (bundled `adb`).

**Spec:** `docs/superpowers/specs/2026-11-14-mobileoptimizer-design.md`

**Layout note:** The spec's `app/`, `core/`, `profiles/` folders live under one importable package `mobileoptimizer/`. `vendor/` stays at the repo root. This is the builder's call, made for clean imports and PyInstaller.

## Global Constraints

- No root. Only commands the ADB `shell` user can run.
- Android 10+ (SDK 29+) is the target. Below SDK 29 the app warns and offers only `generic` profile actions with `risk: safe`.
- Windows 10/11 first, Linux second. macOS is not tested.
- `adb` is bundled. The user never installs it.
- No network access and no telemetry anywhere in the app. Profiles ship inside the app. The only download is in the build script, never in the app.
- Allowed action types are exactly: `setting`, `package_disable`, `package_uninstall`, `appops`, `standby_bucket`, `compile`, `device_config`. No arbitrary shell command type exists.
- Ready-made presets (`max_performance`, `max_battery`, `balanced`) contain only actions with `risk: safe` and `verified: true`. They use `package_disable`, never `package_uninstall`.
- `package_uninstall` is allowed only with `risk: expert`.
- Animation scales in presets are `0.5`, never `0`.
- Temporary types (`standby_bucket`, `device_config`, `compile`) carry a "geçici" badge. The report text for them is "uygulandı (zamanla sıfırlanabilir)".
- Undo is strict LIFO.
- Snapshots go in `%APPDATA%/MobileOptimizer/snapshots/<serial>/<id>.json` on Windows and `~/.local/share/MobileOptimizer/snapshots/<serial>/<id>.json` on Linux. A copy goes to `/sdcard/MobileOptimizer/<id>.json` on the phone.
- The UI language is Turkish. UI strings live in `mobileoptimizer/locale/tr.yaml`.
- The license is GPL-3.0. Debloat entries taken from Universal Android Debloater keep `source: uad`.
- Packaging uses PyInstaller `--onedir` (folder + zip), never `--onefile`. Each release publishes a SHA-256.
- Every commit message ends with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.

## Review Focus

1. **USB cable pulled mid-apply.** All prior values are already in the saved snapshot. Remaining actions are reported `not_run`. Undo of that snapshot restores everything that was applied. Test: Task 7 `test_disconnect_mid_run`.
2. **Package in the list but not installed on this phone.** The action is reported `skipped` ("cihazda yok"), never `failed`, and it is not in the snapshot. Test: Task 7 `test_missing_package_skipped`.
3. **`settings get` prints `null`.** The prior value is recorded as `None`. Revert runs `settings delete`, not `settings put ... null`. Test: Task 5 `test_setting_null_reverts_with_delete`.
4. **Same preset applied twice, then undo all.** The second snapshot records already-changed values. LIFO undo of both returns the original values. Test: Task 6 `test_double_apply_full_undo`.
5. **Phone listed as `unauthorized` or several phones connected.** `devices()` returns the state. The UI shows the "telefondaki izni onaylayın" hint or a picker. Nothing is run on an unauthorized device. Tests: Task 1 `test_devices_parses_states` and Task 9 `test_connect_page_unauthorized_hint`.

---

### Task 1: Project skeleton and ADB wrapper

**Files:**
- Create: `pyproject.toml`, `LICENSE` (GPL-3.0 full text), `.gitignore` (`vendor/`, `dist/`, `build/`, `__pycache__/`), `README.md`
- Create: `mobileoptimizer/__init__.py`, `mobileoptimizer/core/__init__.py`, `mobileoptimizer/core/adb.py`
- Create: `tests/fakes.py`, `tests/conftest.py`, `tests/core/test_adb.py`

**Interfaces:**
- Produces:
  - `class AdbError(Exception)`, `class AdbDisconnected(AdbError)`
  - `@dataclass(frozen=True) class ShellResult: code: int; out: str; err: str`
  - `@dataclass(frozen=True) class DeviceEntry: serial: str; state: str`. `state` is the raw adb state: `"device"`, `"unauthorized"`, or `"offline"`.
  - `class Adb:`
    - `__init__(self, adb_path: Path, serial: str | None = None)`
    - `devices(self) -> list[DeviceEntry]`
    - `shell(self, args: list[str]) -> ShellResult`. Joins args with `shlex.join`. Strips `\r`. Raises `AdbDisconnected` when stderr contains `not found`, `offline`, or `no devices`.
    - `push(self, local: Path, remote: str) -> None`
  - `def find_adb(base: Path | None = None) -> Path`. Search order:
    1. `<base>/vendor/adb/<windows|linux>/adb[.exe]`. `base` defaults to `sys._MEIPASS` when frozen, else the repo root.
    2. `shutil.which("adb")`.
    3. Otherwise raise `AdbError("adb bulunamadı")`.
  - `tests/fakes.py`: `class FakeAdb` with the same public methods as `Adb`. It keeps state in dicts:
    - `props: dict[str, str]`
    - `settings: dict[tuple[str, str], str]`, keyed by `(namespace, key)`
    - `packages: dict[str, str]`, where the value is `"enabled"`, `"disabled"`, or `"uninstalled"` (removed for user 0 but still in the system image)
    - `system_image: set[str]`
    - `appops: dict[tuple[str, str], str]`
    - `buckets: dict[str, int]`
    - `device_config: dict[tuple[str, str], str]`
    - `roles: dict[str, str]`, `ime: str`, `home: str`
    - `pushed: dict[str, str]`
    - `calls: list[list[str]]`
    - `disconnect_after: int | None`: raises `AdbDisconnected` once `len(calls)` reaches it.
    - Later tasks extend it with the exact command shapes they use. Unknown commands raise `AssertionError`.

- [ ] **Step 1: `git init`, write `pyproject.toml`.** Package name `mobileoptimizer`. Python `>=3.11`. Dependencies: `PySide6>=6.7,<7` and `PyYAML>=6.0,<7`. Dev extras: `pytest>=8` and `pytest-qt>=4`. Script entry: `mobileoptimizer = mobileoptimizer.app.main:main`. License: `GPL-3.0-or-later`.
- [ ] **Step 2: Write failing tests** in `tests/core/test_adb.py`. A `fake_run` fixture in `conftest.py` monkeypatches `subprocess.run`.

```python
def test_devices_parses_states(fake_run):
    fake_run.stdout = "List of devices attached\r\nR5CX1\tdevice\r\nabc\tunauthorized\r\n\r\n"
    assert Adb(Path("adb")).devices() == [DeviceEntry("R5CX1", "device"), DeviceEntry("abc", "unauthorized")]

def test_shell_quotes_args_and_strips_cr(fake_run):
    fake_run.stdout = "0.5\r\n"
    r = Adb(Path("adb"), "R5CX1").shell(["settings", "get", "global", "window_animation_scale"])
    assert r.out == "0.5\n"
    assert fake_run.last_args == ["adb", "-s", "R5CX1", "shell", "settings get global window_animation_scale"]

def test_shell_raises_disconnected(fake_run):
    fake_run.returncode, fake_run.stderr = 1, "error: device 'R5CX1' not found"
    with pytest.raises(AdbDisconnected):
        Adb(Path("adb"), "R5CX1").shell(["true"])

def test_find_adb_prefers_vendor_dir(tmp_path, monkeypatch):
    exe = tmp_path / "vendor/adb/linux/adb"; exe.parent.mkdir(parents=True); exe.touch()
    monkeypatch.setattr(sys, "platform", "linux")
    assert find_adb(tmp_path) == exe
```

- [ ] **Step 3: Run** `pytest tests/core/test_adb.py -v`. Expected: FAIL (ImportError).
- [ ] **Step 4: Implement** `adb.py`. Use `subprocess.run(..., capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=120)`. On Windows add `creationflags=subprocess.CREATE_NO_WINDOW`. Implement the `FakeAdb` base.
- [ ] **Step 5: Run** `pytest -v`. Expected: PASS.
- [ ] **Step 6: Commit** `feat: project skeleton and adb wrapper`.

---

### Task 2: Device detection

**Files:**
- Create: `mobileoptimizer/core/device.py`, `tests/core/test_device.py`

**Interfaces:**
- Consumes: `Adb.shell`, `FakeAdb.props`
- Produces:
  - `@dataclass(frozen=True) class DeviceInfo`, with fields:
    - `serial: str`, `manufacturer: str`, `brand: str`, `model: str`
    - `android: str`, `sdk: int`
    - `rom: str`: `"oneui"`, `"miui"`, `"hyperos"`, or `"aosp"`
    - `rom_version: str`
  - `def detect(adb) -> DeviceInfo`: one `getprop` call, then parse the `[key]: [value]` lines.
  - `def display_name(info: DeviceInfo) -> str`. Example: `"Samsung Galaxy A25 — One UI 6.1 — Android 14"`. The model falls back to `ro.product.marketname` when present, else `ro.product.model`.

- [ ] **Step 1: Write failing tests**
  - `test_detect_samsung`: `ro.build.version.oneui=60100` gives `rom == "oneui"` and `rom_version == "6.1"` (major = v//10000, minor = v//100%100).
  - `test_detect_hyperos`: `ro.mi.os.version.name=OS1.0` gives `"hyperos"`. This is checked before MIUI, because HyperOS phones also set the MIUI prop.
  - `test_detect_miui`: only `ro.miui.ui.version.name=V14` gives `"miui"`.
  - `test_detect_generic`: Pixel props give `"aosp"`.
- [ ] **Step 2: Run** `pytest tests/core/test_device.py -v`. Expected: FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run** the tests. Expected: PASS.
- [ ] **Step 5: Commit** `feat: device detection`.

---

### Task 3: Action model, profile loader, validator, code blacklist

**Files:**
- Create: `mobileoptimizer/core/actions.py`, `mobileoptimizer/core/profiles.py`, `mobileoptimizer/core/blacklist.py`
- Create: `tests/core/test_profiles.py`, `tests/data/profiles/*.yaml` (small fixtures)

**Interfaces:**
- Consumes: `DeviceInfo`
- Produces:
  - `ACTION_TYPES = ("setting","package_disable","package_uninstall","appops","standby_bucket","compile","device_config")`
  - `TEMPORARY_TYPES = frozenset({"standby_bucket","device_config","compile"})`
  - `@dataclass(frozen=True) class Action`, with fields:
    - `id: str`, `type: str`, `title: str`, `description: str`
    - `category: Literal["performance","battery","cleanup"]`
    - `risk: Literal["safe","careful","expert"]`
    - `params: Mapping[str, str]`
    - `min_sdk: int | None`, `max_sdk: int | None`
    - `rom: tuple[str, ...]`: empty means any
    - `verified: bool`, `source: str | None`
    - `origin: str`: the name of the profile file the action came from
    - Properties: `temporary -> bool`, `target -> str`, `package -> str | None`
    - Methods: `to_dict() -> dict`, `from_dict(d) -> Action`
  - `Action.target` strings:
    - `setting:<ns>:<key>`
    - `package:<pkg>`, for both package types
    - `appops:<pkg>:<op>`
    - `bucket:<pkg>`
    - `device_config:<ns>:<key>`
    - `compile:<pkg or *>`
  - `params` keys by type:
    - setting: `namespace` (global/system/secure), `key`, `value`
    - package_*: `package`
    - appops: `package`, `op`, `mode`
    - standby_bucket: `package`, `bucket` (`active`/`working_set`/`frequent`/`rare`/`restricted`)
    - compile: `mode` (default `speed-profile`), optional `package`
    - device_config: `namespace`, `key`, `value`
  - `@dataclass(frozen=True) class Profile`, with fields:
    - `name: str`, `brand: str`
    - `match_manufacturers: tuple[str, ...]`
    - `actions: dict[str, Action]`, which includes the actions merged from `extends`
    - `presets: dict[str, tuple[str, ...]]`
    - `blacklist_add: frozenset[str]`
  - `class ProfileError(Exception)`
  - `def load_profile(path: Path, profiles_dir: Path) -> Profile`: resolves `extends`, validates, and puts the action id in error messages.
  - `def load_all(profiles_dir: Path) -> dict[str, Profile]`
  - `def pick_profile(profiles: dict[str, Profile], info: DeviceInfo) -> Profile`: matches lowercase `manufacturer` and `brand` against `match`, else `generic`.
  - `blacklist.py`: `CORE_BLACKLIST: frozenset[str]` contains at least these packages:
    - `android`, `com.android.systemui`, `com.android.settings`, `com.android.phone`
    - `com.android.providers.telephony`, `com.android.providers.settings`
    - `com.google.android.gms`, `com.android.vending`
    - `com.android.packageinstaller`, `com.google.android.packageinstaller`
    - `com.android.shell`
  - `blacklist.py`: `def is_blocked(pkg: str, extra: Iterable[str]) -> bool`
  - Shortcut: `title`/`description` are plain Turkish strings in YAML. Upgrade to `{tr:, en:}` maps when English is added.

YAML shape:

```yaml
brand: samsung
match: [samsung]
extends: generic
blacklist_add: [com.sec.android.app.launcher]
actions:
  - {id: anim_window, type: setting, namespace: global, key: window_animation_scale, value: "0.5",
     category: performance, risk: safe, verified: true, title: "...", description: "..."}
presets:
  max_performance: [anim_window]
```

Validator rules. Each rule has one test.

- `type` must be in `ACTION_TYPES`.
- `id` must be unique after the merge. A child overriding a parent id is an error.
- Package names must match `^[A-Za-z][A-Za-z0-9_]*(\.[A-Za-z0-9_]+)+$`.
- `namespace`/`key`/`op`/`mode`/`bucket` must match `^[A-Za-z0-9_.\-]+$`.
- `value` must match `^[A-Za-z0-9_.,:\-]*$`.
- `package_uninstall` requires `risk: expert`.
- A preset may reference only existing actions with `risk: safe`, `verified: true`, and type not `package_uninstall`.
- A package action on a `CORE_BLACKLIST` or `blacklist_add` package is an error.
- Any top-level or action key outside the schema is an error. In particular, `blacklist_remove` is rejected, which enforces "add only".

- [ ] **Step 1: Write failing tests**
  - `test_rejects_unknown_type`
  - `test_rejects_duplicate_id_across_extends`
  - `test_rejects_bad_package_name`
  - `test_rejects_shell_metachar_value` (value `"1; reboot"`)
  - `test_uninstall_requires_expert`
  - `test_preset_rejects_unverified`
  - `test_preset_rejects_careful`
  - `test_rejects_core_blacklisted_package` (`com.android.systemui`)
  - `test_rejects_brand_blacklisted_package`
  - `test_rejects_blacklist_remove_key`
  - `test_extends_merges_generic_actions`
  - `test_action_dict_roundtrip`
  - `test_pick_profile_redmi_maps_to_xiaomi`
  - `test_pick_profile_unknown_falls_back_generic`
- [ ] **Step 2: Run** `pytest tests/core/test_profiles.py -v`. Expected: FAIL.
- [ ] **Step 3: Implement.** Use `yaml.safe_load` only.
- [ ] **Step 4: Run** the tests. Expected: PASS.
- [ ] **Step 5: Commit** `feat: action model, profile loader and validator`.

---

### Task 4: Runtime guard (device-detected blacklist)

**Files:**
- Create: `mobileoptimizer/core/guard.py`, `tests/core/test_guard.py`

**Interfaces:**
- Consumes: `Adb.shell`, `CORE_BLACKLIST`, `Profile.blacklist_add`
- Produces:
  - `def device_critical_packages(adb) -> frozenset[str]`. It collects:
    - the holders of `android.app.role.DIALER`, `android.app.role.SMS`, and `android.app.role.HOME`, via `cmd role get-role-holders <role>`
    - the IME package: the part before `/` in `settings get secure default_input_method`
    - the HOME package: the last line of `cmd package resolve-activity --brief -a android.intent.action.MAIN -c android.intent.category.HOME`, before `/`
    - Failed or empty lookups are ignored.
  - `def blocked_set(adb, profile: Profile) -> frozenset[str]`: `CORE_BLACKLIST | profile.blacklist_add | device_critical_packages(adb)`

- [ ] **Step 1: Write failing tests**
  - `test_collects_roles_ime_home`
  - `test_failed_lookup_ignored`: the role command exits 255. The result has no error and contains no `""`.
- [ ] **Step 2: Run** the tests. Expected: FAIL.
- [ ] **Step 3: Implement.** Extend `FakeAdb` for these three command shapes.
- [ ] **Step 4: Run** the tests. Expected: PASS.
- [ ] **Step 5: Commit** `feat: runtime critical package guard`.

---

### Task 5: Action executors (capture / apply / verify / revert)

**Files:**
- Create: `mobileoptimizer/core/executors.py`, `tests/core/test_executors.py`

**Interfaces:**
- Consumes: `Action`, `Adb.shell`, `AdbError`
- Produces:
  - `def is_applicable(adb, action: Action) -> str | None`: `None` means the action can run. Otherwise it returns a Turkish reason. `"cihazda yok"` means the package is absent from `pm list packages -u`.
  - `def capture(adb, action: Action) -> object`: the JSON-serializable prior state.
  - `def apply(adb, action: Action) -> None`: raises `AdbError` on a non-zero exit or on `Failure`/`Exception` in stdout.
  - `def verify(adb, action: Action) -> bool`
  - `def revert(adb, action: Action, prior: object) -> str | None`: returns a skip reason if the target no longer exists on the phone (spec 7.6.8), else `None`.

| type | capture | apply | verify | revert |
|------|---------|-------|--------|--------|
| setting | `settings get <ns> <key>`. `"null"` becomes `None`. | `settings put <ns> <key> <value>` | get == value | `None`: `settings delete <ns> <key>`. Else `settings put`. |
| package_disable | `"enabled"`/`"disabled"`/`"uninstalled"` from `pm list packages -d`, `pm list packages`, and `-u` | `pm disable-user --user 0 <pkg>` | pkg in `pm list packages -d` | `enabled`: `pm enable <pkg>`. `uninstalled`: `cmd package install-existing <pkg>`. `disabled`: no-op. |
| package_uninstall | same | `pm uninstall -k --user 0 <pkg>` | pkg not in `pm list packages` | `cmd package install-existing <pkg>`, then `pm disable-user --user 0` if the prior was `disabled` |
| appops | `cmd appops get <pkg> <op>`. Mode word after `: `, or `None` when "No operations". | `cmd appops set <pkg> <op> <mode>` | get == mode | `cmd appops set <pkg> <op> <prior or "default">` |
| standby_bucket | `am get-standby-bucket <pkg>`. Int to name: 5/10=active, 20=working_set, 30=frequent, 40=rare, 45=restricted. | `am set-standby-bucket <pkg> <bucket>` | get == bucket | `am set-standby-bucket <pkg> <prior>` |
| device_config | `device_config get <ns> <key>`. `"null"` becomes `None`. | `device_config put <ns> <key> <value>` | get == value | `None`: `device_config delete <ns> <key>`. Else `put`. |
| compile | `None` | `cmd package compile -m <mode> -f <pkg>`, or `-a` | `True` | no-op |

- [ ] **Step 1: Write failing tests**
  - `test_<type>_roundtrip` for all seven types: capture, apply, verify is True, revert, FakeAdb state equals the original.
  - `test_setting_null_reverts_with_delete` (Review Focus 3)
  - `test_uninstall_revert_restores_disabled_state`
  - `test_revert_package_gone_after_update_returns_reason`: the package is no longer in `system_image`. Expect a non-None reason and no exception.
  - `test_missing_package_not_applicable`
  - `test_apply_failure_in_stdout_raises`: `pm` prints `Failure [...]` with exit 0.
- [ ] **Step 2: Run** `pytest tests/core/test_executors.py -v`. Expected: FAIL.
- [ ] **Step 3: Implement** with a dispatch dict keyed by `action.type`. Extend `FakeAdb`.
- [ ] **Step 4: Run** the tests. Expected: PASS.
- [ ] **Step 5: Commit** `feat: action executors with capture and revert`.

---

### Task 6: Snapshot store, LIFO undo, recovery

**Files:**
- Create: `mobileoptimizer/core/paths.py`, `mobileoptimizer/core/snapshot.py`, `mobileoptimizer/core/recovery.py`
- Create: `tests/core/test_snapshot.py`, `tests/core/test_recovery.py`

**Interfaces:**
- Consumes: `Action.to_dict/from_dict`, `capture`/`revert` (Task 5), `Adb.push`, `Profile`
- Produces:
  - `paths.data_dir() -> Path`: `%APPDATA%/MobileOptimizer` on Windows, else `${XDG_DATA_HOME:-~/.local/share}/MobileOptimizer`.
  - `@dataclass class Entry: action: Action; prior: object; status: str`. `status` is `"pending"`, `"applied"`, `"failed"`, `"not_run"`, or `"reverted"`.
  - `@dataclass class Snapshot: id: str; serial: str; created: str; profile: str; preset: str | None; reverted: bool; entries: list[Entry]`. `id` is a UTC `YYYYMMDDTHHMMSSffffffZ` and sorts in creation order.
  - `class SnapshotStore:`
    - `__init__(self, root: Path)`. The real root is `data_dir()/"snapshots"`.
    - `new(self, serial: str, profile: str, preset: str | None) -> Snapshot`
    - `save(self, snap: Snapshot) -> None`: atomic, temp file + `os.replace`.
    - `list(self, serial: str) -> list[Snapshot]`: oldest first.
    - `load(self, serial: str, snap_id: str) -> Snapshot`
  - `def push_copy(adb, store: SnapshotStore, snap: Snapshot) -> None`: pushes to `/sdcard/MobileOptimizer/<id>.json`. Failure is logged, not raised.
  - `def undo_chain(store, serial: str, snap_id: str) -> list[Snapshot]`: the target plus every later non-reverted snapshot, newest first.
  - `def undo(adb, store, serial: str, snap_id: str) -> list[tuple[str, str | None]]`: reverts entries with status `applied`, in reverse entry order, across the chain. Sets them to `reverted`, sets `reverted=True`, and saves. Returns `(action_id, skip_reason)` pairs.
  - `def can_undo_single(store, serial: str, snap_id: str, action_id: str) -> bool`: False if a later non-reverted snapshot has an `applied` entry with the same `action.target`.
  - `def undo_single(adb, store, serial: str, snap_id: str, action_id: str) -> str | None`
  - `recovery.recover(adb, profile: Profile) -> list[tuple[str, str]]`. For each package action in the profile:
    - if the package is uninstalled for user 0, run `cmd package install-existing`
    - if it is disabled, run `pm enable`
    - Then set `window_animation_scale`, `transition_animation_scale`, and `animator_duration_scale` (global) to `1.0`. It needs no snapshot. Returns `(target, result)` pairs.

- [ ] **Step 1: Write failing tests**
  - `test_save_load_roundtrip`
  - `test_save_leaves_no_tmp_file`
  - `test_undo_chain_lifo`: s1, s2, s3; `undo_chain(s1) == [s3, s2, s1]`.
  - `test_double_apply_full_undo` (Review Focus 4): the setting goes 1.0 → 0.5 in s1 and is applied again in s2. Undo s1 gives `1.0`.
  - `test_can_undo_single_blocked_by_later_snapshot`
  - `test_undo_skips_failed_and_not_run_entries`
  - `test_undo_reports_gone_package_reason`
  - `test_push_copy_failure_does_not_raise`
  - `test_recover_reenables_disabled_and_reinstalls_uninstalled`
  - `test_recover_resets_animation_scales`
- [ ] **Step 2: Run** the tests. Expected: FAIL.
- [ ] **Step 3: Implement.** Snapshots store the full serialized `Action`, so undo works after profile files change.
- [ ] **Step 4: Run** the tests. Expected: PASS.
- [ ] **Step 5: Commit** `feat: snapshots, LIFO undo and recovery`.

---

### Task 7: Session runner (preview, apply, report, drift)

**Files:**
- Create: `mobileoptimizer/core/session.py`, `tests/core/test_session.py`

**Interfaces:**
- Consumes: Tasks 2–6
- Produces:
  - `@dataclass class Preview: to_apply: list[Action]; skipped: list[tuple[Action, str]]`
  - `def build_preview(adb, profile: Profile, info: DeviceInfo, blocked: frozenset[str], *, preset: str | None = None, action_ids: Iterable[str] = ()) -> Preview`. Filters run in this order:
    1. `min_sdk`/`max_sdk` (`"Android sürümü uygun değil"`)
    2. `rom` (`"bu arayüzde yok"`)
    3. if `info.sdk < 29`, keep only `origin == "generic"` and `risk == "safe"` (`"Android sürümü desteklenmiyor"`)
    4. `action.package in blocked` (`"korumalı paket"`)
    5. `is_applicable`
  - `@dataclass class Result: action_id: str; status: str; detail: str`. `status` is `"applied"`, `"applied_temporary"`, `"skipped"`, `"failed"`, or `"not_run"`.
  - `def run(adb, preview: Preview, store: SnapshotStore, serial: str, profile_name: str, preset: str | None, on_progress: Callable[[int, int, Action], None] = lambda *a: None) -> tuple[Snapshot, list[Result]]`:
    1. Capture the priors for all `to_apply` actions.
    2. `store.save`, then `push_copy`.
    3. For each action: apply, verify, set the entry status, `store.save`.
    4. On `AdbDisconnected`: mark the rest `not_run`, save, and return (no raise).
    5. An `AdbError` in one action marks it `failed` with the message and continues. There is no automatic rollback (spec 7.6.7).
    6. Preview skips appear in the results as `skipped`.
  - `def check_drift(adb, store, serial: str) -> list[str]`: `verify` on the `applied` entries of the newest non-reverted snapshot. Returns the ids that fail.

- [ ] **Step 1: Write failing tests**
  - `test_preview_filters_sdk_rom_blocked`
  - `test_old_android_only_generic_safe`
  - `test_missing_package_skipped` (Review Focus 2)
  - `test_snapshot_saved_before_first_apply`: the snapshot file exists before `FakeAdb.calls` has any `put`/`disable-user`.
  - `test_disconnect_mid_run` (Review Focus 1): `disconnect_after` is set mid-run. Expect `not_run` results. Reconnect (reset `disconnect_after`), run `undo`, and the original state is back.
  - `test_failure_continues`
  - `test_temporary_status`
  - `test_check_drift_detects_bucket_change`
- [ ] **Step 2: Run** the tests. Expected: FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run** `pytest -v`. Expected: all PASS.
- [ ] **Step 5: Commit** `feat: session runner with preview, report and drift check`.

---

### Task 8: Profile data (generic, Samsung, Xiaomi) and verification tool

**Files:**
- Create: `mobileoptimizer/profiles/generic.yaml`, `samsung.yaml`, `xiaomi.yaml`
- Create: `mobileoptimizer/tools/__init__.py`, `mobileoptimizer/tools/verify_profile.py`
- Create: `tests/core/test_shipped_profiles.py`

**Interfaces:**
- Consumes: `load_all`, `find_adb`, `Adb`, `is_applicable`, `capture`
- Produces:
  - Three valid profiles, each with `max_performance`, `max_battery`, and `balanced`.
  - `python -m mobileoptimizer.tools.verify_profile --serial <s> --profile <name>`: read-only. Runs `is_applicable` and `capture` per action. Prints `<id> OK`, `<id> MISSING <reason>`, or `<id> NULL` (key absent, so the effect is unknown). It never applies anything.

Content requirements. The exact keys and package lists are the builder's research (spec section 8).

- **generic:**
  - `window_animation_scale`, `transition_animation_scale`, `animator_duration_scale` (global) at `0.5`, `safe`
  - `compile` with `speed-profile` for all packages, `safe`
  - `device_config` Doze/standby keys, `careful`
  - `standby_bucket rare` for common non-critical preinstalled apps, `safe`
- **samsung** (`extends: generic`, match `samsung`):
  - the max refresh rate setting in `max_performance`; 60 Hz in `max_battery`
  - disable Samsung ad/analytics/bloat packages, `safe`
  - Game Optimizing Service, `careful`
  - `blacklist_add` holds the One UI launcher, dialer, contacts, messages, camera, Knox core, OTA updater, and Galaxy Store updater
- **xiaomi** (`extends: generic`, match `xiaomi`, `redmi`, `poco`):
  - disable MSA/analytics/ad packages (for example `com.miui.msa.global`, `com.miui.analytics`) only where `pm disable-user` works on HyperOS
  - refresh rate keys
  - `blacklist_add` holds the launcher, security center, updater, and theme manager core
- `balanced` = cleanup + the three animation scales + compile. No refresh rate, bucket, or device_config actions (spec 7.5).
- UAD-derived entries keep `source: uad`.
- `verified: true` only after `verify_profile` prints `OK` on the matching test phone: the Galaxy A25 for samsung, the Redmi Note 14 4G for xiaomi, and emulators API 29/34/35 for generic.
- Spec 2 lists the "arka plan süreç limiti" (background process limit). It has no action type in spec 7.3 (it is not a `settings` key), so it is **not** in v1. Raise this with the owner rather than adding a new type.

- [ ] **Step 1: Write failing tests**

```python
def test_shipped_profiles_load():
    profiles = load_all(PROFILES_DIR)
    assert {"generic", "samsung", "xiaomi"} <= profiles.keys()
    for p in profiles.values():
        assert {"max_performance", "max_battery", "balanced"} <= p.presets.keys()
        assert p.presets["max_performance"]
```

Also write `test_balanced_has_no_refresh_bucket_or_device_config`.

- [ ] **Step 2: Run** the tests. Expected: FAIL.
- [ ] **Step 3: Write** `verify_profile.py` and the three YAML files.
- [ ] **Step 4: Manual on phones:**
  1. Run `python -m mobileoptimizer.tools.verify_profile --serial <A25> --profile samsung` and the same with `<RedmiNote14> --profile xiaomi`.
  2. Set `verified: true` only on `OK` lines.
  3. On each phone, apply every preset with a throwaway script that uses `session.run`, then `undo`.
  4. Check by hand that calls, SMS, camera, Wi-Fi, mobile data, notifications, and the lock screen still work.
- [ ] **Step 5: Run** `pytest -v`. Expected: PASS.
- [ ] **Step 6: Commit** `feat: shipped profiles for generic, samsung and xiaomi`.

---

### Task 9: PySide6 wizard UI

**Files:**
- Create: `mobileoptimizer/app/__init__.py`, `main.py`, `window.py`, `worker.py`, `i18n.py`
- Create: `mobileoptimizer/app/pages/connect.py`, `device.py`, `profile.py`, `custom.py`, `preview.py`, `apply.py`, `report.py`, `history.py`
- Create: `mobileoptimizer/locale/tr.yaml`
- Create: `tests/app/test_flow.py`

**Interfaces:**
- Consumes: everything in `core`.
- Produces:
  - `i18n.t(key: str, **kw) -> str`: reads `locale/tr.yaml` and calls `str.format(**kw)`. A missing key raises `KeyError`.
  - `window.MainWindow(adb_factory: Callable[[str | None], Adb], store: SnapshotStore, profiles_dir: Path)`: a `QStackedWidget` in spec 7.7 order. The header always shows "Geri al / Geçmiş" and "Yardım".
  - `worker.run_in_thread(fn, *args, on_done, on_error, on_progress=None) -> None`: `QThread`-backed. All ADB calls from the UI go through it.
  - `main.main() -> int`: builds the real `Adb` factory from `find_adb()`. If `AdbError` occurs, it shows `t("error.adb_missing")`.

Page behavior:

- **connect:** Polls `devices()` every 1 s through the worker.
  - 0 devices: show `t("guide.usb_debug")`, plus `t("guide.xiaomi_security")` (the "USB hata ayıklama (Güvenlik ayarları)" option, which needs a Mi account and SIM).
  - `unauthorized`: show `t("connect.unauthorized")`.
  - More than one `device`: show a picker.
  - On Windows, with no device after 30 s: show `t("guide.windows_driver")`.
- **device:** Shows `display_name`. If SDK < 29, shows `t("device.old_android")`. Runs `check_drift`. If it finds drift, shows `t("device.drift", n=...)` with a "Yeniden uygula" button that rebuilds the preview from the last snapshot's action ids.
- **profile:** Radio buttons for Maks Performans, Maks Pil, Dengeli, and Özel.
- **custom:** Tabs for Performans / Pil / Temizlik. Each action has a checkbox, a description, and badges: risk, "geçici" when `temporary`, "doğrulanmamış" when not `verified`. Checking an `expert` action opens a confirm dialog `t("custom.expert_confirm")`. The dialog states that uninstalled system apps come back at factory version.
- **preview:** Lists `to_apply` and `skipped` with reasons, and shows `t("preview.backup_warning")`. "Uygula" stays disabled until the `t("preview.backup_ack")` ("Yedek aldım / anladım") checkbox is ticked.
- **apply:** Shows a progress bar from `on_progress`.
- **report:** Shows counts per status, then each `Result`. Temporary results show "uygulandı (zamanla sıfırlanabilir)". Has a "Geri al" button.
- **history:** Lists snapshots for the serial. Before undo it shows `t("history.chain", n=len(undo_chain(...)))` ("Bu işlem {n} oturumu geri alacak"). Single-action undo is offered only where `can_undo_single`. Also has:
  - "Fabrika ayarına dön": `undo` from the oldest non-reverted snapshot
  - "Kurtarma": `recover`, with its own confirm dialog
- **Yardım menu:** USB guide, Xiaomi guide, Windows driver guide, SmartScreen guide (Task 10).

- [ ] **Step 1: Write failing tests** with `qtbot`, injecting `FakeAdb` via `adb_factory`.
  - `test_full_flow_apply_and_report`
  - `test_apply_disabled_until_backup_ack`
  - `test_connect_page_unauthorized_hint` (Review Focus 5)
  - `test_expert_requires_confirm`
  - `test_history_shows_chain_count`
  - `test_all_tr_keys_exist`: every `t("...")` literal under `mobileoptimizer/app` (regex scan) is a key in `tr.yaml`.
- [ ] **Step 2: Run** `pytest tests/app -v`. Expected: FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run** `pytest -v`. Expected: PASS.
- [ ] **Step 5: Manual.** Run `python -m mobileoptimizer.app.main` with the A25 connected. Walk through Dengeli, apply, report, history, undo, and confirm the phone is back to its original settings.
- [ ] **Step 6: Commit** `feat: wizard UI`.

---

### Task 10: Packaging, bundled adb, unsigned-exe guide

**Files:**
- Create: `scripts/fetch_platform_tools.py`, `scripts/build.py`, `mobileoptimizer.spec`
- Create: `docs/windows-uyari-rehberi.md`, `mobileoptimizer/app/pages/guide_smartscreen.py`
- Modify: `README.md` (download, SHA-256 check, SmartScreen guide link, GPL-3.0, UAD credit)
- Modify: `mobileoptimizer/locale/tr.yaml` (guide strings)

**Interfaces:**
- Consumes: the `find_adb` vendor layout (Task 1). The Yardım menu hook (Task 9).
- Produces:
  - `python scripts/fetch_platform_tools.py`:
    - downloads `https://dl.google.com/android/repository/platform-tools_r35.0.2-windows.zip` and `platform-tools_r35.0.2-linux.zip`
    - checks them against SHA-256 constants pinned in the script. Compute the constants once by hand and commit them.
    - extracts `adb[.exe]`, `AdbWinApi.dll`, `AdbWinUsbApi.dll`, and `NOTICE.txt` into `vendor/adb/<windows|linux>/`
  - `python scripts/build.py`:
    - runs PyInstaller with `mobileoptimizer.spec` (`--onedir`, windowed), bundling `mobileoptimizer/profiles/`, `mobileoptimizer/locale/`, and `vendor/adb/<platform>/`
    - zips the output to `dist/MobileOptimizer-<version>-<platform>.zip` and writes `<zip>.sha256`
  - SmartScreen guide page (Turkish), covering:
    - "Ek bilgi", then "Yine de çalıştır"
    - what to do when an antivirus quarantines the app
    - how to check the hash with `certutil -hashfile <zip> SHA256`

- [ ] **Step 1: Write failing test** `tests/app/test_guides.py::test_smartscreen_guide_strings_exist`: the `guide.smartscreen.*` keys exist and the help menu has the action.
- [ ] **Step 2: Run** the test. Expected: FAIL.
- [ ] **Step 3: Implement** the scripts, spec, guide page, and docs.
- [ ] **Step 4: Run** `python scripts/fetch_platform_tools.py && python scripts/build.py`. Expected: `dist/MobileOptimizer-*-linux.zip` and its `.sha256` exist. Unzip and run the binary: the window opens and lists a connected phone.
- [ ] **Step 5: Manual (Windows).** Build on Windows 10/11 and run the zip on a clean machine. Confirm the SmartScreen steps match the guide. Scan with VirusTotal before release and note false positives in the release notes.
- [ ] **Step 6: Commit** `build: pyinstaller onedir packaging and smartscreen guide`.
