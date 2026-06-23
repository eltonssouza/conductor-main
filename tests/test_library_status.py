"""Test `cdt library status` aggregation (collection mocked — no Chroma needed)."""
import io
import unittest
from contextlib import redirect_stdout
from unittest import mock

from conductor import library


class TestLibraryStatus(unittest.TestCase):
    def _run(self, count, metadatas):
        coll = mock.Mock()
        coll.count.return_value = count
        coll.get.return_value = {"metadatas": metadatas}
        buf = io.StringIO()
        with mock.patch.object(library, "get_collection", return_value=coll), \
             redirect_stdout(buf):
            rc = library.cmd_status([])
        return rc, buf.getvalue()

    def test_empty_index(self):
        rc, out = self._run(0, [])
        self.assertEqual(rc, 0)
        self.assertIn("empty", out.lower())

    def test_aggregates_books_and_categories(self):
        rc, out = self._run(3, [
            {"source": "Clean Code", "category": "03_design_and_architecture"},
            {"source": "Clean Code", "category": "03_design_and_architecture"},
            {"source": "Python Crash Course", "category": "01_programming_languages"},
        ])
        self.assertEqual(rc, 0)
        self.assertIn("3 chunks", out)
        self.assertIn("2 books", out)
        self.assertIn("2 categories", out)
        self.assertIn("Clean Code", out)
        self.assertIn("(2 chunks)", out)        # Clean Code appears twice


if __name__ == "__main__":
    unittest.main()
