"""Tests for ingest.py, built only from rules.md.

Every test names the rule it comes from. rules.md is the only source of truth.

How the tests stay away from your real data
-------------------------------------------
- Each test gets its own temporary folder. The database there is called
  test.db and the log is called test-ingestion-log.json.
- ingest.py keeps the paths of its database and log in two names, DB_FILE and
  LOG_FILE. The tests point those two names at the temporary folder before
  running ingest.py, so ingest.py itself does not have to change.
- When a test is done, passed or failed, its temporary folder and everything
  in it is deleted.
- The books.db and ingestion-log.json in this folder are never opened for
  writing. A safety check at the end of the run fails loudly if either one
  changed.

Run them with:   python3 -m pytest -v
"""
import csv
import hashlib
import importlib.util
import json
import os
import shutil
import sqlite3
import sys
import tempfile

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
INGEST = os.path.join(HERE, "ingest.py")
BOOKS_CSV = os.path.join(HERE, "books.csv")
BATCH2_CSV = os.path.join(HERE, "books-batch2.csv")

# rules.md answer 3: all 23 CSV columns (plus changes_repairs)
COLUMNS = [
    "book_id", "goodreads_book_id", "best_book_id", "work_id", "books_count",
    "isbn", "isbn13", "authors", "original_publication_year", "original_title",
    "title", "language_code", "average_rating", "ratings_count",
    "work_ratings_count", "work_text_reviews_count", "ratings_1", "ratings_2",
    "ratings_3", "ratings_4", "ratings_5", "image_url", "small_image_url",
]

# rules.md section 11 and answer 28: what to do
FIND_ISBN = "find the correct ISBN on the book or from the publisher"
CHECK_DUPLICATE = "check which book the ISBN belongs to"


# ---------------------------------------------------------------- safety check

def _fingerprint(path):
    if not os.path.exists(path):
        return None
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


@pytest.fixture(autouse=True, scope="session")
def real_files_are_never_touched():
    """The tests must never touch books.db or ingestion-log.json in this folder."""
    real = [os.path.join(HERE, "books.db"), os.path.join(HERE, "ingestion-log.json")]
    before = {path: _fingerprint(path) for path in real}
    yield
    after = {path: _fingerprint(path) for path in real}
    assert after == before, "A test changed books.db or ingestion-log.json in your folder!"


# ---------------------------------------------------------------- the test folder

class Workspace:
    """A temporary folder with test.db and a test log, deleted after the test."""

    def __init__(self, folder):
        self.folder = folder
        self.db = os.path.join(folder, "test.db")
        self.log = os.path.join(folder, "test-ingestion-log.json")

    def write_csv(self, name, rows):
        """Write a delivery file. Columns a row doesn't mention are left empty."""
        path = os.path.join(self.folder, name)
        with open(path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=COLUMNS)
            writer.writeheader()
            for row in rows:
                writer.writerow({c: row.get(c, "") for c in COLUMNS})
        return path

    def run(self, csv_path):
        """Run ingest.py on csv_path, the way `python3 ingest.py <file>` would."""
        sys.dont_write_bytecode = True          # leave no __pycache__ behind
        spec = importlib.util.spec_from_file_location("ingest_under_test", INGEST)
        ingest = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(ingest)
        ingest.DB_FILE = self.db                 # test.db, never books.db
        ingest.LOG_FILE = self.log               # the test's own log
        saved_argv = sys.argv
        sys.argv = ["ingest.py", csv_path]
        try:
            ingest.main()
        finally:
            sys.argv = saved_argv

    def remove_database_and_log(self):
        for path in (self.db, self.log):
            if os.path.exists(path):
                os.remove(path)

    # --- reading the results

    def books(self):
        con = sqlite3.connect(self.db)
        con.row_factory = sqlite3.Row
        try:
            return [dict(r) for r in con.execute("SELECT * FROM books ORDER BY rowid")]
        finally:
            con.close()

    def books_with_id(self, book_id):
        return [b for b in self.books() if b["book_id"] == book_id]

    def log_entries(self):
        with open(self.log, encoding="utf-8") as f:
            return json.load(f)


