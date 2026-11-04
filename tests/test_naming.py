import unittest

from ns2_nup_tool.naming import nup_filename


class NamingTests(unittest.TestCase):
    def test_title_and_id_are_safe_and_not_duplicated(self):
        cases = [
            ("Pokemon Legends Z-A Switch 2 Edition", "0100f43008c44000",
             "Pokemon Legends Z-A Switch 2 Edition [0100F43008C44000].nup"),
            ("Game [0100000000001000]", "0100000000001000", "Game [0100000000001000].nup"),
            ('Game: One/Two? ', "", "Game_ One_Two_.nup"),
            ("CON", "", "_CON.nup"),
            ("...", "0000000000000000", "Game.nup"),
            ("Pokémon™ Pokopia", "0400A3A01EE4C000", "Pokémon™ Pokopia [0400A3A01EE4C000].nup"),
        ]
        for title, title_id, expected in cases:
            with self.subTest(title=title):
                self.assertEqual(nup_filename(title, title_id), expected)
