import importlib.util
import unittest
from pathlib import Path


MODULE_PATH = Path(__file__).parents[1] / "built_in_references.py"
SPEC = importlib.util.spec_from_file_location("h3_built_in_references", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class BuiltInReferenceTests(unittest.TestCase):
    def test_catalog_parses_sections_and_multiple_clips(self):
        records = MODULE.list_built_in_references()
        by_name = {record["name"]: record for record in records}

        self.assertGreater(len(records), 500)
        self.assertEqual(by_name["Abby Sciuto"]["folder"], "good")
        self.assertEqual(by_name["Abby Sciuto"]["actor"], "Pauley Perrette")
        self.assertEqual(by_name["Abby Sciuto"]["franchise"], "NCIS")
        self.assertEqual(len(by_name["Ace Ventura"]["clips"]), 2)
        self.assertEqual(by_name["Agent Olivia Dunham"]["folder"], "onthefence")

    def test_duplicate_names_receive_portrayal_specific_tags(self):
        records = MODULE.list_built_in_references()
        batmen = [record for record in records if record["name"] == "Bruce Wayne / Batman"]

        self.assertGreaterEqual(len(batmen), 4)
        self.assertEqual(len({record["tag"] for record in batmen}), len(batmen))
        self.assertIn(
            "Bruce Wayne / Batman | Christian Bale | The Dark Knight",
            {record["tag"] for record in batmen},
        )

    def test_portrayal_specific_tag_resolves_and_short_duplicate_is_rejected(self):
        prompt, mapping = MODULE.resolve_built_in_prompt(
            "^Bruce Wayne / Batman | Christian Bale | The Dark Knight^ enters."
        )

        self.assertEqual(
            prompt,
            "Bruce Wayne / Batman played by Christian Bale featured on The Dark Knight enters.",
        )
        self.assertIn("Christian Bale | The Dark Knight^ ->", mapping)
        with self.assertRaisesRegex(ValueError, "multiple portrayals"):
            MODULE.resolve_built_in_prompt("^Bruce Wayne / Batman^ enters.")

    def test_prompt_expansion_and_mapping(self):
        prompt, mapping = MODULE.resolve_built_in_prompt(
            "[Shot 1] ^Abby Sciuto^ meets ^Achilles^."
        )

        self.assertEqual(
            prompt,
            "[Shot 1] Abby Sciuto played by Pauley Perrette featured on NCIS "
            "meets Achilles played by Brad Pitt featured on Troy.",
        )
        self.assertIn("^Abby Sciuto^ -> Abby Sciuto played by Pauley Perrette featured on NCIS", mapping)
        self.assertIn("^Achilles^ -> Achilles played by Brad Pitt featured on Troy", mapping)

    def test_repeated_tag_maps_once(self):
        prompt, mapping = MODULE.resolve_built_in_prompt(
            "^Ace Ventura^ watches ^Ace Ventura^."
        )
        self.assertEqual(prompt.count("played by Jim Carrey"), 2)
        self.assertEqual(len(mapping.splitlines()), 1)

    def test_voice_tag_expands_without_franchise(self):
        prompt, mapping = MODULE.resolve_built_in_prompt(
            "<d>[English ~George Costanza~] Damn, Jerry.</d>"
        )

        self.assertEqual(
            prompt,
            "<d>[English in George Costanza's voice as played by Jason Alexander] "
            "Damn, Jerry.</d>",
        )
        self.assertEqual(
            mapping,
            "~George Costanza~ -> in George Costanza's voice as played by Jason Alexander",
        )
        self.assertNotIn("Seinfeld", prompt + mapping)

    def test_character_and_voice_variants_are_both_mapped(self):
        prompt, mapping = MODULE.resolve_built_in_prompt(
            "^George Costanza^ speaks. ~George Costanza~ replies."
        )

        self.assertIn("featured on Seinfeld speaks", prompt)
        self.assertIn("in George Costanza's voice as played by Jason Alexander replies", prompt)
        self.assertEqual(len(mapping.splitlines()), 2)

    def test_no_tags_passes_through(self):
        source = "[Shot 1] An unknown person walks into frame."
        self.assertEqual(MODULE.resolve_built_in_prompt(source), (source, ""))

    def test_unknown_tag_is_clear(self):
        with self.assertRaisesRegex(ValueError, "no character 'Missing Person'"):
            MODULE.resolve_built_in_prompt("^Missing Person^ enters.")


if __name__ == "__main__":
    unittest.main()
