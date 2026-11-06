"""Feature tests against the real page, with geolocation and third-party network doubled."""
import datetime
import functools
import hashlib
import http.server
import json
import re
import threading
import unittest
from pathlib import Path
from playwright.sync_api import sync_playwright, expect

ROOT = Path(__file__).resolve().parents[1]
FAILURE = 'Location unavailable — showing distance from the mosque instead'
RECENT = (datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=9))) - datetime.timedelta(days=1)).strftime('%Y-%m-%d')
USER = {'latitude': 37.5595, 'longitude': 126.9849}

def place(id, name, type, lat, lng, **extra):
    return {'id': id, 'name': name, 'type': type, 'lat': lat, 'lng': lng, 'address': 'Test address', 'area': 'Test', 'tier': 'unverified',
            'halalBasis': 'Test fixture.', 'lastChecked': RECENT, 'sources': [], 'nearestStation': '', 'transitTime': '', 'wifi': None, 'vegetarianOptions': '', **extra}

# Test-only records. "far" sits beside USER and well beyond 1.1 km of the mosque.
FIXTURE = [
    place('seoul-central-mosque', 'Seoul Central Mosque', 'mosque', 37.5331, 126.9969),
    place('near', 'Near Grill', 'restaurant', 37.5340, 126.9960),
    place('far', 'Far Grill', 'restaurant', 37.5590, 126.9850),
]

class QuietHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass

class FeatureTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = http.server.ThreadingHTTPServer(('127.0.0.1', 0), functools.partial(QuietHandler, directory=str(ROOT)))
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.url = 'http://127.0.0.1:' + str(cls.server.server_port)
        cls.pw = sync_playwright().start()
        cls.browser = cls.pw.chromium.launch(headless=True)

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.pw.stop()
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join()

    def open(self, init_script='', places=FIXTURE, service_workers='block'):
        context = self.browser.new_context(service_workers=service_workers)
        self.addCleanup(context.close)
        context.route('**/tile.openstreetmap.org/**', lambda route: route.abort())
        context.route('https://api.aladhan.com/v1/qibla/**', lambda route: route.fulfill(json={'code': 200, 'data': {'direction': 292.0}}))
        context.route('https://api.aladhan.com/v1/timings/**', lambda route: route.abort())
        if places is not None:
            context.route('**/data/places.js', lambda route: route.fulfill(body='window.PLACES=' + json.dumps(places), content_type='text/javascript'))
        if init_script:
            context.add_init_script(init_script)
        page = context.new_page()
        page.goto(self.url)
        return page

    def geo_script(self, outcome):
        return """
          window.geoCalls = 0;
          Object.defineProperty(navigator, 'geolocation', {value: {getCurrentPosition(ok, fail) {
            window.geoCalls++;
            %s
          }}});
        """ % outcome

    def geo_success(self):
        return self.geo_script('ok({coords: %s});' % json.dumps(USER))

    def card_ids(self, page):
        return page.locator('.place-card').evaluate_all('cards => cards.map(c => c.id.replace("place-", ""))')

