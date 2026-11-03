"""Regression tests use a temporary static test server; no site backend is required."""
import functools
import http.server
import io
import threading
import unittest
import wave
from pathlib import Path
from playwright.sync_api import sync_playwright, expect

ROOT = Path(__file__).resolve().parents[1]

class QuietHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass

class GuideBrowserRegressions(unittest.TestCase):
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

    def test_map_pin_has_44px_keyboard_target(self):
        page = self.browser.new_page()
        try:
            page.goto(self.url)
            pin = page.get_by_role('button', name='Open Seoul Central Mosque listing')
            expect(pin).to_be_visible()
            box = pin.bounding_box()
            self.assertGreaterEqual(box['width'], 44)
            self.assertGreaterEqual(box['height'], 44)
            pin.press('Enter')
            expect(page.locator('.leaflet-popup')).to_be_visible()
            self.assertEqual(page.evaluate('document.activeElement.id'), 'place-seoul-central-mosque')
        finally:
            page.close()

    def test_blocked_audio_unlock_restores_manual_volume(self):
        context = self.browser.new_context()
        buf = io.BytesIO()
        with wave.open(buf, 'wb') as recording:
            recording.setnchannels(1)
            recording.setsampwidth(2)
            recording.setframerate(8000)
            recording.writeframes(b'\0\0' * 800)
        # Only the browser playback-policy boundary is doubled; real Audio, volume,
        # page state, controls and audio-fetch code are exercised.
        context.route('**/assets/adhan.mp3', lambda route: route.fulfill(body=buf.getvalue(), content_type='audio/wav'))
        context.add_init_script("""
          window.qaAudios = [];
          const OriginalAudio = window.Audio;
          window.Audio = function(...args) {
            const audio = new OriginalAudio(...args);
            window.qaAudios.push(audio);
            return audio;
          };
          let attempts = 0;
          HTMLMediaElement.prototype.play = function() {
            return ++attempts === 1
              ? Promise.reject(new DOMException('Simulated browser policy', 'NotAllowedError'))
              : Promise.resolve();
          };
        """)
        try:
            page = context.new_page()
            page.goto(self.url)
            page.locator('#auto-adhan').click()
            expect(page.locator('#audio-status')).to_contain_text('could not start')
            self.assertEqual(page.evaluate('qaAudios[0].volume'), 1)
            page.locator('#play-adhan').click()
            expect(page.locator('#audio-status')).to_contain_text('Playing adhan')
            self.assertEqual(page.evaluate('qaAudios[0].volume'), 1)
        finally:
            context.close()
