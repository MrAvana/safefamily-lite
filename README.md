# SafeFamily Lite — Home Assistant integration

A Home Assistant custom integration for the **Elari FixiTime Fun** (and
compatible SafeFamily / Elari kids' smartwatches). Provides local control,
monitoring, and configuration of the watch from Home Assistant — no need to
touch the official app for day-to-day use.

> **Reverse-engineered** from the SafeFamily Lite Android app. This is not
> an official Elari integration.

## Features

- **Two data sources** — the Elari vendor cloud, or your own private backend
  (see [Local backend mode](#local-backend-mode))
- **Live tracking** — GPS/LBS position, battery, signal, steps, satellites
- **Commands** — find watch, restart, power off, take photo
- **Chat** — send text messages and emoji stickers
- **Contacts** — read/add/remove phonebook and SOS contacts with avatars
- **Alarms** — view, add, and delete watch alarms
- **Geofences** — create/edit/delete safe zones; fences render on the HA map
- **Location history** — fetch arbitrary date ranges; today's trail is a sensor
- **Class Mode** — time windows when the watch is silent
- **Class Schedule** — per-day timetable with subjects
- **Camera** — trigger photos, view the latest on a dashboard
- **Care Time** — frequent position updates with configurable interval
- **Settings** — block stranger calls, auto-answer, take-off alert
- **Device pairing** — add/remove watches from HA without the app
- **Hidden calls** — call history (ECP API)

## Supported devices

| Model | Status |
|---|---|
| Elari FixiTime Fun (RU_K01, model 44) | ✅ Fully tested |
| Other Elari / ru-watch.com watches | Likely works, untested |

The backend is `appapi.ru-watch.com`. Two regions are supported by the API
and both are implemented: **EU** (`skills.apps.elari.tech`) and
**RU** (`skills.apps.elari.systems`). Pick the region your account was
registered in during setup.

If that cloud is unreachable — or gone — the same integration can run against
your own server instead, see [Local backend mode](#local-backend-mode).

## Installation

### Via HACS (recommended)

1. In HACS, go to **Integrations → ⋮ → Custom repositories**
2. Add `https://github.com/MrAvana/safefamily-lite` as an **Integration**
3. Search for "SafeFamily Lite" in HACS and install
4. Restart Home Assistant

### Manual

1. Copy `custom_components/safefamily_lite/` into your HA
   `custom_components/` folder.
2. Restart Home Assistant.

## Configuration

**Settings → Devices & Services → Add Integration → SafeFamily Lite**

The first step asks where the watch data should come from: the **Elari vendor
cloud** (email + password, and everything else documented in this README) or a
**local backend** (your own server — position and status only, see
[Local backend mode](#local-backend-mode)).

### Elari vendor cloud

| Field | Description |
|---|---|
| Email | Your SafeFamily / Elari account email |
| Password | Account password |
| Region | `EU` (most accounts) or `RU` (Belarus/Russia) |

The integration logs in, obtains a session token, and polls every 5 minutes
by default. The token is **persisted across restarts**, so Home Assistant
does not need to re-login each time it starts.

### Options

**Settings → Devices & Services → SafeFamily Lite → Configure**

| Option | Default | Range | Mode |
|---|---|---|---|
| `region` | `EU` | `EU` or `RU` | cloud |
| `local_url` | — | any `http://` URL | local |
| `local_name` | watch IMEI | any text | local |
| `scan_interval` | `300` (cloud) / `60` (local) | 30–3600 s (15–3600 local) | both |

Only the options that apply to the configured mode are shown. Changes reload
the integration automatically. Lower scan intervals give faster UI updates but
increase traffic; the watch itself only reports every ~2.5 minutes, so anything
below ~60 seconds just re-reads the same value.

### Upstream outages

If the Elari backend returns a server error (e.g. `HTTP 503` from nginx),
the integration reports **"SafeFamily server unavailable"** and retries
quietly. This is not treated as a credential problem and does not trigger a
re-authentication flow. It recovers automatically once the backend is back.

## Local backend mode

A watch does not have to talk to the vendor at all. It speaks a simple line
protocol of its own, so a small private server can take the cloud's place: it
accepts the watch's connection, answers its login and configuration exchanges,
stores every position and heartbeat the watch reports, and exposes a tiny HTTP
JSON API that this integration polls. Your positions then live on your own
hardware instead of someone else's.

### Requirements

* A server running the backend, reachable *by the watch* (the watch dials out
  to it, so no inbound port on your router is needed).
* Home Assistant able to reach that server's HTTP API — same LAN is ideal.
* The watch pointed at that server. This is a one-time SMS to the watch's SIM;
  the backend's own documentation covers the exact command.

### Setup

1. **Settings → Devices & Services → Add Integration → SafeFamily Lite**
2. Choose **Local backend**
3. Enter the backend URL, for example `http://192.168.8.20:8080`
4. Optionally give the watch a friendly name (otherwise its IMEI is used)

If the backend is up but no watch has reported yet, setup keeps retrying
(Home Assistant shows *Retrying setup*) and the entities appear by themselves
as soon as one connects.

### Entities

| Entity | Description |
|---|---|
| `device_tracker.<name>` | Position from the newest fix |
| `sensor.<name>_battery` | Watch battery % |
| `sensor.<name>_last_contact` | Timestamp of the newest sign of life |
| `sensor.<name>_contacts` | How many numbers are in the watch's phonebook |
| `sensor.<name>_backend_link` | `online` / `offline` |
| `binary_sensor.<name>_tunnel` | Whether the public tunnel to the backend is up |
| `button.<name>_locate_now` | Ask the watch for a real-time fix, then re-poll |
| `button.<name>_restart` | Reboot the watch; it returns in about a minute |
| `button.<name>_refresh` | Re-poll the backend immediately |

The tracker carries the detail automations need:

| Attribute | Meaning |
|---|---|
| `source` | How the fix was obtained — `gps`, `unwired`, `opencellid`, `+cache` |
| `accuracy_m` | Estimated error radius in metres |
| `fix_time` | When that fix was taken |
| `online` | Whether the watch has reported recently |
| `last_contact`, `battery`, `firmware`, `imei` | Status and identity |

**Check `accuracy_m` before trusting a position.** Cell-tower fixes are
routinely 900 m to several kilometres off; only a real GPS fix is
street-accurate. GPS is not a setting to switch on: the watch asks for the best
fix it can get, so it reports GPS outdoors and falls back to a tower fix indoors.
When `source` is `gps` and `accuracy_m` is `null`, the tracker reports a nominal
10 m — the GPS frame carries no HDOP, and 0 would claim the fix is exact. The
`null` is left in place so the substituted value stays visible.

The tunnel sensor answers a question none of the others can. The watch reaches
the backend over a public relay, so the backend can be perfectly healthy on the
LAN while nothing from the watch arrives at all. The backend checks that path by
round-tripping a login frame through the relay every 30 seconds; the sensor goes
off after about 90 seconds of failures, and reads as *unknown* (not off) if the
backend cannot be asked. It is about the tunnel, not the watch —
`sensor.<name>_backend_link` is the one that knows about the watch. `last_probe`
and `age_s` are attributes, so an automation can tell "down" from "down for
20 minutes".

### Phonebook (who is allowed to call the watch)

The watch's phonebook is its **call whitelist**. With "Protect from Stranger
Calls" on — the factory default, and a setting the watch keeps to itself — a
caller who is not in the phonebook is rejected. An empty phonebook therefore
does not mean "no numbers stored": it means *nobody can reach the child*, the
guardian included. That is what a factory reset leaves behind, because the
vendor app was the only thing that used to write the list and its cloud is gone.

`POST /contacts` on the backend writes the whole phonebook through the watch's
own protocol, and the backend keeps the list and re-writes it at every login, so
a reset heals itself. Two services expose that here:

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

Leaving it out gives **Other** (`6`), matching the vendor app's default. The
mapping is taken from the vendor app's contact list rather than confirmed on the
watch — the one entry written so far succeeded as a *call*, which says nothing
about how an avatar renders.

Two things to know before editing the list:

* **A push replaces all 13 slots.** `add_local_contact` reads the stored copy,
  updates one entry and writes the result back, which is the only way to "add"
  to a list that cannot be read from the device. `remove_local_contact` is the
  mirror image: it matches the number ignoring `+`, spaces and dashes, drops
  every form of it, and writes the rest back. It **fails** if nothing matched,
  so a typo cannot pass for a removal that worked.
* **The number is stored in both presentations, automatically.** The firmware
  compares the calling number as a string, and the same subscriber may arrive
  as `+261340000000` or `0340000000` depending on how the call is routed, so
  `add_local_contact` writes both: type either one and the pair is stored,
  international first and that one marked SOS, because a second SOS entry would
  dial the same person twice. This needs the country calling code and domestic
  trunk prefix set once under *Configure* on the integration entry. Without
  them, adding refuses rather than storing half a contact — removing still
  works. Entries written before that setting existed are healed the next time
  anything is added or removed.

  Two presentations mean two of the 13 slots per contact, so six people fill
  the list.

The backend refuses a list that drops a number it is configured to protect
(`CONTACT_REQUIRED`), and the call now fails with the backend's own reason in
the UI — *refusing to remove the guardian number(s)* — rather than the bare
"unknown error" a raw exception used to produce.

### What is not available

Chat, alarms, geofences, photos, class mode and the settings entities all live
in the vendor cloud, so local mode does not create them, and the vendor-only
services are not registered.

Two vendor sensors are deliberately absent: the heartbeat `signal` and
`satellites` values are hardcoded constants in this watch's firmware, so
publishing them as measurements would be fiction.

## Entities

The entities in this section are the **vendor cloud** ones. In
[local backend mode](#local-backend-mode) only the position, battery,
last-contact, phonebook, link and button entities listed above are created.

For each paired watch, the integration creates a device with these entities:

### Sensors

| Entity | Description |
|---|---|
| `sensor.<name>_battery` | Watch battery % |
| `sensor.<name>_steps` | Step count reported by the watch |
| `sensor.<name>_steps_today` | Today's total (from hourly data) |
| `sensor.<name>_satellites` | GPS satellites locked |
| `sensor.<name>_signal` | GSM signal % |
| `sensor.<name>_position_mode` | `GPS` / `LBS` / `WiFi` |
| `sensor.<name>_last_contact` | Timestamp of the last position fix |
| `sensor.<name>_last_heartbeat` | Timestamp of the last keepalive |
| `sensor.<name>_location_history` | Today's distance traveled (km) with trail attributes |
| `sensor.<name>_last_call` | Timestamp of the most recent call |
| `sensor.<name>_call_history` | Total call count + last 50 in attributes |
| `sensor.<name>_profile` | Nickname; full profile in attributes |
| `sensor.<name>_alerts` | Count of alerts; recent alerts in attributes |
| `sensor.<name>_geofences` | Count of fences; full list in attributes |
| `sensor.<name>_friends` | Count of paired friend watches |
| `sensor.<name>_shares` | Accounts with access to this watch |
| `sensor.<name>_alarms` | Count of configured alarms |
| `sensor.<name>_next_alarm` | Timestamp of the next scheduled alarm |
| `sensor.<name>_class_mode` | Count of Class Mode windows |
| `sensor.<name>_timetable` | Count of scheduled subjects |
| `sensor.<name>_messages` | Count of recent messages; list in attributes |
| `sensor.<name>_voice_messages` | Count of voice recordings |
| `sensor.<name>_photos` | Count of photos with URLs |
| `sensor.<name>_contacts` | Count of SOS/phonebook contacts |
| `sensor.<name>_device_id` | The watch's numeric API device ID |
| `sensor.<name>_imei` | The watch's IMEI (SerialNumber) |
| `sensor.<name>_device_info` | Diagnostic: device metadata (model, protocol, activation/expiry, capacity) |
| `sensor.<name>_commands` | Diagnostic dump of all settings |
| `sensor.<name>_sms_commands` | Ready-to-send APN set commands (diagnostic) |

### Device info (diagnostic)

`sensor.<name>_device_info` shows the metadata the API exposes for the watch —
model/type, protocol, IMSI, SIM and main phone, activation/expiry dates,
capacity (`watch_user_count`, `wear`), service contacts, and so on. Fields that
are null or empty are omitted.

The watch **firmware version is not exposed by the API**, so it is not reported.
`protocol` (also used as the device registry software version) and
`device_params` are the closest available signals.

### APN SMS commands (diagnostic)

`sensor.<name>_sms_commands` exposes ready-to-send SMS bodies that change the
watch's APN. Send the text to the watch's SIM from your phone. Its `commands`
attribute is a list of plain `"<label>: <body>"` strings, for example:

```yaml
commands:
  - "Change APN (Telma): APN#0#64604#internet#0#0#0"
  - "Change APN (Orange MG): APN#0#64602#orangenet#0#0#0"
  - "Change APN (Airtel MG): APN#0#64601#internet.mg.airtel.com#0#0#0"
```

The examples ship for Madagascar operators and are defined at the top of
`sms.py` — edit `APN_COMMANDS` to change operators, APNs, or to switch between
the legacy format (`APN#<port>#<mccmnc>#<apn>#<user>#<password>#<ip>`) and the
Apex format (`#APN#=<mccmnc>,<apn>,<user>,<password>,<ip>#`).

The other SMS control commands the app can compose (`u_sms_nowpos`,
`u_sms_tracking`, `u_sms_verifi`, `u_sms_ip`, `u_sms_phone`) were tested
against a retail watch and produced no reaction, so they are not exposed.
Everything else the app can do (find watch, power off, alarms, spy call,
whitelist, class mode, camera, …) goes through the cloud API, not SMS.

### Binary sensor

| Entity | Description |
|---|---|
| `binary_sensor.<name>_online` | `Connected` if the watch reported recently |

The offline threshold is 2 hours by default. Adjust in `const.py`
(`DEFAULT_OFFLINE_AFTER_MIN`) if your watch reports less frequently.

### Device tracker

| Entity | Description |
|---|---|
| `device_tracker.<name>` | Watch position (lat/lng). Attributes: last fix, last contact, position type, speed, battery, signal |

### Buttons

| Entity | Action |
|---|---|
| `button.<name>_restart` | Reboot the watch |
| `button.<name>_find_watch` | Ring / vibrate the watch |
| `button.<name>_power_off` | Power the watch off |
| `button.<name>_take_photo` | Trigger the watch camera |
| `button.<name>_refresh` | Force an immediate re-poll |
| `button.<name>_send_sticker_1..4` | Send one of four emoji stickers |

### Switches

All switches are **verified** against captures from the official app.

| Entity | Effect |
|---|---|
| `switch.<name>_block_stranger_calls` | Only whitelisted numbers can reach the watch (inverted wire) |
| `switch.<name>_auto_answer` | Watch auto-answers incoming calls |
| `switch.<name>_take_off_alert` | Alert when the watch is taken off |
| `switch.<name>_care_time` | Frequent position updates |

### Numbers / Selects / Times

| Entity | Description |
|---|---|
| `number.<name>_step_goal` | Pedometer goal in steps |
| `select.<name>_gender` | Profile gender |
| `select.<name>_care_time_mode` | Update interval (1/5/15/20/25/30/45/60/120 min) |
| `time.<name>_care_time_start` | Care Time window start |
| `time.<name>_care_time_end` | Care Time window end |

### Text / Date inputs

| Entity | Description |
|---|---|
| `text.<name>_nickname` | Owner nickname |
| `text.<name>_phone` | Contact phone (mirrored to `Sim`) |
| `text.<name>_grade` | School grade |
| `date.<name>_birthday` | Owner birthday |

### Images

| Entity | Description |
|---|---|
| `image.<name>_last_emoji` | Most recent emoji sticker received |
| `image.<name>_last_photo` | Most recent camera photo from the watch |

### Geo-location

| Entity | Description |
|---|---|
| `geo_location.<name>_fence_<id>` | One entity per geofence, drawn on the HA map |

## Services

All services are under the `safefamily_lite.` domain. Use
**Developer Tools → Actions** to call them.

### Device management

| Service | Description |
|---|---|
| `check_device` | Validate a watch IMEI; returns pairing info |
| `add_device` | Pair a new watch (runs `check_device` first) |
| `remove_device` | Unpair a watch by its numeric device ID |

### Commands

| Service | Description |
|---|---|
| `send_command` | Send any raw CmdCode |

### Profile

| Service | Description |
|---|---|
| `save_profile` | Update profile fields (nickname, birthday, gender, grade, phone, ...) |

### Contacts

| Service | Description |
|---|---|
| `add_contact` | Add or replace a contact (with avatar picker: Father / Mother / Sister / Grandpa / Granny / Brother / Other) |
| `remove_contact` | Remove a contact by name or number |
| `set_contacts` | Replace the entire list (raw JSON) |

### Alarms

| Service | Description |
|---|---|
| `add_alarm` | Add an alarm (`06:00` + days list) |
| `delete_alarm` | Delete by index or time |
| `set_alarms` | Replace the entire list (raw JSON) |

### Geofences

| Service | Description |
|---|---|
| `geofence_create` | Add a fence (name, lat, lng, radius) |
| `geofence_edit` | Modify an existing fence |
| `geofence_delete` | Remove a fence by ID |
| `list_geofences` | Return the fence list |

### Location

| Service | Description |
|---|---|
| `get_location_history` | Fetch positions for a date range |

### Messages

| Service | Description |
|---|---|
| `send_text` | Send a text message |
| `send_emoji` | Send one of four stickers (`k01em0`..`k01em3`, `0`..`3`, or a label) |
| `mark_message_read` | Mark one message (or all unread) as read; returns count |
| `delete_message` | Delete one message by its `file_id` |
| `delete_all_messages` | Delete all cached text + voice messages; returns count |

### Class Mode

| Service | Description |
|---|---|
| `set_class_mode` | Replace all windows (raw JSON) |
| `add_class_window` | Add a window (`08:00`–`11:30` on Mon,Tue,...) |
| `clear_class_mode` | Remove all windows |

### Class Schedule (timetable)

| Service | Description |
|---|---|
| `set_class_schedule` | Replace the full timetable (raw JSON) |
| `set_class_subject` | Set one cell (day + period + subject) |
| `add_class_period` | Add a new time slot |
| `delete_class_period` | Remove a slot |
| `clear_class_schedule` | Remove all subjects |

## Example dashboards

### Watch status card

```yaml
type: entities
title: My watch
entities:
  - entity: binary_sensor.watch_online
  - entity: device_tracker.watch
  - entity: sensor.watch_battery
  - entity: sensor.watch_position_mode
  - entity: sensor.watch_last_contact
  - entity: sensor.watch_signal
Quick action card
yaml
type: glance
title: Watch actions
entities:
  - entity: button.watch_find_watch
  - entity: button.watch_take_photo
  - entity: button.watch_restart
  - entity: button.watch_refresh
Emoji keyboard
yaml
type: glance
title: Send a sticker
entities:
  - entity: button.watch_send_sticker_1
  - entity: button.watch_send_sticker_2
  - entity: button.watch_send_sticker_3
  - entity: button.watch_send_sticker_4
Live map with fences
yaml
type: map
entities:
  - device_tracker.watch
  - geo_location.watch_fence_home
  - geo_location.watch_fence_school
hours_to_show: 24
Example automations
Notify when the watch goes offline
yaml
automation:
  - alias: Watch offline alert
    trigger:
      - platform: state
        entity_id: binary_sensor.watch_online
        to: "off"
        for: "01:00:00"
    action:
      - service: notify.mobile_app_phone
        data:
          title: "My watch is offline"
          message: >
            Last contact:
            {{ state_attr('binary_sensor.watch_online', 'last_contact') }}
Notify when the watch leaves home
yaml
automation:
  - alias: Watch left home
    trigger:
      - platform: state
        entity_id: device_tracker.watch
        from: "home"
    action:
      - service: notify.mobile_app_phone
        data:
          title: "Watch left home"
          message: "The watch is on the move"
Send a message at school pickup time
yaml
automation:
  - alias: Remind the watch to come home
    trigger:
      - platform: time
        at: "15:30:00"
    condition:
      - condition: state
        entity_id: binary_sensor.watch_online
        state: "on"
    action:
      - service: safefamily_lite.send_text
        data:
          device_id: "{{ states('sensor.watch_device_id') | int }}"
          text: "Time to come home!"
Forward alerts to your phone
yaml
automation:
  - alias: Forward watch alerts
    trigger:
      - platform: state
        entity_id: sensor.watch_alerts
        attribute: last_alert_date
    action:
      - service: notify.mobile_app_phone
        data:
          title: >
            {{ state_attr('sensor.watch_alerts', 'last_alert_name') }}
          message: >
            {{ state_attr('sensor.watch_alerts', 'last_alert_message') }}
Notes and known limitations
Reverse-engineered status
This integration was built by decompiling the SafeFamily Lite Android app
(version 1.0.5) and observing its network traffic. Every command in the
switch platform and every service has been validated against a real capture
of the app, so the wire formats are known to be correct.

Dead commands
Two commands appear in the server's CommandList response but no code path
in the app ever sends them, and the watch does not visibly react:

0144 — labelled "Set the bluetooth switch"

0115 — labelled "Set the body feeling switch"

These have been intentionally omitted from the integration.

Step goal
The step goal (CmdCode 1508) is write-only from the API's perspective.
The app stores its own copy in local SharedPreferences on the phone; the
server never stores or returns the value. As a result:

HA's number.<name>_step_goal remembers what you set (via RestoreEntity)
and pushes it to the watch

The app will show its own cached value — it cannot be synchronized

The watch receives the same 1508 command either way

Treat HA as the authoritative source for the step goal. The app's number
is cosmetic.

Static asset paths
The integration serves two asset folders over HTTP:

/safefamily_lite/emojis/<code>.png — the four sticker images

/safefamily_lite/contact_icons/<name>.svg — the contact avatars

Both are unauthenticated. They contain no sensitive data.

Poll interval
The default 5-minute interval matches the watch's own report cadence. The
server does not implement push notifications to third-party clients, so
faster polling is the only way to get more responsive updates. 60 seconds
is the practical minimum.

Credits
Reverse engineering, integration, and testing: @MrAvana

Built with Home Assistant

Disclaimer
This project is not affiliated with Elari or any of its subsidiaries. It is
provided for personal use with devices you own. The SafeFamily Lite name
and logo belong to their respective owners.

If you brick your watch or lose your account access while using this
integration, that's on you. Every write operation has been tested on real
hardware, but the underlying API is undocumented and could change at any
time.

