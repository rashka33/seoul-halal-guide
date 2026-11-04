"""Feature tests against the real page, with geolocation and third-party network doubled."""
import datetime
import functools
import http.server
import json
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
        self.assertEqual(page.locator('.place-card[id*="cafe"]').count(), 0)