class NearMeTests(FeatureTestCase):
    def test_location_is_requested_only_after_tap(self):
        page = self.open(self.geo_success())
        expect(page.locator('.place-card')).to_have_count(3)
        self.assertEqual(page.evaluate('geoCalls'), 0)
        page.locator('#near-me').click()
        self.assertEqual(page.evaluate('geoCalls'), 1)

    def test_success_sorts_labels_and_recenters_then_resets(self):
        page = self.open(self.geo_success())
        original = self.card_ids(page)
        self.assertEqual(original, ['seoul-central-mosque', 'near', 'far'])
        page.locator('#near-me').click()
        self.assertEqual(self.card_ids(page)[0], 'far')
        expect(page.locator('#place-far .distance')).to_have_text('0.06 km from you')
        expect(page.locator('#result-count')).to_contain_text('distance from you')
        expect(page.locator('.leaflet-tooltip')).to_have_text('You are here')
        expect(page.locator('.you-pin')).to_have_count(1)
        expect(page.locator('#near-me-status')).to_have_text('')
        page.locator('#near-me-reset').click()
        self.assertEqual(self.card_ids(page), original)
        expect(page.locator('.you-pin')).to_have_count(0)
        expect(page.locator('#place-far .distance')).to_contain_text('min walk')
        expect(page.locator('#result-count')).to_contain_text('nearest to Seoul Central Mosque first')
        expect(page.locator('#near-me')).to_be_visible()

    def assert_failure_changes_nothing_else(self, script):
        page = self.open(script)
        before = page.locator('#place-far').inner_text(), self.card_ids(page), page.locator('#result-count').inner_text()
        page.locator('#near-me').click()
        expect(page.locator('#near-me-status')).to_have_text(FAILURE)
        self.assertEqual((page.locator('#place-far').inner_text(), self.card_ids(page), page.locator('#result-count').inner_text()), before)
        expect(page.locator('.you-pin')).to_have_count(0)
        expect(page.locator('#near-me-reset')).to_be_hidden()
        expect(page.locator('#near-me')).to_be_enabled()

    def test_denial_shows_exact_message(self):
        self.assert_failure_changes_nothing_else(self.geo_script("fail({code: 1, message: 'denied'});"))

    def test_no_geolocation_support_shows_exact_message(self):
        self.assert_failure_changes_nothing_else("Object.defineProperty(navigator, 'geolocation', {value: undefined});")

    def test_near_filter_still_measures_from_the_mosque(self):
        page = self.open(self.geo_success())
        page.locator('#near-me').click()
        page.locator('#near-filter').check()
        self.assertEqual(set(self.card_ids(page)), {'seoul-central-mosque', 'near'})

    def test_location_is_not_stored_or_placed_in_request_urls(self):
        page = self.open(self.geo_success())
        requests = []
        page.on('request', lambda request: requests.append(request.url))
        page.locator('#near-me').click()
        expect(page.locator('.you-pin')).to_have_count(1)
        page.wait_for_timeout(200)
        stored = page.evaluate('JSON.stringify([{...localStorage}, {...sessionStorage}, document.cookie])')
        self.assertNotIn('37.5595', stored)
        self.assertNotIn('126.9849', stored)
        for url in requests:
            self.assertNotIn('37.5595', url)
            self.assertNotIn('126.9849', url)

class RouteLinkTests(FeatureTestCase):
    def route_links(self, page, id):
        return page.locator(f'#place-{id} .routes a').evaluate_all('links => links.map(a => [a.textContent, a.href])')

    def test_links_start_at_the_mosque_without_user_location(self):
        page = self.open()
        self.assertEqual(self.route_links(page, 'far'), [
            ['Transit · Naver (live arrivals)', 'https://map.naver.com/p/directions/126.9969,37.5331,Seoul%20Central%20Mosque,,/126.985,37.559,Far%20Grill,,/-/transit'],
            ['Walking · Naver', 'https://map.naver.com/p/directions/126.9969,37.5331,Seoul%20Central%20Mosque,,/126.985,37.559,Far%20Grill,,/-/walk'],
            ['Transit · Google', 'https://www.google.com/maps/dir/?api=1&destination=37.559,126.985&travelmode=transit'],
        ])

    def test_links_start_at_the_user_with_near_me_and_revert_on_reset(self):
        page = self.open(self.geo_success())
        before = self.route_links(page, 'far')
        page.locator('#near-me').click()
        expect(page.locator('.you-pin')).to_have_count(1)
        self.assertEqual(self.route_links(page, 'far'), [
            ['Transit · Naver (live arrivals)', 'https://map.naver.com/p/directions/126.9849,37.5595,My%20location,,/126.985,37.559,Far%20Grill,,/-/transit'],
            ['Walking · Naver', 'https://map.naver.com/p/directions/126.9849,37.5595,My%20location,,/126.985,37.559,Far%20Grill,,/-/walk'],
            ['Transit · Google', 'https://www.google.com/maps/dir/?api=1&origin=37.5595,126.9849&destination=37.559,126.985&travelmode=transit'],
        ])
        page.locator('#near-me-reset').click()
        self.assertEqual(self.route_links(page, 'far'), before)

    def test_every_card_has_three_links_and_no_referrer(self):
        page = self.open()
        expect(page.locator('.routes a')).to_have_count(9)
        self.assertEqual(page.locator('.routes a[rel="noopener noreferrer"]').count(), 9)

    def test_every_card_discloses_what_a_route_link_shares(self):
        page = self.open()
        expect(page.locator('.routes + .route-note')).to_have_count(3)
        expect(page.locator('.route-note').first).to_have_text('Route links open Naver Maps or Google Maps. With Near me on, they share your location with that service.')

    def test_station_and_time_render_only_when_present(self):
        page = self.open(places=[place('a', 'With', 'restaurant', 37.534, 126.996, nearestStation='Itaewon Station (Line 6), Exit 3', transitTime='About 12 min by subway'), place('b', 'Without', 'restaurant', 37.535, 126.996)])
        expect(page.locator('#place-a .facts')).to_contain_text('Nearest station: Itaewon Station (Line 6), Exit 3')
        expect(page.locator('#place-a .facts')).to_contain_text('Typical: About 12 min by subway')
        self.assertNotIn('Nearest station', page.locator('#place-b').inner_text())
        self.assertNotIn('Typical:', page.locator('#place-b').inner_text())

    def test_seed_data_leaves_station_and_time_empty(self):
        page = self.open(places=None)
        fields = page.evaluate('PLACES.map(p => [p.nearestStation, p.transitTime])')
        self.assertTrue(fields)
        self.assertTrue(all(field == ['', ''] for field in fields))

