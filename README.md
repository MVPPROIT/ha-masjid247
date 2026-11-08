<p align="center">
  <img src="https://raw.githubusercontent.com/MVPPROIT/ha-masjid247/main/custom_components/masjid247/brand/logo@2x.png" alt="masjid 24/7" height="96">
</p>

# Masjid 24/7 for Home Assistant

Prayer times for your masjid in Home Assistant: the start and jamaat time of every
prayer, sunrise, Jummah, the Hijri date, and which prayer is next. These are each
masjid's own published timetable on [Masjid 24/7](https://www.masjid247.com), not
calculated times. You can add one masjid or several.

## Install

### HACS (recommended)

1. In Home Assistant open **HACS → ⋮ → Custom repositories**.
2. Add `https://github.com/MVPPROIT/ha-masjid247` with type **Integration**.
3. Search HACS for **Masjid 24/7**, open it and press **Download**.
4. Restart Home Assistant.

### Manual

Copy `custom_components/masjid247` into your Home Assistant `config/custom_components/`
folder and restart.

## Set up

1. Find your masjid's **Masjid ID**. Open
   [masjid247.com/clock/setup](https://www.masjid247.com/clock/setup), search for your
   masjid and press **Add**. The number shown next to it is its ID, for example
   Leicester Central Mosque is **965**.
2. In Home Assistant go to **Settings → Devices & services → Add integration** and pick
   **Masjid 24/7**.
3. Enter the ID. For several masjids, separate them with commas: `965, 2093`.

To add or remove masjids later, open the integration and press **Configure**. Up to
10 masjids are supported.

## What you get

Each masjid becomes a device with these sensors.

| Sensor | Shows |
|---|---|
| Fajr / Dhuhr / Asr / Maghrib / Isha **begins** | When the prayer starts today |
| Fajr / Dhuhr / Asr / Maghrib / Isha **jamaat** | Today's jamaat time |
| Sunrise | Today's sunrise |
| Jummah | The first Jummah of this Friday (or the next one) |
| Next prayer | `Fajr`, `Dhuhr`, `Jummah`, `Asr`, `Maghrib` or `Isha`; its start and jamaat are attributes |
| Next jamaat | When the next jamaat is, for triggering automations |
| Hijri date | The masjid's Hijri date, e.g. *28 Jumada al-Awwal 1448* |

Some sensors are added but switched off. You can enable them on the device page:

- **Sehri ends** (filled in during Ramadan)
- **Zawal**
- Only if your masjid publishes them: a second Asr start (e.g. Hanafi), second jamaat
  times, and Jummah 2, 3 and so on.

How the values behave:

- Time sensors show **today's** time, in the masjid's own time zone, so clock changes
  are handled. They switch to the next day's times at midnight.
- Each time sensor has a `tomorrow` attribute.
- If a masjid leaves Maghrib's start time blank, *Maghrib begins* shows the Maghrib
  jamaat, as the Masjid 24/7 app does.
- On Fridays *Next prayer* says **Jummah**, using the masjid's Dhuhr/Jummah jamaat.

## Automation examples

Pause the TV five minutes before every jamaat:

```yaml
triggers:
  - trigger: time
    at:
      entity_id: sensor.leicester_central_mosque_next_jamaat
      offset: "-00:05:00"
actions:
  - action: media_player.media_pause
    target:
      entity_id: media_player.living_room_tv
```

Play the adhan when Asr begins:

```yaml
triggers:
  - trigger: time
    at: sensor.leicester_central_mosque_asr_begins
actions:
  - action: media_player.play_media
    target:
      entity_id: media_player.kitchen_speaker
    data:
      media_content_id: media-source://media_source/local/adhan.mp3
      media_content_type: music
```

Minutes until the next jamaat, as a template:

```jinja
{{ ((as_datetime(states('sensor.leicester_central_mosque_next_jamaat')) - now()).total_seconds() // 60) | int }}
```

## Where the times come from

The integration reads a copy of the Masjid 24/7 timetables kept at
`masjid247.mvppro.co.uk`. Home Assistant never calls Masjid 24/7's own servers. That
copy is refreshed from Masjid 24/7 every 6 hours, so a masjid's correction shows up
the same day. The first time anyone asks for a masjid, the copy fetches it once.

How often Home Assistant checks and what it does when offline:

- Home Assistant checks every 3 hours. It downloads two small files per masjid: this
  month and next.
- The last timetable is saved, so times keep working through internet or server
  outages, including across a restart.

**Privacy:** requests send nothing but the Masjid ID. The server keeps a standard web
access log (IP address and the file requested).

## Troubleshooting

- *"No prayer timetable was found"*: check the number on the setup page. Some masjids
  on Masjid 24/7 do not publish times.
- *Next month's times missing near the end of the month*: the masjid has not published
  them yet. They appear once it does.
- Download diagnostics from the integration's ⋮ menu when reporting a problem.

## Licence

The code is MIT licensed (see `LICENSE`). The Masjid 24/7 name and logo (the images in
`custom_components/masjid247/brand/`) belong to Masjid 24/7 and are not covered by
that licence.
