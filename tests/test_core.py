"""Development only: python -m unittest discover -s tests -v (requires Playwright + Chrome)."""
import unittest
from pathlib import Path
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]

class GuideDomainTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.pw = sync_playwright().start()
        cls.browser = cls.pw.chromium.launch(headless=True)
        cls.page = cls.browser.new_page()
        if (ROOT / "app.js").exists():
            cls.page.add_script_tag(path=str(ROOT / "app.js"))

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.pw.stop()

    def run_js(self, expression):
        self.assertTrue(self.page.evaluate("!!window.GuideCore"), "GuideCore implementation is missing")
        return self.page.evaluate(expression)

    def test_seoul_midnight_ignores_device_timezone(self):
        self.assertEqual(self.run_js("GuideCore.seoulDate(new Date('2026-11-03T15:00:00Z'))"), "2026-11-04")
        self.assertEqual(self.run_js("GuideCore.seoulDate(new Date('2026-11-03T14:59:59Z'))"), "2026-11-03")

    def test_strict_90_day_boundary_and_invalid_dates(self):
        result = self.run_js("""GuideCore.annotatePlaces(['2026-08-05','2026-08-04','','2026-11-04','2026-02-30'].map((lastChecked,i)=>({id:String(i),lat:37.5331,lng:126.9969,tier:'unverified',lastChecked,sources:[]})), '2026-11-03').map(p=>p.stale)""")
        self.assertEqual(result, [False, True, True, True, True])

    def test_tiers_do_not_promote_without_evidence(self):
        result = self.run_js("""GuideCore.annotatePlaces([{tier:'certified_seen',certificateExpiry:'2026-01-01',sources:['https://a.example']},{tier:'cross_checked',sources:['https://a.example']},{tier:'self_declared',sources:[]}].map((p,i)=>({...p,id:String(i),lastChecked:'2026-11-03',lat:37.5331,lng:126.9969})), '2026-11-03').map(p=>p.effectiveTier)""")
        self.assertEqual(result, ['unverified','unverified','unverified'])

    def test_filters_exclude_stale_and_distant_records(self):
        self.assertEqual(self.run_js("""GuideCore.filterPlaces([{id:'mosque',type:'mosque',effectiveTier:'unverified',distanceKm:0,stale:false},{id:'near',type:'restaurant',effectiveTier:'self_declared',distanceKm:0.5,stale:false},{id:'far',type:'restaurant',effectiveTier:'unverified',distanceKm:2,stale:false},{id:'old',type:'restaurant',effectiveTier:'unverified',distanceKm:0.2,stale:true}],{type:'restaurant',tier:'all',near:true}).map(p=>p.id)"""), ['near'])

    def test_next_prayer_excludes_sunrise_and_rolls_to_tomorrow(self):
        self.assertEqual(self.run_js("""GuideCore.nextPrayer([{date:'2026-11-03',timings:{Fajr:'05:00',Sunrise:'06:30',Dhuhr:'12:00',Asr:'15:00',Maghrib:'17:30',Isha:'19:00'}},{date:'2026-11-04',timings:{Fajr:'05:01',Sunrise:'06:31',Dhuhr:'12:00',Asr:'15:00',Maghrib:'17:30',Isha:'19:00'}}],Date.parse('2026-11-03T11:00:00Z')).name"""), 'Fajr')
        self.assertEqual(self.run_js("GuideCore.prayerEpoch('2026-11-03','12:00 (KST)')"), 1793674800000)

if __name__ == '__main__':
    unittest.main()