class CafeTests(FeatureTestCase):
    CAFES = FIXTURE + [
        place('cafe-yes', 'Open Cafe', 'cafe', 37.5335, 126.9965, wifi=True, vegetarianOptions='Fully vegan menu', halalBasis='Café listing, not a halal claim.'),
        place('cafe-unknown', 'Quiet Cafe', 'cafe', 37.5336, 126.9966, wifi=None),
        place('cafe-no', 'Busy Cafe', 'cafe', 37.5337, 126.9967, wifi=False),
    ]

    def test_type_filter_shows_only_cafes(self):
        page = self.open(places=self.CAFES)
        expect(page.locator('.place-card')).to_have_count(6)
        page.locator('#type-filter').select_option('cafe')
        self.assertEqual(set(self.card_ids(page)), {'cafe-yes', 'cafe-unknown', 'cafe-no'})
        expect(page.locator('.card-meta span:first-child').first).to_have_text('Café')

    def test_legend_lists_cafe(self):
        page = self.open()
        expect(page.locator('.map-legend')).to_contain_text('Café')

    def test_wifi_line_only_on_cafes(self):
        page = self.open(places=self.CAFES)
        expect(page.locator('#place-cafe-yes .facts')).to_contain_text('Free WiFi: Yes')
        expect(page.locator('#place-cafe-no .facts')).to_contain_text('Free WiFi: No')
        expect(page.locator('#place-cafe-unknown .facts')).to_contain_text('Free WiFi: Not recorded')
        self.assertNotIn('Free WiFi', page.locator('#place-near').inner_text())

    def test_vegetarian_is_its_own_line_never_in_the_basis(self):
        page = self.open(places=self.CAFES)
        expect(page.locator('#place-cafe-yes .facts')).to_contain_text('Vegetarian options: Fully vegan menu')
        self.assertNotIn('egetarian', page.locator('#place-cafe-yes .check-basis').inner_text())
        self.assertNotIn('Vegetarian options', page.locator('#place-cafe-unknown').inner_text())

    def test_stale_cafe_stays_hidden(self):
        page = self.open(places=[place('old', 'Old Cafe', 'cafe', 37.5335, 126.9965, lastChecked=''), place('near', 'Near Grill', 'restaurant', 37.534, 126.996)])
        self.assertEqual(self.card_ids(page), ['near'])

    def test_seed_cafes_match_the_brief_and_stay_hidden(self):
        page = self.open(places=None)
        seeds = {c['id']: c for c in page.evaluate("PLACES.filter(p => p.type === 'cafe')")}
        self.assertEqual({k: (v['wifi'], v['alcoholServed']) for k, v in seeds.items()}, {
            'baraka-cafe': (None, False), 'plant': (True, True), 'downt-espresso': (True, None), 'coffee-lab': (True, True)})
        for seed in seeds.values():
            self.assertEqual((seed['tier'], seed['lastChecked']), ('unverified', ''))
            self.assertGreaterEqual(len(seed['sources']), 2)
        self.assertEqual(seeds['plant']['vegetarianOptions'], 'Fully vegan menu')
        for id in ('plant', 'downt-espresso', 'coffee-lab'):
            self.assertIn('foreigner-visitor reviews', seeds[id]['halalBasis'])
        for seed in seeds.values():
            self.assertIn('not a halal claim', seed['halalBasis'])
            self.assertIn('Evidence type:', seed['halalBasis'])
        self.assertEqual(page.locator('.place-card[id*="cafe"]').count(), 0)

