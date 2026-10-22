import unittest

from well_actually_processing.service import contains_well_actually_phrase


class TranscriptPhraseDetectionTests(unittest.TestCase):
    def test_matches_case_insensitively_when_punctuation_separates_words(self):
        self.assertTrue(contains_well_actually_phrase("Well, ACTUALLY!"))
        self.assertTrue(contains_well_actually_phrase("I said well—actually, that's it."))

    def test_matches_phrase_inside_larger_transcript(self):
        self.assertTrue(
            contains_well_actually_phrase("The phrase was: 'well actually', I think.")
        )

    def test_requires_both_complete_adjacent_words(self):
        self.assertFalse(contains_well_actually_phrase("farewell, actually"))
        self.assertFalse(contains_well_actually_phrase("well actuallyness"))
        self.assertFalse(contains_well_actually_phrase("well, truly"))


if __name__ == "__main__":
    unittest.main()
