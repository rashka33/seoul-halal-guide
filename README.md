# Seoul Halal Guide

A free, static, mobile-first guide around Seoul Central Mosque in Itaewon. Plain HTML/CSS/JavaScript: no framework, build, backend, database, account or API key.

## Run locally

Open `index.html` for the static document, or use `python3 -m http.server 8765 --bind 127.0.0.1` and visit http://127.0.0.1:8765. A local HTTP server is recommended for audio and consistent browser storage behavior. Production needs only GitHub Pages. Network access is needed for fresh prayer times, Qibla and OSM tiles. After one online visit over HTTPS or localhost, `sw.js` serves this site's own files offline, including the phrases; it is network first and leaves third-party requests alone. Leaflet 1.9.4 is vendored locally with its license.

## Add a listing in two minutes

The edit takes two minutes **after** the actual desk check. Follow [DESK_CHECK.md](DESK_CHECK.md) first.

1. Open `data/places.js`. Copy an object, give it a unique `id`, and fill its name, exact checked address, coordinates and type (`mosque`, `restaurant`, `grocery`, `prayer_room`, `cafe`). Seed coordinates are rough estimates; check the entrance before publishing.
2. Write a concise `halalBasis`, the URLs you actually read in `sources`, and the real `lastChecked` date in `YYYY-MM-DD`. Set the tier using the rules below. Leave unknown facts `null`, never guess hours or prices. Use price levels 1–3 only if sourced.
3. Add the Naver search/listing URL first and Google Maps URL second. Add relevant notes. Commit the edit. No other file needs changing.

Required fields: `id`, `name`, `type`, `lat`, `lng`, `address`, `area`, `tier`, `halalBasis`, `certifier`, `alcoholServed`, `prayerSpace`, `priceLevel`, `hours`, `lastChecked`, `sources`, `naverUrl`, `googleUrl`, `notes`.

Optional fields, filled only from a desk check and never guessed: `nearestStation` (e.g. “Itaewon Station (Line 6), Exit 3”), `transitTime` (e.g. “About 12 min by subway”, shown after “Typical: ”), `vegetarianOptions` (its own fact line, never part of the halal basis) and `wifi` (`true`/`false`/`null`, shown on café cards only).

Café listings are not halal claims. Their basis says what kind of evidence was found, such as foreigner-visitor reviews and WiFi notes. Tier and freshness rules are the same as for every other place.

### Evidence tiers

- `certified_seen`: an actual certificate photo/listing found online with expiry **in the future**. Also set `certificateUrl` (include it in `sources`) and `certificateExpiry` (`YYYY-MM-DD`). Expired, same-day, unknown or unseen expiry cannot use this tier. Confirm the certificate is for this exact branch and scope.
- `cross_checked`: at least **two independent recent sources** agree. Two URLs from the same business or directory are not independent. Code requires two distinct hostnames as a minimum safeguard; humans must still establish independence, recency and agreement.
- `self_declared`: only the business itself claims halal; link that actual claim in `sources`.
- `unverified`: anything else. Grey badge, no inferred assurance.

Every card says when it was checked and explains its basis. The mosque is in the grey tier: the KMF source establishes the mosque/address/prayer space, not a food certificate. Its record was desk-checked on 2026-11-03. The requested Friday advisory is supplied editorial guidance, not a published fixed Jumu’ah schedule.

### Freshness is mandatory

Missing, invalid or future `lastChecked` dates and dates **older than 90 Seoul calendar days** are hidden from both cards and map. Exactly 90 days old still appears. Runtime `stale: true` is set on excluded records, inspectable in `window.PLACES`; a static site cannot rewrite its source file. Source dates never advance automatically. `GuideCore.annotatePlaces()` derives freshness and `effectiveTier`; an expired certificate is downgraded even during the 90-day window. All fourteen business seeds (ten restaurants and groceries, four cafés) are unverified with empty dates and remain hidden until a real human check. The pending count includes stale and unchecked records regardless of filters. Do not change check dates to fill the page.

Edit the mosque record’s `notes` to update the visible Friday note immediately below prayers. It remains an advisory even when the mosque listing ages out, and does not bypass listing freshness.

## Near me and route links

Near me asks for location only after a tap. The position stays in page memory: it is never written to storage or sent by this site's code. Two things do follow from using it, both visible on the page: re-centering makes the browser fetch OpenStreetMap tiles for that area, and a route link passes the position to Naver or Google if the user taps that link. “Back to mosque order” clears it. The 1.1 km filter always measures from the mosque.

