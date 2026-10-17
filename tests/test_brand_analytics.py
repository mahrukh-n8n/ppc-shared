import csv
import io
import math
from pathlib import Path
import unittest
from ppc_shared.brand_analytics import parse_report, query_reports, metrics
from ppc_shared.utils import safe_float

FIXTURES = Path(__file__).parent / "fixtures" / "brand-analytics"


def reports(family):
    result = []
    for p in sorted(FIXTURES.glob("*.csv")):
        parsed = parse_report(p.read_bytes())
        parsed["id"] = p.name
        if parsed["family"] == family:
            result.append(parsed)
    return result


class BrandAnalyticsTests(unittest.TestCase):
    def test_workbook_aggregates(self):
        expected = {
            "brand": [0.000489792620794474, 0.0011765259541625488, 0.0011607661056297156, 0.001932740626207963, 0.06443298969072164, 0.32, 0.2, 0.026823720101190145, 0.3243446750435315, 0.12174690573674055, 0.037609269589531494, -0.004344675043531476, 0.07825309426325947],
            "asin": [0.025530745082737706, 0.08765432098765433, 0.11443806398687449, 0.1158974358974359, 0.061653351858284126, 0.7859154929577464, 0.3183098591549296, 0.017957540393380985, 0.6019753086419753, 0.24074074074074073, 0.043695811464903145, 0.18394018431577108, 0.07756911841418887],
        }
        fields = ["impressions_share", "clicks_share", "cart_adds_share", "purchases_share", "ctr", "atc", "cvr", "market_ctr", "market_atc", "market_cvr", "ctr_performance", "atc_performance", "cvr_performance"]
        for family, values in expected.items():
            result = query_reports(reports(family), {"family": family})
            self.assertEqual(result["row_count"], 3)
            for field, value in zip(fields, values):
                self.assertAlmostEqual(result["summary"][field], value, places=12)
        catalog = query_reports(reports("catalog"), {"family": "catalog"})
        self.assertEqual(catalog["summary"]["impressions"], 20657)
        self.assertAlmostEqual(catalog["summary"]["sales"], 1455.64)

    def test_header_variants_and_collisions(self):
        raw = next(FIXTURES.glob("*ASIN_View*" )).read_text()
        variant = raw.replace("Search Query,", "\ufeff Search  query ,").replace("Impressions: ASIN Count", " Impressions : ASIN Count ")
        self.assertEqual(len(parse_report(variant.encode())["rows"]), 3)
        with self.assertRaisesRegex(ValueError, "Duplicate headers"):
            parse_report(raw.replace("Search Query Score", "Search query").encode())
        with self.assertRaisesRegex(ValueError, "Missing columns"):
            parse_report(raw.replace("Impressions: ASIN Count", "Impressions: Brand Count").encode())

    def test_null_prices_and_existing_number_contract(self):
        rows = reports("brand")[0]["rows"]
        self.assertIsNone(rows[1]["purchases_price"])
        self.assertEqual(safe_float("12,5"), 12.5)
        self.assertEqual(safe_float("1,234"), 1.234)
        self.assertIsNone(metrics([{"impressions": 0, "clicks": 0}])["ctr"])

    def test_filters_summaries_and_pagination(self):
        result = query_reports(reports("asin"), {"family": "asin", "filters": {"label": {"type": "equals", "filter": "kw1"}}, "page_size": 1})
        self.assertEqual(result["summary"]["purchases"], 103)
        result = query_reports(reports("asin"), {"family": "asin", "page_size": 1})
        self.assertEqual(len(result["rows"]), 1)
        self.assertEqual(result["summary"]["purchases"], 113)
        result = query_reports(reports("asin"), {"family": "asin", "filters": {"ctr": {"type": "greaterThan", "filter": 7}}})
        self.assertEqual(result["row_count"], 2)
        result = query_reports(reports("brand"), {"family": "brand", "keywords": []})
        self.assertEqual(result["rows"], [])
        self.assertIsNone(result["summary"])
        result = query_reports(reports("catalog"), {"family": "catalog", "asins": []})
        self.assertEqual(result["row_count"], 0)

    def test_period_comparison_and_view_specific_averages(self):
        data = reports("asin")
        result = query_reports(data, {"family": "asin", "view": "comparison"})
        self.assertEqual(result["delta"]["values"]["purchases"], -17)
        result = query_reports(data, {"family": "asin", "view": "details", "keywords": ["KW1"]})
        self.assertEqual(result["rows"][0]["avg_cart_adds"], 130.5)
        raw = next(FIXTURES.glob("*ASIN_View*" )).read_text()
        with self.assertRaisesRegex(ValueError, "Reporting Date conflicts"):
            parse_report(raw.replace("6/22/2024", "6/21/2024").encode())


if __name__ == "__main__":
    unittest.main()

class CatalogExtraFieldsTests(unittest.TestCase):
    def test_catalog_source_fields_are_available_with_explicit_aggregation(self):
        result = query_reports(reports("catalog"), {"family": "catalog", "view": "details"})
        fields = {c["field"] for c in result["columns"]}
        self.assertIn("impressions_price", fields)
        self.assertIn("purchases_rating", fields)
        self.assertIn("clicks_one_day", fields)
        self.assertEqual(result["summary"]["clicks_one_day"], 354)
        self.assertAlmostEqual(result["summary"]["impressions_price"], 6.49)