@pytest.fixture
def work():
    folder = tempfile.mkdtemp(prefix="ingest-test-")
    try:
        yield Workspace(folder)
    finally:
        shutil.rmtree(folder, ignore_errors=True)   # removed whether the test passed or failed


def notes_by_isbn(changes):
    """Split a changes_repairs note into its parts for each ISBN.

    rules.md section 2: each note starts with the ISBN it is about, "isbn:" or
    "isbn13:". Example 7 shows that more problems for the same ISBN follow
    after "; " without repeating the prefix.
    """
    groups = {}
    current = None
    for part in (changes.split("; ") if changes else []):
        if part.startswith("isbn13: "):
            current, part = "isbn13", part[len("isbn13: "):]
        elif part.startswith("isbn: "):
            current, part = "isbn", part[len("isbn: "):]
        elif part.startswith("Updated:") or part == "Warning: missing book_id":
            current = None                       # answers 7 and 15: no isbn prefix
        groups.setdefault(current, []).append(part)
    return groups


def count_rows(csv_path):
    with open(csv_path, newline="", encoding="utf-8-sig") as f:
        return sum(1 for _ in csv.DictReader(f))


# ---------------------------------------------------------------- section 12: the examples

# Examples that name one ISBN value. The other ISBN column is left empty, so the
# test only looks at the note for the column the example is about.
ONE_COLUMN_EXAMPLES = [
    # (example, book_id, title, column, value as it arrives, stored, notes, listed first?)
    (1, "1", "The Hunger Games", "isbn", "439023483", "0439023483",
     ["Repaired"], False),
    (2, "10007", "Small Hours", "isbn", "1854433017", "1854433017",
     ["Wrong ISBN: check digit fails"], True),
    (3, "4", "To Kill a Mockingbird", "isbn", "61120081", "0061120081",
     ["Repaired"], None),
    (4, "10002", "Salt and Ember", "isbn", "0-450-19827-8", "0450198278",
     ["Repaired"], None),
    (5, "10003", "A Field Guide to Quiet Places", "isbn", " 162 001 4750 ", "1620014750",
     ["Repaired"], None),
    (6, "10004", "Winter Orchard", "isbn", "031200009x", "031200009X",
     ["Repaired"], None),
    (7, "1543", "The Racketeer", "isbn", "385535144", "385535144",
     ["Wrong ISBN: check digit fails", "Wrong ISBN: wrong number of digits (9)"], True),
    (8, "10008", "The Glass Aviary", "isbn", "04390A3483", "04390A3483",
     ["Wrong ISBN: contains a letter or symbol"], True),
    (9, "10009", "Borrowed Light", "isbn", "15287463097", "15287463097",
     ["Wrong ISBN: wrong number of digits (11)"], True),
    # 11 and 12: value and note only. "Listed first" is not tested, because
    # answer 19 and these two examples disagree about it (decided 2026-11-08).
    (11, "1", "The Hunger Games", "isbn13", "9.78043902348e+12", "9.78043902348e+12",
     ["Wrong ISBN: contains a letter or symbol", "Wrong ISBN: wrong number of digits (14)"],
     None),
    (12, "1165", "Wait for You", "isbn13", "2.94001623192e+12", "2.94001623192e+12",
     ["Wrong ISBN: contains a letter or symbol", "Wrong ISBN: wrong number of digits (14)",
      "Wrong ISBN: does not start with 978 or 979"],
     None),
]


