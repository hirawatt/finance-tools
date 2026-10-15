"""Tests for utils.surveillance (pure parsers and matching, no network)."""

import unittest

import pandas as pd

from utils.surveillance import (
    SURVEILLANCE_COLUMNS,
    check_symbols,
    parse_asm,
    parse_gsm,
)

ASM_PAYLOAD = {
    "longterm": {
        "data": [
            {
                "symbol": "a2zinfra",
                "companyName": "A2Z Infra Engineering Limited",
                "asmSurvIndicator": "Stage I",
                "survCode": "LTASM - I (13)",
                "asmTime": "15-Oct-2026",
            }
        ]
    },
    "shortterm": {
        "data": [
            {
                "symbol": "abansent",
                "companyName": "Abans Enterprises Limited",
                "asmSurvIndicator": "Stage II",
                "survCode": "STASM - II (12)",
                "asmTime": "15-Oct-2026",
            }
        ]
    },
}

GSM_PAYLOAD = [
    {
        "symbol": "agstra",
        "companyName": "AGS Transact Technologies Limited",
        "gsmStage": "VI",
        "survCode": "GSM - VI (6)",
        "gsmTime": "15-Oct-2026",
    },
    {
        "symbol": "nulstage",
        "companyName": "No Stage Limited",
        "gsmStage": "",
        "survDesc": "GSM - 0",
        "gsmTime": "15-Oct-2026",
    },
]


class TestParseAsm(unittest.TestCase):
    def test_parses_both_terms(self):
        frame = parse_asm(ASM_PAYLOAD)
        self.assertEqual(list(frame.columns), SURVEILLANCE_COLUMNS)
        self.assertEqual(len(frame), 2)
        self.assertEqual(
            set(frame["List"]), {"ASM · Long Term", "ASM · Short Term"}
        )

    def test_normalises_fields(self):
        frame = parse_asm(ASM_PAYLOAD).set_index("Symbol")
        self.assertIn("A2ZINFRA", frame.index)  # uppercased
        self.assertEqual(frame.loc["A2ZINFRA", "Stage"], "Stage I")
        self.assertEqual(frame.loc["A2ZINFRA", "Code"], "LTASM - I (13)")
        self.assertEqual(frame.loc["A2ZINFRA", "Updated"], "15-Oct-2026")

    def test_accepts_plain_list(self):
        frame = parse_asm([{"symbol": "foo", "survDesc": "whatever"}])
        self.assertEqual(frame.loc[0, "Symbol"], "FOO")

    def test_empty_payload(self):
        for payload in (None, {}, {"longterm": {"data": []}}):
            frame = parse_asm(payload)
            self.assertTrue(frame.empty)
            self.assertEqual(list(frame.columns), SURVEILLANCE_COLUMNS)


class TestParseGsm(unittest.TestCase):
    def test_parses_records(self):
        frame = parse_gsm(GSM_PAYLOAD)
        self.assertEqual(len(frame), 2)
        self.assertTrue((frame["List"] == "GSM").all())
        self.assertEqual(frame.loc[0, "Stage"], "Stage VI")

    def test_falls_back_to_surv_desc_without_stage(self):
        frame = parse_gsm(GSM_PAYLOAD).set_index("Symbol")
        self.assertEqual(frame.loc["NULSTAGE", "Stage"], "GSM - 0")

    def test_empty_payload(self):
        for payload in (None, []):
            frame = parse_gsm(payload)
            self.assertTrue(frame.empty)
            self.assertEqual(list(frame.columns), SURVEILLANCE_COLUMNS)


class TestCheckSymbols(unittest.TestCase):
    def setUp(self):
        self.surveillance = pd.concat(
            [parse_asm(ASM_PAYLOAD), parse_gsm(GSM_PAYLOAD)], ignore_index=True
        )

    def test_matches_case_insensitively(self):
        matched = check_symbols(["a2zinfra", "AGSTRA"], self.surveillance)
        self.assertEqual(set(matched["Symbol"]), {"A2ZINFRA", "AGSTRA"})

    def test_ignores_absent_and_blank_symbols(self):
        matched = check_symbols(["", "  ", "NOTLISTED"], self.surveillance)
        self.assertTrue(matched.empty)

    def test_sorted_by_symbol(self):
        matched = check_symbols(["agstra", "a2zinfra"], self.surveillance)
        self.assertEqual(matched["Symbol"].tolist(), sorted(matched["Symbol"].tolist()))

    def test_no_surveillance_data(self):
        for empty in (None, pd.DataFrame()):
            matched = check_symbols(["A2ZINFRA"], empty)
            self.assertTrue(matched.empty)
            self.assertEqual(list(matched.columns), SURVEILLANCE_COLUMNS)


if __name__ == "__main__":
    unittest.main()
