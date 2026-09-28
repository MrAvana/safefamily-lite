# SafeFamily Lite — Home Assistant integration

A Home Assistant custom integration for the **Elari FixiTime Fun** (and
compatible SafeFamily / Elari kids' smartwatches). Provides local control,
monitoring, and configuration of the watch from Home Assistant — no need to
touch the official app for day-to-day use.

> **Reverse-engineered** from the SafeFamily Lite Android app. This is not
> an official Elari integration.

## Features

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

## Installation

### Via HACS (recommended)

1. In HACS, go to **Integrations → ⋮ → Custom repositories**
2. Add `https://github.com/MrAvana/ha-safefamily-lite` as an **Integration**
3. Search for "SafeFamily Lite" in HACS and install
4. Restart Home Assistant

### Manual

1. Copy `custom_components/safefamily_lite/` into your HA
   `custom_components/` folder.
2. Restart Home Assistant.

## Configuration

**Settings → Devices & Services → Add Integration → SafeFamily Lite**

| Field | Description |
|---|---|
| Email | Your SafeFamily / Elari account email |
| Password | Account password |
| Region | `EU` (most accounts) or `RU` (Belarus/Russia) |

The integration logs in, obtains a JWT, and polls every 5 minutes by default.

### Options

**Settings → Devices & Services → SafeFamily Lite → Configure**

| Option | Default | Range |
|---|---|---|
| `scan_interval` | `300` (5 min) | 30–3600 seconds |

Lower values give faster UI updates but increase API traffic. 60 seconds is
a practical minimum if you want the app and HA to stay close in sync.

## Entities

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
| `sensor.<name>_commands` | Diagnostic dump of all settings |

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
title: Mitia's watch
entities:
  - entity: binary_sensor.mitia_online
  - entity: device_tracker.mitia
  - entity: sensor.mitia_battery
  - entity: sensor.mitia_position_mode
  - entity: sensor.mitia_last_contact
  - entity: sensor.mitia_signal
Quick action card
yaml
type: glance
title: Watch actions
entities:
  - entity: button.mitia_find_watch
  - entity: button.mitia_take_photo
  - entity: button.mitia_restart
  - entity: button.mitia_refresh
Emoji keyboard
yaml
type: glance
title: Send a sticker
entities:
  - entity: button.mitia_send_sticker_1
  - entity: button.mitia_send_sticker_2
  - entity: button.mitia_send_sticker_3
  - entity: button.mitia_send_sticker_4
Live map with fences
yaml
type: map
entities:
  - device_tracker.mitia
  - geo_location.mitia_fence_home
  - geo_location.mitia_fence_school
hours_to_show: 24
Example automations
Notify when the watch goes offline
yaml
automation:
  - alias: Watch offline alert
    trigger:
      - platform: state
        entity_id: binary_sensor.mitia_online
        to: "off"
        for: "01:00:00"
    action:
      - service: notify.mobile_app_avana
        data:
          title: "Mitia's watch is offline"
          message: >
            Last contact:
            {{ state_attr('binary_sensor.mitia_online', 'last_contact') }}
Notify when the watch leaves home
yaml
automation:
  - alias: Watch left home
    trigger:
      - platform: state
        entity_id: device_tracker.mitia
        from: "home"
    action:
      - service: notify.mobile_app_avana
        data:
          title: "Watch left home"
          message: "Mitia is on the move"
Send a message at school pickup time
yaml
automation:
  - alias: Remind Mitia to come home
    trigger:
      - platform: time
        at: "15:30:00"
    condition:
      - condition: state
        entity_id: binary_sensor.mitia_online
        state: "on"
    action:
      - service: safefamily_lite.send_text
        data:
          device_id: "{{ states('sensor.mitia_device_id') | int }}"
          text: "Time to come home!"
Forward alerts to your phone
yaml
automation:
  - alias: Forward watch alerts
    trigger:
      - platform: state
        entity_id: sensor.mitia_alerts
        attribute: last_alert_date
    action:
      - service: notify.mobile_app_avana
        data:
          title: >
            {{ state_attr('sensor.mitia_alerts', 'last_alert_name') }}
          message: >
            {{ state_attr('sensor.mitia_alerts', 'last_alert_message') }}
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

