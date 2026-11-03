# Seoul Halal Guide design

## Purpose and constraints
A free mobile-first field guide for Muslim travelers around Seoul Central Mosque. Plain HTML, CSS and JavaScript, no build, backend, accounts, credentials or paid services. GitHub Pages hosting. All listing content and mosque notes live in data/places.js.

## Proposed approach
Use one page with a prayer-first layout, then map, filters, distance-sorted cards and disclaimer. A map-first approach would bury the most important daily task; a marketing hero would add unnecessary scrolling. The proposed prayer-first approach follows the brief.

## Visual system
White #FFFFFF background; forest #123E32 prayer surface; green #24744C actions; pale green #EEF6F0 supporting areas; ink #182D24; amber #8A5300. Dark green, green, amber and grey tier badges include text. System humanist sans for controls and body, Georgia for the site name only. Left-aligned content, restrained borders, no decorative gradients or stock imagery. Tap targets at least 44px. Prayer times use tabular numerals. Desktop prayer panel spans the content width; map and listings share a two-column region. Mobile stacks everything, with a compact two-row prayer grid.

## Prayer behavior
Seoul timezone determines date and prayer boundaries independently of device timezone. AlAdhan timings are keyed by Seoul date, method and Asr school in localStorage. Default MWL; ISNA, Umm Al-Qura, Diyanet, JAKIM and Kemenag selectable. Prevent stale response races. Cache only matching-day timings. Next prayer excludes sunrise; fetch tomorrow for the post-Isha countdown. Refresh on Seoul midnight and page visibility restoration. Explicit loading, retry and offline states. Countdown ticks each second. Automatic adhan only with opt-in while the page is open; browser playback restrictions and missing audio are explained. Local audio placeholder is allowed. Qibla bearing is fetched and shown relative to true north, without claiming live device orientation.

## Trust and listings
Every record follows the requested schema. Strictly validate YYYY-MM-DD dates, exclude future or missing dates and hide records older than 90 Seoul calendar days. Mark excluded records stale in runtime data without silently changing check dates. Keep all ten unchecked seed businesses unverified with empty dates and TODO comments. Do not invent certification, prices or hours. Mosque details distinguish supplied location from researched claims and use conservative confidence. Surface pending-check counts and an honest empty state. Guard tier promotion: certificate expiry evidence for certified_seen; at least two independent recent sources for cross_checked. Distances use haversine and walking estimates use 5 km/h, clearly approximate. One filtered array drives cards and map markers. Naver directions precede Google. Safe DOM rendering for editable content.

## Data and maintenance
Deliver index.html, styles.css, app.js, data/places.js, DESK_CHECK.md and README.md. README explains a two-minute listing edit, trust fields, rechecking, local preview, audio replacement and GitHub Pages. DESK_CHECK follows the supplied source sequence and independent-source requirement.

## Verification
Check real prayer API response and method IDs against official docs. Browser check desktop and narrow mobile; test all five requested acceptance cases, including stale fixture and filter-marker equality. Check API failures, localStorage denial, next-day rollover and absent audio. Review current web-design-guidelines for semantics, labels, focus, contrast, touch sizes, reduced motion and responsive overflow. Report only tests actually run. GitHub repository creation and deployment depend on available authenticated access; no invented URLs.
