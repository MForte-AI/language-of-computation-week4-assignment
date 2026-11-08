#!/usr/bin/env python3
"""Load a books CSV file into books.db, following rules.md.

Usage:
    python3 ingest.py books.csv

No AI and no internet: the same file always gives the same result.
books.db and ingestion-log.json are kept in the same folder as this script.
"""
import csv
import json
import os
import re
import sqlite3
import sys
from datetime import datetime

COLUMNS = [
    "book_id", "goodreads_book_id", "best_book_id", "work_id", "books_count",
    "isbn", "isbn13", "authors", "original_publication_year", "original_title",
    "title", "language_code", "average_rating", "ratings_count",
    "work_ratings_count", "work_text_reviews_count", "ratings_1", "ratings_2",
    "ratings_3", "ratings_4", "ratings_5", "image_url", "small_image_url",
]

HERE = os.path.dirname(os.path.abspath(__file__))
DB_FILE = os.path.join(HERE, "books.db")
LOG_FILE = os.path.join(HERE, "ingestion-log.json")

# Labels (rules.md section 6, and answer 17 / answer 7)
WRONG_CHAR = "Wrong ISBN: contains a letter or symbol"
WRONG_COUNT = "Wrong ISBN: wrong number of digits ({})"
WRONG_PREFIX = "Wrong ISBN: does not start with 978 or 979"
WRONG_CHECK = "Wrong ISBN: check digit fails"
MISSING = "Missing ISBN"
REPAIRED = "Repaired"
WARN_MISMATCH = "Warning ISBN-10 and ISBN-13 do not match"
WARN_DUPLICATE = "Warning duplicate ISBN: also used by book_id {}"
WARN_KEPT_EMPTY = "Warning: new delivery had no ISBN, kept previous"
WARN_KEPT_WRONG = "Warning: new delivery had a wrong ISBN, kept previous"
WARN_CHECK_NUMBERS = "Warning: check ISBN numbers for correct one"
WARN_NO_BOOK_ID = "Warning: missing book_id"

# "What to do" texts (rules.md section 11 and answer 28)
DO_FIND_ISBN = "find the correct ISBN on the book or from the publisher"
DO_DUPLICATE = "check which book the ISBN belongs to"
DO_WHICH_ISBN = "check which ISBN is correct on the book or from the publisher"
DO_PREVIOUS = "check whether the previous ISBN is still correct"
DO_BOOK_ID = "find the book's book_id"

REASON_EXISTS = "already exists"
REASON_TWICE = "appeared twice in this file"


# ---------------------------------------------------------------- checks

def isbn10_valid(s):
    """Rules section 4: 9 digits then a digit or X; weights 10..1, total divisible by 11."""
    if not re.fullmatch(r"\d{9}[\dX]", s):
        return False
    total = sum((10 - i) * (10 if c == "X" else int(c)) for i, c in enumerate(s))
    return total % 11 == 0


def checksum13_passes(s):
    """Weights 1,3,1,3..., total divisible by 10 (s must be 13 digits)."""
    total = sum(int(c) * (1 if i % 2 == 0 else 3) for i, c in enumerate(s))
    return total % 10 == 0


def isbn13_valid(s):
    """Rules section 5: 13 digits, starts with 978 or 979, check digit passes."""
    return (bool(re.fullmatch(r"\d{13}", s))
            and s.startswith(("978", "979"))
            and checksum13_passes(s))


def isbn10_to_13(s10):
    """The ISBN-13 that belongs to a valid ISBN-10 (used for the match check)."""
    core = "978" + s10[:9]
    total = sum(int(c) * (1 if i % 2 == 0 else 3) for i, c in enumerate(core))
    return core + str((10 - total % 10) % 10)


def is_good(value, column):
    """Answer 18: a good ISBN is a valid one (as it arrived, or repaired)."""
    return isbn10_valid(value) if column == "isbn" else isbn13_valid(value)


