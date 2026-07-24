# BlueStacks1 E2E — 2026-07-24

- Device: `BlueStacks1` (`127.0.0.1:5556`)
- Kodi: `21.2`
- Repository: `repository.mwodevelop.testing` `1.0.0`
- Umbrella playback build: `6.7.81.4`
- MwoScrapers: `0.1.1`
- External provider selected through Kodi GUI: `script.module.mwoscrapers`
- Test content: `Sintel` (2010), IMDb `tt1727587`
- Sources displayed: 5, all from Torrentio through MwoScrapers
- Real-Debrid attempts before success: 4
- Kodi player: internal video player, speed `1`
- Observed playback: 31 seconds of 14:48
- Test-window RD codes `34` / `35`: 0 / 0
- Result: PASS

The earlier `Big Buck Bunny` control run proved a mislabeled provider result:
the selected hash was named as the test movie but Real-Debrid exposed a
different 2025 file. Umbrella rejected it without playback. This distinguishes
bad source metadata from transport/resolver failure.

During the successful Sintel run, one candidate returned an empty unrestrict
URL. Playback continued with the next source; the resulting diagnostic
`None.endswith` was fixed by the forward release `6.7.81.5`.

Installation and device validation are reproducible with
`tests/e2e/bluestacks_e2e.py`; deterministic repository HTTP E2E is
`tests/e2e/run.sh`.