class PhraseTests(FeatureTestCase):
    def test_all_phrases_render_with_all_three_lines(self):
        page = self.open()
        expect(page.locator('.phrase-row')).to_have_count(100)
        expect(page.locator('#phrase-count')).to_have_text('100 phrases')
        first = page.locator('.phrase-row').first
        expect(first.locator('.phrase-en')).to_have_text('Hello')
        expect(first.locator('.phrase-ko')).to_have_text('안녕하세요')
        expect(first.locator('.phrase-rom')).to_have_text('annyeonghaseyo')

    def test_category_chips_use_human_labels_and_filter(self):
        page = self.open()
        self.assertEqual(page.locator('.phrase-chip').all_inner_texts(), ['All', 'Greetings & courtesy', 'Food & halal', 'Vegetarian requests', 'Directions & transport', 'Money & shopping', 'Prayer & mosque', 'Emergencies & help', 'Numbers', 'Label-spotting words'])
        counts = {'Greetings & courtesy': 12, 'Food & halal': 16, 'Vegetarian requests': 6, 'Directions & transport': 14, 'Money & shopping': 10, 'Prayer & mosque': 10, 'Emergencies & help': 10, 'Numbers': 12, 'Label-spotting words': 10, 'All': 100}
        for label, count in counts.items():
            page.get_by_role('button', name=label, exact=True).click()
            expect(page.locator('.phrase-row')).to_have_count(count)
            expect(page.get_by_role('button', name=label, exact=True)).to_have_attribute('aria-pressed', 'true')

    def test_search_covers_english_and_romanization_within_category(self):
        page = self.open()
        page.locator('#phrase-search').fill('POLICE')
        expect(page.locator('.phrase-row')).to_have_count(1)
        page.locator('#phrase-search').fill('gamsahamnida')
        expect(page.locator('.phrase-row')).to_have_count(3)
        page.get_by_role('button', name='Greetings & courtesy', exact=True).click()
        expect(page.locator('.phrase-row')).to_have_count(2)
        page.locator('#phrase-search').fill('zzzz')
        expect(page.locator('#phrase-count')).to_have_text('0 phrases')

    def open_overlay(self, page):
        page.locator('.phrase-row').first.click()
        expect(page.locator('#phrase-overlay')).to_be_visible()

    def test_overlay_is_full_screen_with_very_large_hangul(self):
        page = self.open()
        self.open_overlay(page)
        expect(page.locator('#overlay-ko')).to_have_text('안녕하세요')
        expect(page.locator('#overlay-en')).to_have_text('Hello')
        box = page.locator('#phrase-overlay').bounding_box()
        self.assertEqual((box['width'], box['height']), (page.viewport_size['width'], page.viewport_size['height']))
        size = page.locator('#overlay-ko').evaluate('n => parseFloat(getComputedStyle(n).fontSize)')
        english = page.locator('#overlay-en').evaluate('n => parseFloat(getComputedStyle(n).fontSize)')
        self.assertGreaterEqual(size, 56)
        self.assertGreater(size, english * 3)

    def test_overlay_closes_by_tap_anywhere_close_button_and_escape(self):
        page = self.open()
        self.open_overlay(page)
        page.locator('#overlay-ko').click()
        expect(page.locator('#phrase-overlay')).to_be_hidden()
        self.open_overlay(page)
        page.locator('#overlay-close').click()
        expect(page.locator('#phrase-overlay')).to_be_hidden()
        self.open_overlay(page)
        page.keyboard.press('Escape')
        expect(page.locator('#phrase-overlay')).to_be_hidden()
        self.assertEqual(page.evaluate('document.activeElement.className'), 'phrase-row')

    def test_longest_phrase_fits_a_small_phone_without_side_scroll(self):
        page = self.open()
        page.set_viewport_size({'width': 320, 'height': 568})
        page.locator('#phrase-search').fill('kindness')
        self.open_overlay(page)
        self.assertLessEqual(page.locator('#phrase-overlay').evaluate('n => n.scrollWidth'), 320)

    def test_phrases_and_page_work_offline_from_cache(self):
        page = self.open(places=None, service_workers='allow')
        page.evaluate('navigator.serviceWorker.ready.then(() => true)')
        page.context.set_offline(True)
        page.reload()
        expect(page.locator('.phrase-row')).to_have_count(100)
        self.open_overlay(page)
        expect(page.locator('#overlay-ko')).to_have_text('안녕하세요')