def evaluate(raw, column):
    """Answer 8, steps a-d, for one ISBN value.

    Returns (kind, value, labels):
      kind "missing"      - nothing left after cleaning
      kind "valid"        - value is the valid ISBN; labels is [Repaired] if it changed
      kind "wrong_column" - value is a valid ISBN of the other kind
      kind "wrong"        - labels are the Wrong ISBN labels
    """
    # a. remove hyphens and spaces, lowercase x becomes capital X
    cleaned = raw.replace("-", "").replace(" ", "").replace("x", "X")
    if cleaned == "":
        return "missing", "", [MISSING]

    if column == "isbn":
        # b. isbn column only: all digits (plus a final X), shorter than 10 -> add zeros
        candidate = cleaned
        if re.fullmatch(r"\d*X?", cleaned) and len(cleaned) < 10:
            candidate = cleaned.zfill(10)
        # c. valid -> store it
        if isbn10_valid(candidate):
            return "valid", candidate, ([REPAIRED] if candidate != raw else [])
        if isbn13_valid(cleaned):
            return "wrong_column", cleaned, []
        expected = 10
    else:
        candidate = cleaned          # answer 9: no zeros added in isbn13
        if isbn13_valid(candidate):
            return "valid", candidate, ([REPAIRED] if candidate != raw else [])
        if isbn10_valid(cleaned):
            return "wrong_column", cleaned, []
        expected = 13

    # d. label the problems found in the cleaned value
    labels = []
    # check digit: only when the value has the right shape after step b
    if column == "isbn" and re.fullmatch(r"\d{9}[\dX]", candidate):
        labels.append(WRONG_CHECK)
    if column == "isbn13" and re.fullmatch(r"\d{13}", candidate) and not checksum13_passes(candidate):
        labels.append(WRONG_CHECK)
    # letter or symbol: X is allowed only as the last character of an ISBN-10
    body = cleaned[:-1] if (column == "isbn" and cleaned.endswith("X")) else cleaned
    if re.search(r"\D", body):
        labels.append(WRONG_CHAR)
    # wrong number of digits: only when the number of characters is also wrong
    digits = re.sub(r"\D", "", body) + ("X" if body != cleaned else "")
    if len(cleaned) != expected and len(digits) != expected:
        labels.append(WRONG_COUNT.format(len(digits)))
    # 978 / 979: ISBN-13, judged on its digits
    if column == "isbn13" and not re.sub(r"\D", "", cleaned).startswith(("978", "979")):
        labels.append(WRONG_PREFIX)
    return "wrong", raw, labels


# ---------------------------------------------------------------- notes

class Notes:
    """Notes grouped by the ISBN they are about, in the order they appear.

    Written as  "isbn: A; B; isbn13: C"  (rules section 2, examples 7 and 10).
    Notes that are not about an ISBN (missing book_id, Updated) have no prefix.
    """

    def __init__(self, order=("isbn", "isbn13")):
        self.groups = {column: [] for column in order}   # column -> list of labels

    def add(self, column, label):
        self.groups.setdefault(column, []).append(label)

    def replace(self, column, labels):
        self.groups[column] = list(labels)

    def labels(self, column):
        return self.groups.get(column, [])

    def all_labels(self):
        return [lab for labs in self.groups.values() for lab in labs]

    def text(self, first=(), last=()):
        parts = list(first)
        for column, labs in self.groups.items():
            if labs:
                parts.append(f"{column}: " + "; ".join(labs))
        parts.extend(last)
        return "; ".join(parts)


