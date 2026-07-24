# BlueStacks1 final E2E — 2026-07-24

- Kodi: `21.3`
- Repository: public `repository.mwodevelop.testing` `1.0.0`
- Umbrella: `6.7.81.7`
- MwoScrapers: `0.1.2`
- Initial state: Umbrella and MwoScrapers absent
- User action: install Umbrella only
- Dependency result: Kodi automatically installed MwoScrapers
- Test content: `Sintel` (2010), IMDb `tt1727587`
- Provider: Torrentio through MwoScrapers
- Sources displayed: 5
- Playback observed: at least 50 seconds of 14:48
- Video/audio: Android H.264 decoder and AAC decoder
- Result: PASS

The machine-readable record is
`2026-07-24-bluestacks1-clean-dependency.json`. It contains the installed
versions, before/after dependency state, safe Kodi installation markers, and
the playback markers from input stream creation through player close.

The test is reproducible with the three phases of
`tests/e2e/bluestacks_e2e.py`: `prepare`, `verify`, and `playback`. Installation
and source selection intentionally go through Kodi's GUI; the script never
injects an add-on into Kodi's profile.