class CompassTests(FeatureTestCase):
    BEARING_ONLY = "rotate(292deg)"

    def ready(self, init_script=''):
        page = self.open(init_script)
        expect(page.locator('#qibla-bearing')).to_have_text('292.0°')
        return page

    def fire(self, page, alpha):
        page.evaluate("alpha => window.dispatchEvent(new DeviceOrientationEvent('deviceorientationabsolute', {alpha, absolute: true}))", alpha)

    def test_heading_math(self):
        page = self.ready()
        self.assertEqual(page.evaluate("GuideCore.headingFromEvent({webkitCompassHeading: 40, alpha: 1, absolute: true})"), 40)
        self.assertEqual(page.evaluate("GuideCore.headingFromEvent({alpha: 90, absolute: true})"), 270)
        self.assertIsNone(page.evaluate("GuideCore.headingFromEvent({alpha: 90, absolute: false})"))
        self.assertEqual(page.evaluate("GuideCore.arrowRotation(292, 300)"), 352)

    def test_arrow_follows_heading_then_stop_restores_bearing(self):
        page = self.ready()
        page.locator('#use-compass').click()
        expect(page.locator('#use-compass')).to_have_text('Stop compass')
        self.fire(page, 90)
        self.assertEqual(page.locator('#qibla-arrow').evaluate('n => n.style.transform'), 'rotate(22deg)')
        expect(page.locator('#qibla-bearing')).to_have_text('292.0°')
        page.locator('#use-compass').click()
        self.assertEqual(page.locator('#qibla-arrow').evaluate('n => n.style.transform'), self.BEARING_ONLY)
        self.fire(page, 10)
        self.assertEqual(page.locator('#qibla-arrow').evaluate('n => n.style.transform'), self.BEARING_ONLY)

    def assert_falls_back(self, page):
        expect(page.locator('#compass-status')).to_have_text('Compass unavailable on this device. Use the bearing above.', timeout=6000)
        expect(page.locator('#qibla-bearing')).to_have_text('292.0°')
        expect(page.locator('#use-compass')).to_have_text('Use compass')
        self.assertEqual(page.locator('#qibla-arrow').evaluate('n => n.style.transform'), self.BEARING_ONLY)

    def test_permission_is_requested_only_after_tap_and_denial_falls_back(self):
        page = self.ready("window.asks = 0; DeviceOrientationEvent.requestPermission = async () => { window.asks++; return 'denied'; };")
        self.assertEqual(page.evaluate('asks'), 0)
        page.locator('#use-compass').click()
        self.assert_falls_back(page)
        self.assertEqual(page.evaluate('asks'), 1)

    def test_no_sensor_support_falls_back(self):
        page = self.ready('delete window.DeviceOrientationEvent;')
        page.locator('#use-compass').click()
        self.assert_falls_back(page)

    def test_no_reading_times_out_to_fallback(self):
        page = self.ready()
        page.locator('#use-compass').click()
        self.assert_falls_back(page)

