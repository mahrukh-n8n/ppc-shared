from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

import pandas as pd

from ppc_shared import build_campaigns


class RecommendedBudgetTests(unittest.TestCase):
    def build(self, days=7, spend=700, orders=50, budget=1000):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "bulk.xlsx"
            with pd.ExcelWriter(path, engine="openpyxl") as writer:
                for sheet, name, share in (
                    ("Sponsored Products Campaigns", "SP", 0.4),
                    ("Sponsored Brands Campaigns", "SB", 0.6),
                    ("Sponsored Display Campaigns", "SD", 0),
                ):
                    pd.DataFrame([{
                        "Entity": "Campaign", "Campaign Name": name,
                        "State": "enabled", "Daily Budget": budget,
                        "Spend": spend * share, "Orders": orders * share,
                    }]).to_excel(writer, sheet_name=sheet, index=False)
            campaigns, summary, *_ = build_campaigns(path, days=days)
            return {c["campaign_name"]: c for c in campaigns}, summary

    def test_allocates_average_daily_spend_across_ad_products(self):
        campaigns, summary = self.build()
        self.assertEqual(campaigns["SP"]["recommended_budget"], 40)
        self.assertEqual(campaigns["SB"]["recommended_budget"], 60)
        self.assertEqual(campaigns["SD"]["recommended_budget"], 0)
        self.assertEqual(summary["budget"], 3000)
        self.assertEqual(summary["daily_spend"], 100)

    def test_does_not_depend_on_configured_budget(self):
        campaigns, _ = self.build(budget=0)
        self.assertEqual(campaigns["SP"]["recommended_budget"], 40)

    def test_uses_period_length(self):
        campaigns, _ = self.build(days=14)
        self.assertEqual(campaigns["SP"]["recommended_budget"], 20)

    def test_zero_spend_or_orders(self):
        for inputs in ({"spend": 0}, {"orders": 0}):
            with self.subTest(inputs=inputs):
                campaigns, _ = self.build(**inputs)
                self.assertTrue(all(c["recommended_budget"] == 0 for c in campaigns.values()))

    def test_unknown_daily_spend_stays_missing(self):
        for days in (None, 0, -1):
            with self.subTest(days=days):
                campaigns, _ = self.build(days=days)
                self.assertTrue(all(c["recommended_budget"] is None for c in campaigns.values()))
