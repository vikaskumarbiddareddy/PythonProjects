import unittest

from goggin.main import greet


class TestGreet(unittest.TestCase):
    def test_default(self):
        self.assertEqual(greet(), "Hello from Goggin!")

    def test_custom_name(self):
        self.assertEqual(greet("World"), "Hello from World!")


if __name__ == "__main__":
    unittest.main()