class AdhanTests(FeatureTestCase):
    CAPTURE = """
      window.qaAudios = [];
      const OriginalAudio = window.Audio;
      window.Audio = function(...args) { const audio = new OriginalAudio(...args); window.qaAudios.push(audio); return audio; };
    """

    def wait_until_playing(self, page):
        page.wait_for_function('qaAudios[0] && !qaAudios[0].paused && qaAudios[0].currentTime > 0')

    def test_nothing_loads_until_a_tap(self):
        page = self.open(self.CAPTURE)
        requests = []
        page.on('request', lambda request: requests.append(request.url))
        page.wait_for_timeout(300)
        self.assertEqual(page.evaluate('qaAudios.length'), 0)
        self.assertFalse([url for url in requests if 'adhan.mp3' in url])

    def test_button_plays_the_real_recording_then_stops(self):
        page = self.open(self.CAPTURE)
        page.locator('#play-adhan').click()
        self.wait_until_playing(page)
        expect(page.locator('#audio-status')).to_contain_text('Playing adhan')
        expect(page.locator('#play-adhan')).to_have_text('Stop Adhan')
        self.assertAlmostEqual(page.evaluate('qaAudios[0].duration'), 154, delta=1)
        self.assertFalse(page.evaluate('qaAudios[0].muted'))
        page.locator('#play-adhan').click()
        expect(page.locator('#play-adhan')).to_have_text('Play Adhan')
        self.assertTrue(page.evaluate('qaAudios[0].paused'))

    def test_automatic_toggle_unlocks_silently_and_plays_at_prayer_time(self):
        now = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=9))).replace(hour=11, minute=59, second=50, microsecond=0)
        timings = {name: time for name, time in zip(['Fajr', 'Sunrise', 'Dhuhr', 'Asr', 'Maghrib', 'Isha'], ['05:00', '06:30', '12:00', '15:00', '17:30', '19:00'])}
        def fulfill(route):
            date = route.request.url.split('/timings/')[1].split('?')[0]
            route.fulfill(json={'code': 200, 'data': {'timings': timings, 'date': {'gregorian': {'date': date}, 'hijri': {'day': '1', 'month': {'en': 'Test'}, 'year': '1448'}}, 'meta': {'timezone': 'Asia/Seoul', 'method': {'id': 3}, 'school': 'STANDARD'}}})
        context = self.browser.new_context(service_workers='block')
        self.addCleanup(context.close)
        context.route('**/tile.openstreetmap.org/**', lambda route: route.abort())
        context.route('https://api.aladhan.com/v1/qibla/**', lambda route: route.abort())
        context.route('https://api.aladhan.com/v1/timings/**', fulfill)
        context.add_init_script(self.CAPTURE + "window.qaMuted = []; const play = HTMLMediaElement.prototype.play; HTMLMediaElement.prototype.play = function() { window.qaMuted.push(this.muted); return play.call(this); };")
        page = context.new_page()
        page.clock.install(time=now)
        page.goto(self.url)
        page.clock.run_for(1000)
        expect(page.locator('#countdown')).to_contain_text('Dhuhr')
        page.locator('#auto-adhan').click()
        expect(page.locator('#audio-status')).to_contain_text('Automatic adhan is on')
        self.assertEqual(page.evaluate('qaMuted'), [True])
        self.assertTrue(page.evaluate('qaAudios[0].paused'))
        self.assertFalse(page.evaluate('qaAudios[0].muted'))
        page.clock.run_for(12000)
        self.wait_until_playing(page)
        self.assertEqual(page.evaluate('qaMuted'), [True, False])
        expect(page.locator('#audio-status')).to_contain_text('Playing adhan')

    def test_credit_stays_visible_and_names_the_source(self):
        page = self.open()
        credit = page.locator('.adhan-credit')
        expect(credit).to_contain_text('Adam-synagda')
        expect(credit).to_contain_text('CC0')
        expect(credit.locator('a')).to_have_attribute('href', 'https://commons.wikimedia.org/wiki/File:Beautiful_adhan.ogg')
        page.locator('#play-adhan').click()
        expect(credit).to_be_visible()

    def test_placeholder_wording_is_gone(self):
        for name in ('index.html', 'app.js', 'README.md', 'assets/README.md'):
            self.assertNotIn('placeholder', (ROOT / name).read_text().lower(), name)
        self.assertGreater((ROOT / 'assets/adhan.mp3').stat().st_size, 1000000)

class IntegrityTests(unittest.TestCase):
    SITE = ['index.html', 'app.js', 'styles.css', 'sw.js', 'data/places.js', 'data/phrases.js', 'README.md', 'DESK_CHECK.md', 'docs/DESIGN.md', 'tests/test_features.py']

    def test_no_banned_wording(self):
        for name in self.SITE:
            self.assertNotIn('verified' + ' halal', (ROOT / name).read_text().lower(), name)

    def test_only_approved_edits_differ_from_the_supplied_phrases(self):
        data = (ROOT / 'data/phrases.js').read_bytes()
        fixed = 'romanization:"yeogiseo sewojuseyo"'.encode()
        self.assertEqual(data.count(fixed), 1)
        data = data.replace(fixed, 'romanization:"yeogiseo sewojuseoyo"'.encode())
        for tail in ('category:"vegetarian"},\n  {en:"Where is Itaewon'.encode(), 'category:"prayer"},\n  {en:"Help!"'.encode()):
            self.assertEqual(data.count(tail), 1)
            data = data.replace(tail, tail.replace(b'},', b'}'))
        self.assertEqual(hashlib.sha256(data).hexdigest(), 'd0a945f4226f0296cd0e5f9cbce94f01403383cb68b6ee0291bca0ae1f440bdd')

    def test_every_seed_is_unverified_with_no_check_date(self):
        text = (ROOT / 'data/places.js').read_text()
        records = re.findall(r"^  \{id:'([^']+)'.*$", text, re.M)
        lines = [line for line in text.splitlines() if line.startswith("  {id:'")]
        self.assertEqual(len(records), 14)
        for line in lines:
            self.assertIn("lastChecked:''", line)
            self.assertIn("tier:'unverified'", line)