def check_isbns(raw10, raw13):
    """Rules section 3 for one row. Returns (stored isbn, stored isbn13, Notes)."""
    kind10, val10, labels10 = evaluate(raw10, "isbn")
    kind13, val13, labels13 = evaluate(raw13, "isbn13")
    notes = Notes()

    if kind10 == "wrong_column" or kind13 == "wrong_column":
        if kind10 == "wrong_column" and kind13 == "missing":
            # ISBN-13 in the ISBN-10 column: move it (example 10 puts isbn13 first)
            notes = Notes(order=("isbn13", "isbn"))
            notes.add("isbn13", REPAIRED)
            notes.add("isbn", MISSING)
            return "", val10, notes
        if kind13 == "wrong_column" and kind10 == "missing":
            # ISBN-10 in the ISBN-13 column: move it
            notes.add("isbn", REPAIRED)
            notes.add("isbn13", MISSING)
            return val13, "", notes
        # the correct column already has a value: move nothing, both stay as they arrived
        for column, kind, labels in (("isbn", kind10, labels10), ("isbn13", kind13, labels13)):
            if kind == "wrong":
                for lab in labels:
                    notes.add(column, lab)
            notes.add(column, WARN_CHECK_NUMBERS)
        return raw10, raw13, notes

    stored = {}
    for column, raw, kind, val, labels in (("isbn", raw10, kind10, val10, labels10),
                                           ("isbn13", raw13, kind13, val13, labels13)):
        stored[column] = val if kind == "valid" else raw   # bad values kept as they arrived
        for lab in labels:
            notes.add(column, lab)
    return stored["isbn"], stored["isbn13"], notes


def what_to_do(labels):
    """One 'what to do' per kind of note, in note order (answer 28)."""
    out = []
    for lab in labels:
        if lab.startswith("Wrong ISBN") or lab == MISSING:
            todo = DO_FIND_ISBN
        elif lab.startswith("Warning duplicate ISBN"):
            todo = DO_DUPLICATE
        elif lab in (WARN_MISMATCH, WARN_CHECK_NUMBERS):
            todo = DO_WHICH_ISBN
        elif lab in (WARN_KEPT_EMPTY, WARN_KEPT_WRONG):
            todo = DO_PREVIOUS
        elif lab == WARN_NO_BOOK_ID:
            todo = DO_BOOK_ID
        else:
            continue
        if todo not in out:
            out.append(todo)
    return out


def notes_by_isbn(changes):
    """Split a changes_repairs note into the labels for each ISBN (rules section 2).

    "isbn: A; B; isbn13: C" -> {"isbn": [A, B], "isbn13": [C]}.
    Notes with no isbn prefix (missing book_id, Updated) are kept under None.
    """
    groups = {}
    current = None
    for part in (changes.split("; ") if changes else []):
        if part.startswith("isbn13: "):
            current, part = "isbn13", part[len("isbn13: "):]
        elif part.startswith("isbn: "):
            current, part = "isbn", part[len("isbn: "):]
        elif part.startswith("Updated:") or part == WARN_NO_BOOK_ID:
            current = None
        groups.setdefault(current, []).append(part)
    return groups


def still_to_fix(con):
    """Section 15: every book in the database whose isbn has a problem or which
    has a Warning, whichever run found it."""
    out = []
    for book_id, title, isbn, isbn13, changes in con.execute(
            'SELECT "book_id", "title", "isbn", "isbn13", changes_repairs FROM books ORDER BY rowid'):
        groups = notes_by_isbn(changes or "")
        labels = [lab for part in groups.values() for lab in part]
        isbn_problem = any(lab.startswith("Wrong ISBN") or lab == MISSING
                           for lab in groups.get("isbn", []))
        warning = any(lab.startswith("Warning") for lab in labels)
        if isbn_problem or warning:
            out.append({"book_id": book_id, "title": title, "isbn": isbn, "isbn13": isbn13,
                        "note": changes, "what_to_do": what_to_do(labels)})
    return out


# ---------------------------------------------------------------- database

def open_database():
    con = sqlite3.connect(DB_FILE)
    cols = ", ".join(f'"{c}" TEXT' for c in COLUMNS)
    con.execute(f"CREATE TABLE IF NOT EXISTS books ({cols}, changes_repairs TEXT)")
    # one row per book_id (rows with no book_id are never the same book - answer 7)
    con.execute("CREATE UNIQUE INDEX IF NOT EXISTS books_book_id "
                "ON books(book_id) WHERE book_id <> ''")
    return con


