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
