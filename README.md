# SafeFamily Lite — Home Assistant integration

A Home Assistant custom integration for **Elari FixiTime Fun** (and compatible
SafeFamily / Elari kids' smartwatches), running entirely against a private
local backend.

> **2.0.0 is local-only.** The Elari vendor cloud integration has been removed.
> Existing cloud entries cannot be migrated; remove the old entry and add the
> integration again with your local backend URL. The last cloud-capable release
> is preserved in git as `v1.15.4-cloud` / `cloud-legacy`.

## Features

- **Local backend only** — no vendor account, no cloud API, no cloud fallback.
- Position tracking, battery, last contact and watch link state.
- Locate, refresh, restart and take-photo buttons.
- Newest camera photo as an image entity.
- Phonebook management, including guardian protection.
- Voice messages and Home Assistant TTS playback on the watch.
- Short text notifications on the watch screen.
- Four built-in K01 stickers (teal, orange, green, red).
- All data stays on your own hardware.

## Supported devices

| Device | Status |
|---|---|
| Elari FixiTime Fun (RU_K01, model 44) | Tested |
| Other watches speaking the same IW protocol | Likely works, untested |

The watch must be pointed at the local backend. That is a one-time SMS to the
watch's SIM; see the backend's own documentation for the exact command. The
watch dials out to the backend, so no inbound port on your router is needed.

## Installation

### HACS

1. Add this repository as a custom repository in HACS.
2. Install **SafeFamily Lite**.
3. Restart Home Assistant.

### Manual

Copy `custom_components/safefamily_lite` into your Home Assistant
`config/custom_components/` directory and restart.

## Requirements

- A server running the local backend, reachable by the watch.
- Home Assistant able to reach the backend's HTTP API; same LAN is ideal.
- The watch pointed at that backend.
- For TTS, a working `tts.piper` entity (or another TTS engine you explicitly
  choose).

## Configuration

1. **Settings → Devices & Services → Add Integration → SafeFamily Lite**
2. Enter the backend URL, for example `http://192.168.8.20:8080`
3. Optionally give the watch a friendly name; otherwise its IMEI is used.

If the backend is up but no watch has reported yet, setup keeps retrying and
the entities appear once a watch connects.

### Options

| Option | Default | Description |
|---|---|---|
| `local_url` | — | Private backend URL |
| `local_name` | empty | Friendly watch name; empty uses the IMEI |
| `scan_interval` | `60` | Poll interval in seconds, 15–3600 |

## Entities

| Entity | Description |
|---|---|
| `device_tracker.<name>` | Position from the newest fix |
| `sensor.<name>_battery` | Watch battery % |
| `sensor.<name>_last_contact` | Timestamp of the newest sign of life |
| `sensor.<name>_contacts` | Number of entries in the stored phonebook |
| `sensor.<name>_voice_messages` | Number of voice recordings |
| `sensor.<name>_backend_link` | `online` / `offline` |
| `binary_sensor.<name>_tunnel` | Whether the backend's public tunnel is up |
| `button.<name>_locate_now` | Ask the watch for a real-time fix, then re-poll |
| `button.<name>_restart` | Reboot the watch; it returns in about a minute |
| `button.<name>_refresh` | Re-poll the backend immediately |
| `button.<name>_take_photo` | Trigger the watch camera |
| `image.<name>_last_photo` | Newest photo the backend holds |

The tracker carries the detail automations need:

| Attribute | Meaning |
|---|---|
| `source` | How the fix was obtained — `gps`, `unwired`, `opencellid`, `+cache` |
| `accuracy_m` | Estimated error radius in metres |
| `fix_time` | When that fix was taken |
| `online` | Whether the watch has reported recently |
| `last_contact`, `battery`, `firmware`, `imei` | Status and identity |

**Check `accuracy_m` before trusting a position.** Cell-tower fixes are
routinely hundreds of metres to several kilometres off; only a real GPS fix is
street-accurate. GPS is not a setting to switch on: the watch asks for the best
fix it can get, so it reports GPS outdoors and falls back to a tower fix indoors.

The tunnel sensor answers a question none of the others can. The watch reaches
the backend through a public relay, so the backend can be healthy on the LAN
while nothing from the watch arrives. The backend probes that path by
round-tripping a login frame; the sensor goes off after repeated failures, and
reads as *unknown* (not off) if the backend cannot be asked.

## Phonebook (who is allowed to call the watch)

The watch's phonebook is its **call whitelist**. With "Protect from Stranger
Calls" on — the factory default — a caller who is not in the phonebook is
rejected. An empty phonebook therefore means *nobody can reach the child*, the
guardian included.

The backend writes the whole phonebook through the watch's own protocol, keeps
the list, and re-writes it at every login, so a reset heals itself.

| Service | Description |
|---|---|
| `safefamily_lite.set_local_contacts` | Replace the whole phonebook from JSON |
| `safefamily_lite.add_local_contact` | Add or update one contact, storing both forms of the number |
| `safefamily_lite.remove_local_contact` | Remove one contact, every stored form of its number |

```yaml
action: safefamily_lite.add_local_contact
data:
  imei: "123456789012345"
  name: Dad
  number: "+15551234567"
  icon: Father    # or 0-6; see the table below
  sos: true
```

In the service UI, **set phonebook**, **add**, and **remove** all use a watch
device picker. The YAML examples use `imei`, which remains supported for
scripts and existing automations.

`sensor.<name>_contacts` shows the stored list, `pushed_at`, the numbers the
backend refuses to drop (`guardian_numbers`) and whether they are present. It
reports **what the backend last wrote**, not an observation of the watch: the
protocol has no way to read the phonebook back. `unknown` (backend too old to
answer) is kept distinct from `0`, because `0` is the value worth alarming on.

The `icon` is the avatar drawn beside the name, and it is cosmetic — it plays no
part in who may call. In the UI it is a pick-list:

| Value | Name | Value | Name |
|---|---|---|---|
| `0` | Father | `4` | Granny |
| `1` | Mother | `5` | Brother |
| `2` | Sister | `6` | Other |
| `3` | Grandpa | | |

Leaving it out gives **Other** (`6`). The mapping follows the vendor app's
contact list; the avatar rendering itself has not been confirmed on every
firmware revision.

Two things to know before editing the list:

- **A push replaces all 13 slots.** `add_local_contact` reads the stored copy,
  updates one entry and writes the result back, which is the only way to "add"
  to a list that cannot be read from the device. `remove_local_contact` matches
  the number ignoring `+`, spaces and dashes, drops every form of it, and writes
  the rest back. It **fails** if nothing matched, so a typo cannot pass for a
  successful removal.
- **The number is stored in both presentations, automatically.** The firmware
  compares the calling number as a string, and the same subscriber may arrive
  as `+15551234567` or `05551234567` depending on routing, so
  `add_local_contact` writes both. The country comes from Home Assistant's own
  setting — *Settings → System → General → Country* — and the number is
  validated against that country's numbering plan before anything is written.
  A mistyped number is refused instead of stored as an entry that will never
  ring. A number from another country keeps its `+` form only.

Every write declares the guardian with the list: the entry marked SOS is
expanded to every form of its number and sent as the numbers that may not be
dropped, and the backend remembers that guard for later writes. A push that
would remove one fails with the backend's own reason in the UI. `sos: true`
moves the flag to the new entry (the watch has one SOS button), so the guardian
can be changed by adding the new one first, then removing the old one. A list
with no SOS entry is refused, because there would be nothing to protect.

`set_local_contacts` is the raw escape hatch and therefore must include an
entry with `"is_sos": true`. It also replaces the phonebook even when the
backend has no record of one, which is the deliberate way to rebuild a list
after the backend's `state.db` is lost; an add or remove in that state is
refused instead, since it would send a one-entry list over all 13 slots.

## Voice messages and TTS

The local backend can queue an existing AMR file or generate a spoken message
with Home Assistant's TTS engine:

```yaml
action: safefamily_lite.send_tts_voice
data:
  imei: "123456789012345"
  message: "Hello, time to come home."
  engine: tts.piper
  language: en_US
  notify: false
  burst: true
```

In the service UI the watch is a device picker, and `language` is a dropdown
with common codes plus a custom value. The YAML example uses `imei`, which
remains supported for scripts and existing automations; the picker resolves the
same IMEI from the selected device.

`engine` defaults to the local `tts.piper` entity. Pass another TTS entity only
when you deliberately want that provider, since a cloud engine would receive
the message text. `notify: true` sends the immediate audible alert; `burst:
true` pushes the file to a connected watch now. With `notify: false` the burst
is silent and the child can play it when they choose.

The backend converts the TTS engine's MP3/WAV output to AMR-NB before queueing
it; the watch does not accept the original format. `send_local_voice` remains
available for a prepared AMR file:

```yaml
action: safefamily_lite.send_local_voice
data:
  watch: 0123456789abcdef0123456789abcdef
  url: "http://127.0.0.1:8123/local/hello.amr"
  notify: false
```

`url` must be reachable from Home Assistant itself, for example a file in
`/config/www`.

## Text notifications

The watch can show a short message on screen and beep:

```yaml
action: safefamily_lite.send_local_text
data:
  watch: 0123456789abcdef0123456789abcdef
  text: "Time to come home"
```

This is the watch's own notification overlay, not an SMS. It is transient: it
disappears after a moment and does not appear in the Messaging app. Text is
capped at 64 characters. The watch must be connected when the service is
called; the message is never queued, so an offline watch fails instead of
showing the text hours later. In the service UI the watch is a device picker,
and `imei` remains a script fallback.

## Stickers

The watch has four built-in K01 stickers. They use the same transient overlay
as a text notification and are sent as a fixed `k01emN` code, not as free text:

```yaml
action: safefamily_lite.send_local_emoji
data:
  watch: 0123456789abcdef0123456789abcdef
  sticker: Teal
```

Choose `Teal`, `Orange`, `Green` or `Red`. The watch must be connected when
the service is called; the sticker is never queued. It is not an SMS and does
not appear in the Messaging app. All four stickers were confirmed on a
physical K01 on 2026-10-22.

## Services

All services are under the `safefamily_lite.` domain.

| Service | Description |
|---|---|
| `set_local_contacts` | Replace the whole phonebook from JSON |
| `add_local_contact` | Add or update one contact |
| `remove_local_contact` | Remove one contact |
| `send_local_voice` | Queue an AMR file for the watch |
| `send_tts_voice` | Generate and queue a TTS message |
| `send_local_text` | Show a short notification on the watch now |
| `send_local_emoji` | Show one of the four built-in K01 stickers now |

Use **Developer Tools → Actions** to call them. The phonebook, voice, text and
sticker services accept `watch` (device picker) or `imei` (script fallback).

## Example automations

### Notify when the watch goes offline

```yaml
automation:
  - alias: Watch offline alert
    trigger:
      - platform: state
        entity_id: binary_sensor.watch_tunnel
        to: "off"
        for: "00:05:00"
    action:
      - service: notify.mobile_app_phone
        data:
          title: "Watch link is down"
          message: "The backend tunnel has been down for five minutes."
```

### Remind the watch to come home

```yaml
automation:
  - alias: Remind the watch to come home
    trigger:
      - platform: time
        at: "15:30:00"
    condition:
      - condition: state
        entity_id: sensor.watch_backend_link
        state: "online"
    action:
      - service: safefamily_lite.send_tts_voice
        data:
          imei: "123456789012345"
          message: "Time to come home!"
          engine: tts.piper
          notify: false
          burst: true
```

## What is not available yet

The cloud-only feature set was removed in 2.0.0. These are not exposed by the
local backend yet:

- chat and message history
- alarms and class mode / timetable
- vendor geofences
- call history and profile/settings entities
- auto-answer and Care Time
- step goal, steps and vendor diagnostic sensors

Some of these can be rebuilt locally; others depend on vendor services and may
never return. In particular, the heartbeat `signal` and `satellite` values are
hardcoded constants in this watch's firmware, so publishing them as
measurements would be fiction.

## Security notes

- The local backend HTTP API is intended for a trusted LAN. It is not a
  hardened internet-facing service.
- Do not port-forward the backend or the watch's vendor API.
- If you need remote access, use a private tunnel and keep the backend's own
  authentication/allow-list in front of it.
- Phonebook writes are safety-critical: keep the guardian entry and test with
  invalid numbers before changing a real list.
- The backend stores the last-known-good phonebook so a failed push cannot leave
  the watch with an empty whitelist.

## Troubleshooting

**Setup keeps retrying.** The backend is reachable but no watch has logged in
yet. Check the watch's server/APN configuration and the backend log.

**`cannot_connect` during setup.** Check the URL from the Home Assistant host,
not just from your browser. A containerised HA may need the host's LAN address
rather than `localhost`.

**Entities disappear after upgrade.** The old cloud entry is no longer valid.
Remove it under **Settings → Devices & Services**, then add the integration
again with the local backend URL.

**A photo does not arrive.** The backend logs the upload session and drops a
session that stops making progress; the previous photo is kept. Check the
backend log and the watch's camera/flash state.

## Credits

Reverse engineering, integration and testing: @MrAvana

Built with Home Assistant.

## Disclaimer

This project is not affiliated with Elari or any of its subsidiaries. It is
provided for personal use with devices you own. The SafeFamily Lite name and
logo belong to their respective owners.

If you brick your watch or lose access to it while using this integration,
that is on you. Every write operation has been tested on real hardware, but the
underlying protocol is undocumented and may change.