def load_existing(con):
    """book_id -> {rowid, values}, and an index of valid ISBNs -> book_ids."""
    existing = {}
    isbn_index = {"isbn": {}, "isbn13": {}}
    names = ", ".join(f'"{c}"' for c in COLUMNS)
    for row in con.execute(f"SELECT rowid, {names} FROM books ORDER BY rowid"):
        values = dict(zip(COLUMNS, row[1:]))
        if values["book_id"] != "":
            existing[values["book_id"]] = {"rowid": row[0], "values": values}
        for column in ("isbn", "isbn13"):
            if is_good(values[column], column):
                isbn_index[column].setdefault(values[column], {})[values["book_id"]] = None
    return existing, isbn_index


# ---------------------------------------------------------------- log

def read_log():
    """Earlier runs, never overwritten. Read before anything changes."""
    if not os.path.exists(LOG_FILE):
        return []
    with open(LOG_FILE, encoding="utf-8") as f:
        runs = json.load(f)
    if not isinstance(runs, list):
        sys.exit(f"Stopped: {LOG_FILE} is not a list of runs, so nothing was changed.")
    return runs


def write_log(runs):
    tmp = LOG_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(runs, f, indent=2, ensure_ascii=False)
        f.write("\n")
    os.replace(tmp, LOG_FILE)


# ---------------------------------------------------------------- main

