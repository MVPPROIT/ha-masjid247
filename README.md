<p align="center">
  <img src="https://raw.githubusercontent.com/MVPPROIT/ha-masjid247/main/custom_components/masjid247/brand/logo@2x.png" alt="masjid 24/7" height="96">
</p>

# Masjid 24/7 for Home Assistant

Prayer Times for your Masjid in Home Assistant: the Beginning and Jam’aat time of
every Prayer, Sunrise, Jummah, the Hijri Date, and which Prayer is next. These are
each Masjid's own published Timetable on [Masjid 24/7](https://www.masjid247.com), not
calculated times. You can add one Masjid or several.

## Install

### HACS (Recommended)

1. In Home Assistant open **HACS → ⋮ → Custom repositories**.
2. Add `https://github.com/MVPPROIT/ha-masjid247` with type **Integration**.
3. Search HACS for **Masjid 24/7**, open it and press **Download**.
4. Restart Home Assistant.

### Manual

Copy `custom_components/masjid247` into your Home Assistant `config/custom_components/`
folder and restart.

## Set Up

1. Find your **Masjid ID**. Open
   [masjid247.com/clock/setup](https://www.masjid247.com/clock/setup), search for your
   Masjid and press **Add**. The number shown next to it is its Masjid ID, for example
   Leicester Central Mosque is **965**.
2. In Home Assistant go to **Settings → Devices & services → Add integration** and pick
   **Masjid 24/7**.
3. Enter the Masjid ID. For several Masjids, separate them with commas: `965, 2093`.

To add or remove Masjids later, open the integration and press **Configure**. Up to
10 Masjids are supported.

## What You Get

Each Masjid becomes a device with these sensors.

| Sensor | Shows |
|---|---|
| Fajr / Dhuhr / Asr / Maghrib / Isha **Beginning** | When the Prayer begins today |
| Fajr / Dhuhr / Asr / Maghrib / Isha **Jam’aat** | Today's Jam’aat time |
| Sunrise | Today's Sunrise |
| Jummah | The first Jummah of this Friday (or the next one) |
| Next Prayer | `Fajr`, `Dhuhr`, `Jummah`, `Asr`, `Maghrib` or `Isha`; its Beginning and Jam’aat times are attributes |
| Next Jam’aat | When the next Jam’aat is, for triggering automations |
| Hijri Date | The Masjid's Hijri Date, e.g. *28 Jumada al-Awwal 1448* |

Some sensors are added but switched off. You can enable them on the device page:

- **Sehri Ends** (filled in during Ramadan)
- **Zawal**
- Only if your Masjid publishes them: **Asr 2nd Beginning** (e.g. Hanafi), **2nd
  Jam’aat** times, and **Jummah 2**, **3** and so on.

How the values behave:

- Time sensors show **today's** time, in the Masjid's own time zone, so clock changes
  are handled. They switch to the next day's times at midnight.
- Each time sensor has a `tomorrow` attribute.
- If a Masjid leaves Maghrib's Beginning time blank, *Maghrib Beginning* shows the
  Maghrib Jam’aat, as the Masjid 24/7 app does.
- On Fridays *Next Prayer* says **Jummah**, using the Masjid's Dhuhr/Jummah Jam’aat.

## Automation Examples

Pause the TV five minutes before every Jam’aat:

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

Play the Adhan when Asr begins:

```yaml
triggers:
  - trigger: time
    at: sensor.leicester_central_mosque_asr_beginning
actions:
  - action: media_player.play_media
    target:
      entity_id: media_player.kitchen_speaker
    data:
      media_content_id: media-source://media_source/local/adhan.mp3
      media_content_type: music
```

Minutes until the next Jam’aat, as a template:

```jinja
{{ ((as_datetime(states('sensor.leicester_central_mosque_next_jamaat')) - now()).total_seconds() // 60) | int }}
```

## Where the Times Come From

The integration reads a copy of the Masjid 24/7 Timetables kept at
`masjid247.mvppro.co.uk`. Home Assistant never calls Masjid 24/7's own servers. That
copy is refreshed from Masjid 24/7 every 6 hours, so a Masjid's correction shows up
the same day. The first time anyone asks for a Masjid, the copy fetches it once.

How often Home Assistant checks and what it does when offline:

- Home Assistant checks every 3 hours. It downloads two small files per Masjid: this
  month and next.
- The last Timetable is saved, so times keep working through internet or server
  outages, including across a restart.

**Privacy:** requests send nothing but the Masjid ID. The server keeps a standard web
access log (IP address and the file requested).

## Troubleshooting

- *"No Prayer Timetable was found"*: check the number on the setup page. Some Masjids
  on Masjid 24/7 do not publish times.
- *Next month's times missing near the end of the month*: the Masjid has not published
  them yet. They appear once it does.
- Download diagnostics from the integration's ⋮ menu when reporting a problem.

## Upgrading from 1.0.0

1.1.0 renames the sensors to *Beginning* and *Jam’aat*. Existing sensors are renamed in
place and keep their entity IDs and history, so automations keep working.

## Licence

The code is MIT licensed (see `LICENSE`). The Masjid 24/7 name and logo (the images in
`custom_components/masjid247/brand/`) belong to Masjid 24/7 and are not covered by
that licence.