Route links are deep links. Naver starts from the user's position under Near me, otherwise from Seoul Central Mosque. Google omits `origin` unless Near me is active. Arrival times appear only on Naver after the tap; this site never computes them. Naver does not publicly document its web directions format, so `naverRouteUrl` in `app.js` is the one place to change it.

## Useful Korean

`data/phrases.js` is supplied content: do not alter the Korean or romanization. Search covers English and romanization. Tapping a row shows the Hangul full screen to show to a local.

## Prayer times and audio

AlAdhan timings use Seoul’s date/timezone regardless of the visitor’s device timezone. The header’s Hijri date is read **only** from that day’s `data.date.hijri`. It is unavailable until a valid matching response or cache loads; there is no independent conversion. API Hijri dates can differ from local moon sighting.

Calculation IDs: MWL 3 (default), ISNA 2, Umm Al-Qura 4, Diyanet 13 (API marks experimental), JAKIM 17, Kemenag 20. Asr school: Shafi 0, Hanafi 1. Preferences persist in localStorage when available. Timings cache keys include Seoul date, method and school; older-day data is never substituted. “Refresh times” fetches fresh data with matching cache fallback. Settings changes cannot let an older request overwrite a newer choice. Tomorrow is fetched for the post-Isha Fajr countdown. Sunrise is displayed but is not an adhan event. Timings are calculated, not a congregation schedule.

`assets/adhan.mp3` is an intentionally empty **placeholder**. Replace it with an MP3 you have permission to distribute. Until then Play Adhan gives a clear message and automatic playback cannot be armed. Audio needs a user gesture in each tab/session; the saved preference is shown as needing re-arming. Automatic adhan is best effort while this page is **visible and open**. It does not replay missed prayers after suspension, run in the background, send push notifications or promise alarms. Qibla is a bearing clockwise from true north. “Use compass” optionally rotates the arrow against the phone's heading after a tap, where the device allows it. Phone compasses read magnetic north, so treat it as approximate. Without a sensor or permission, the page says so and keeps the bearing.

## Turn on GitHub Pages (free)

1. Create a **public** GitHub repository named `seoul-halal-guide` and push all these files to `main` (keep `index.html` at the root).
2. In the repository choose **Settings → Pages → Build and deployment → Deploy from a branch**.
3. Choose **main**, folder **/ (root)** and **Save**. Wait for GitHub’s deployment to finish.
4. Open the URL displayed by Pages. Relative asset paths work beneath `/seoul-halal-guide/`; no build command is needed. `.nojekyll` is included.

Keep Leaflet’s license and the visible **© OpenStreetMap contributors** attribution. Do not remove or cover map attribution. Map links and source links open a new tab. No analytics or tracking SDK is included.

## Development checks

The site itself has no Python or Playwright dependency. Optional domain checks: install Playwright in a temporary Python environment, run `python -m playwright install chromium --only-shell`, then run `python -m unittest discover -s tests -v`. Tests execute the real JavaScript in Playwright’s headless Chromium. Regression tests start and stop a temporary local static server and cover map-pin keyboard/touch targets and recovery from blocked audio playback. Domain tests cover Seoul midnight, strict freshness, tier safeguards, distance filtering and next-day prayer selection. Feature tests cover Near me (mocked geolocation), route links, cafés, phrases, the overlay, offline reload, the compass and data integrity. Browser acceptance checks should also cover live API loading, countdown, method/school persistence, stale fixtures, map/card agreement, missing audio, offline behavior, mobile overflow, keyboard access and attribution.

## Public sources

- [KMF Seoul Central Mosque](https://www.koreaislam.org/seoul-muslim-info서울중앙성원안내/) — mosque identity, address and prayer facilities.
- [AlAdhan API documentation](https://aladhan.com/prayer-times-api) and [calculation methods](https://api.aladhan.com/v1/methods).
- [Leaflet 1.9.4 documentation](https://leafletjs.com/reference-1.9.4.html).
- [Web Interface Guidelines](https://github.com/vercel-labs/web-interface-guidelines/blob/main/command.md) — accessibility review reference.

Halal information is desk research from public sources, not an inspection or a religious ruling. Certification and opening status change — confirm before you go.