def main():
    if len(sys.argv) != 2:
        sys.exit("Usage: python3 ingest.py <file.csv>")
    csv_path = sys.argv[1]
    if not os.path.isfile(csv_path):                      # answer 2
        sys.exit(f"Stopped: the file {csv_path} was not found. Nothing was changed.")

    ran_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")  # answer 27
    runs = read_log()
    con = open_database()
    existing, isbn_index = load_existing(con)

    counts = {"read": 0, "loaded": 0, "updated": 0, "skipped": 0, "rejected": 0,
              "repairs": 0, "isbn13_only_problems": 0}
    needs_attention = []
    not_loaded = []
    seen_in_file = set()

    finished, error = True, None
    try:
        with open(csv_path, newline="", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            reader.fieldnames                     # read the header (line 1)
            previous_line = reader.line_num
            for row in reader:
                line = previous_line + 1          # answer 26: header is line 1
                previous_line = reader.line_num
                counts["read"] += 1

                arrived = {c: (row.get(c) or "") for c in COLUMNS}   # missing column -> empty
                book_id = arrived["book_id"]
                title = arrived["title"]

                # rule 9: twice in the same file -> load the first, skip the second
                if book_id != "" and book_id in seen_in_file:
                    counts["skipped"] += 1
                    not_loaded.append({"line": line, "book_id": book_id, "title": title,
                                       "reason": REASON_TWICE})
                    continue
                if book_id != "":
                    seen_in_file.add(book_id)

                values = dict(arrived)
                values["isbn"], values["isbn13"], notes = check_isbns(arrived["isbn"], arrived["isbn13"])

                old = existing.get(book_id) if book_id != "" else None

                # rule 9: never replace a good ISBN with an empty or Wrong one
                if old is not None:
                    for column in ("isbn", "isbn13"):
                        old_value = old["values"][column]
                        if is_good(old_value, column) and not is_good(values[column], column):
                            cleaned_new = arrived[column].replace("-", "").replace(" ", "")
                            values[column] = old_value
                            notes.replace(column, [WARN_KEPT_EMPTY if cleaned_new == "" else WARN_KEPT_WRONG])

                # answer 11: both valid -> they must belong together
                if isbn10_valid(values["isbn"]) and isbn13_valid(values["isbn13"]):
                    if isbn10_to_13(values["isbn"]) != values["isbn13"]:
                        notes.add("isbn13", WARN_MISMATCH)

                # rule 10: same valid ISBN on a different book_id (database + this file)
                for column in ("isbn", "isbn13"):
                    if is_good(values[column], column):
                        others = [b for b in isbn_index[column].get(values[column], {}) if b != book_id]
                        if others:
                            notes.add(column, WARN_DUPLICATE.format(others[0]))

                first = [WARN_NO_BOOK_ID] if book_id == "" else []

                if old is None:
                    outcome = "loaded"
                    changes = notes.text(first=first)
                    con.execute(
                        f"INSERT INTO books ({', '.join(chr(34) + c + chr(34) for c in COLUMNS)}, changes_repairs) "
                        f"VALUES ({', '.join('?' * (len(COLUMNS) + 1))})",
                        [values[c] for c in COLUMNS] + [changes])
                else:
                    changed = [c for c in COLUMNS if values[c] != old["values"][c]]
                    if not changed:                               # rule 9 / answer 14: identical
                        counts["skipped"] += 1
                        not_loaded.append({"line": line, "book_id": book_id, "title": title,
                                           "reason": REASON_EXISTS})
                        continue
                    outcome = "updated"
                    changes = notes.text(first=first, last=["Updated: " + ", ".join(changed)])
                    sets = ", ".join(f'"{c}" = ?' for c in COLUMNS)
                    con.execute(f"UPDATE books SET {sets}, changes_repairs = ? WHERE rowid = ?",
                                [values[c] for c in COLUMNS] + [changes, old["rowid"]])
                    # the ISBN index follows the record
                    for column in ("isbn", "isbn13"):
                        isbn_index[column].get(old["values"][column], {}).pop(book_id, None)

                counts[outcome] += 1
                if book_id != "":
                    existing[book_id] = {"rowid": old["rowid"] if old else None, "values": values}
                for column in ("isbn", "isbn13"):
                    if is_good(values[column], column):
                        isbn_index[column].setdefault(values[column], {})[book_id] = None

                # rule 11 / answers 19, 25: repairs counted per value, problems listed
                labels = notes.all_labels()
                counts["repairs"] += labels.count(REPAIRED)
                isbn_problem = any(lab.startswith("Wrong ISBN") or lab == MISSING
                                   for lab in notes.labels("isbn"))
                warning = any(lab.startswith("Warning") for lab in labels) or bool(first)
                isbn13_problem = any(lab.startswith("Wrong ISBN") or lab == MISSING
                                     for lab in notes.labels("isbn13"))
                if isbn_problem or warning:
                    needs_attention.append({
                        "line": line, "book_id": book_id, "title": title,
                        "isbn_as_arrived": arrived["isbn"], "isbn13_as_arrived": arrived["isbn13"],
                        "outcome": outcome, "note": changes,
                        "what_to_do": what_to_do(first + labels),
                    })
                elif isbn13_problem:
                    counts["isbn13_only_problems"] += 1

        con.commit()
    except Exception as exc:                  # rules section 14: undo the whole run
        con.rollback()
        finished, error = False, f"{type(exc).__name__}: {exc}"
    fix_list = still_to_fix(con)              # rules section 15
    con.close()

    entry = {"ran_at": ran_at, "file": csv_path, "finished": finished}
    if error:
        entry["error"] = error
    entry.update({
        "counts": counts,
        "needs_attention": needs_attention,
        "not_loaded": not_loaded,
        "still_to_fix": fix_list,
    })
    runs.append(entry)
    write_log(runs)

    if not finished:
        sys.exit(f"Stopped: the run did not finish ({error}). "
                 "Nothing from this run was kept in books.db; the log says why.")

    print(f"Ran {ran_at} on {csv_path}")
    print(f"  read {counts['read']}, loaded {counts['loaded']}, updated {counts['updated']}, "
          f"skipped {counts['skipped']}, rejected {counts['rejected']}")
    print(f"  repairs {counts['repairs']}, rows needing a person {len(needs_attention)}, "
          f"rows whose only problem is in isbn13 {counts['isbn13_only_problems']}, "
          f"books still to fix {len(fix_list)}")
    print(f"  details: {os.path.basename(LOG_FILE)} (open it in report.html)")


if __name__ == "__main__":
    main()