@pytest.mark.parametrize(
    "example, book_id, title, column, arrives, stored, notes, listed",
    ONE_COLUMN_EXAMPLES,
    ids=[f"example_{e[0]}" for e in ONE_COLUMN_EXAMPLES],
)
def test_example_one_isbn(work, example, book_id, title, column, arrives, stored, notes, listed):
    """rules.md section 12, examples 1-9, 11 and 12."""
    path = work.write_csv("delivery.csv", [{"book_id": book_id, "title": title, column: arrives}])
    work.run(path)

    # rule 1: nothing is rejected, the row loads
    [book] = work.books_with_id(book_id)
    run = work.log_entries()[-1]
    assert run["counts"]["loaded"] == 1
    assert run["counts"]["rejected"] == 0

    # the stored value and the note, exactly as the table says
    assert book[column] == stored
    assert notes_by_isbn(book["changes_repairs"]).get(column) == notes

    # the morning report (rule 11, answer 26: the first book is on line 2)
    listed_rows = [r for r in run["needs_attention"] if r["book_id"] == book_id]
    if listed is True:
        assert len(listed_rows) == 1
        assert listed_rows[0]["line"] == 2
        assert FIND_ISBN in listed_rows[0]["what_to_do"]
    elif listed is False:
        assert listed_rows == []

    # example 1: "counted in the repairs total" (answer 25: per value)
    if example == 1:
        assert run["counts"]["repairs"] == 1


# Examples whose whole row is given, so the whole note can be checked.
WHOLE_ROW_EXAMPLES = [
    # (example, book_id, title, isbn arrives, isbn13 arrives, stored isbn, stored isbn13, note)
    (10, "10014", "An Atlas of Small Kindnesses", "9781982147600", "",
     "", "9781982147600", "isbn13: Repaired; isbn: Missing ISBN"),
    (14, "106", "Bossypants", "", "",
     "", "", "isbn: Missing ISBN; isbn13: Missing ISBN"),
    (15, "10006", "Notes from the Night Ferry", "", "9798351220413",
     "", "9798351220413", "isbn: Missing ISBN"),
]


@pytest.mark.parametrize(
    "example, book_id, title, isbn, isbn13, stored_isbn, stored_isbn13, note",
    WHOLE_ROW_EXAMPLES,
    ids=[f"example_{e[0]}" for e in WHOLE_ROW_EXAMPLES],
)
def test_example_whole_row(work, example, book_id, title, isbn, isbn13,
                           stored_isbn, stored_isbn13, note):
    """rules.md section 12, examples 10, 14 and 15."""
    path = work.write_csv("delivery.csv",
                          [{"book_id": book_id, "title": title, "isbn": isbn, "isbn13": isbn13}])
    work.run(path)

    [book] = work.books_with_id(book_id)
    run = work.log_entries()[-1]
    assert run["counts"]["loaded"] == 1
    assert run["counts"]["rejected"] == 0
    assert book["isbn"] == stored_isbn
    assert book["isbn13"] == stored_isbn13
    assert book["changes_repairs"] == note

    # all three are "listed first ... with find the correct ISBN"
    [listed] = [r for r in run["needs_attention"] if r["book_id"] == book_id]
    assert listed["line"] == 2
    assert FIND_ISBN in listed["what_to_do"]


def test_example_13_duplicate_isbn_on_another_book(work):
    """rules.md section 12 example 13, and rule 10.

    Book 9 (Angels & Demons) is already in the database with 1416524797.
    Paper Moons arrives with the same ISBN-10.
    """
    first = work.write_csv("first.csv", [{
        "book_id": "9", "title": "Angels & Demons", "isbn": "1416524797",
        "isbn13": "9.78141652479e+12"}])
    work.run(first)
    second = work.write_csv("second.csv", [{
        "book_id": "10013", "title": "Paper Moons", "isbn": "1416524797"}])
    work.run(second)

    # rule 10: both load
    [angels] = work.books_with_id("9")
    [paper_moons] = work.books_with_id("10013")
    assert paper_moons["isbn"] == "1416524797"
    assert notes_by_isbn(paper_moons["changes_repairs"]).get("isbn") == [
        "Warning duplicate ISBN: also used by book_id 9"]

    # rule 10: only the newcomer gets the warning
    assert "duplicate" not in (angels["changes_repairs"] or "")

    # listed first, with "check which book the ISBN belongs to"
    run = work.log_entries()[-1]
    [listed] = [r for r in run["needs_attention"] if r["book_id"] == "10013"]
    assert CHECK_DUPLICATE in listed["what_to_do"]


