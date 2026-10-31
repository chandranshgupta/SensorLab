"""Board driver unit tests.
Matrix frames aur level bar calculations check karta hai.
"""

import unittest
from board.python.main import FACE_GOOD, make_level_bar_frame


class TestBoardLogic(unittest.TestCase):
    def test_face_good_dimensions(self):
        # 8 rows aur 13 columns check karo
        self.assertEqual(len(FACE_GOOD), 8)
        for row in FACE_GOOD:
            self.assertEqual(len(row), 13)

    def test_level_bar_generation(self):
        # 0.0 level pe 0 columns filled honi chahiye
        bar_zero = make_level_bar_frame(0.0)
        self.assertEqual(len(bar_zero), 8)
        self.assertTrue(all(val == 0 for row in bar_zero for val in row))

        # 1.0 level pe saari 13 columns filled honi chahiye
        bar_full = make_level_bar_frame(1.0)
        self.assertTrue(all(val > 0 for row in bar_full for val in row))

        # 0.5 level pe roughly half columns filled honi chahiye
        bar_half = make_level_bar_frame(0.5)
        self.assertEqual(sum(1 for val in bar_half[0] if val > 0), 6)


if __name__ == "__main__":
    unittest.main()