# ---------------------------------------------------------------- running the same file twice

def test_same_file_twice_creates_no_duplicates(work):
    """Rules 8 and 9, section 15: running the same file again never adds a book twice."""
    work.run(BOOKS_CSV)
    after_first = len(work.books())
    work.run(BOOKS_CSV)
    books = work.books()

    assert len(books) == after_first
    book_ids = [b["book_id"] for b in books if b["book_id"] != ""]
    assert len(book_ids) == len(set(book_ids)), "a book_id appears more than once"

    # rule 9: every row of the second run is identical, so it is skipped
    second = work.log_entries()[-1]["counts"]
    assert second["loaded"] == 0
    assert second["skipped"] == second["read"]


def test_every_run_adds_a_log_entry_and_keeps_earlier_ones(work):
    """Section 15: every run adds one entry to the end; earlier entries are never changed."""
    earlier = []
    for run_number in range(1, 4):
        work.run(BATCH2_CSV)
        entries = work.log_entries()
        assert len(entries) == run_number
        assert entries[:-1] == earlier, "an earlier log entry was changed or removed"
        assert entries[-1]["file"] == BATCH2_CSV
        earlier = entries


def test_counts_add_up_to_rows_read(work):
    """Section 15 (and rules 1, 9, answer 24): loaded + updated + skipped + rejected = read."""
    deliveries = [BOOKS_CSV, BOOKS_CSV, BATCH2_CSV]
    for path in deliveries:
        work.run(path)

    entries = work.log_entries()
    assert len(entries) == len(deliveries)
    for path, entry in zip(deliveries, entries):
        counts = entry["counts"]
        assert counts["read"] == count_rows(path)
        assert counts["loaded"] + counts["updated"] + counts["skipped"] + counts["rejected"] \
            == counts["read"], f"counts don't add up for {os.path.basename(path)}: {counts}"
        assert counts["rejected"] == 0              # rule 1


@pytest.mark.parametrize("delivery", [BOOKS_CSV, BATCH2_CSV], ids=["books.csv", "books-batch2.csv"])
def test_same_file_on_empty_database_gives_same_database(work, delivery):
    """Rule 7 and section 15: the same file on an empty database always gives the same database."""
    work.run(delivery)
    first = work.books()
    work.remove_database_and_log()            # back to an empty database
    work.run(delivery)
    second = work.books()

    assert len(first) > 0
    assert second == first


# ---------------------------------------------------------------- section 15: still to fix

def test_still_to_fix_lists_every_book_still_needing_a_person(work):
    """Section 15: every report has a "Still to fix" list of every book in the
    database whose isbn has a problem or which has a Warning, whichever run
    found it. Checked on the second run of books.csv, where nothing new is found.
    """
    work.run(BOOKS_CSV)
    work.run(BOOKS_CSV)

    expected = {}
    for book in work.books():
        notes = notes_by_isbn(book["changes_repairs"])
        isbn_problem = any(n.startswith("Wrong ISBN") or n == "Missing ISBN"
                           for n in notes.get("isbn", []))
        warning = any(n.startswith("Warning") for part in notes.values() for n in part)
        if isbn_problem or warning:
            expected[book["book_id"]] = book["changes_repairs"]

    still_to_fix = work.log_entries()[-1]["still_to_fix"]
    listed = {r["book_id"]: r["note"] for r in still_to_fix}

    assert len(expected) > 0
    assert listed == expected
