# Rules for loading books into books.db

## 1. Nothing is rejected
- every row loads; bad values are kept exactly as they arrived
- a person decides what to do, using the notes and the report


## 2. The Changes/Repairs column
- a new column on every book
- each note starts with the ISBN it is about: "isbn:" or "isbn13:"
- if there is more than one problem, note every one

## 3. Formatting repairs (in this order)
- remove hyphens and spaces (both ISBNs)
- lowercase x becomes capital X
- ISBN-10 with fewer than 10 characters: add zeros to the front until 10
- the repair is kept only if the check digit passes
- If an ISBN is in the wrong column (an ISBN-13 in the ISBN-10 column, or
  an ISBN-10 in the ISBN-13 column) and its check digit passes, move it to
  the correct column. The note on the moved ISBN is "Repaired". The column
  it moved out of is now empty, so it gets "Missing ISBN".
- If the correct column already has a value, do not move anything: both
  values stay as they arrived and get the note "Warning: check ISBN numbers
  for correct one".
- if the check digit fails, the value stays as it arrived and gets the
  Wrong ISBN note
- repair notes: Repaired

## 4. Checking an ISBN-10
- exactly 10 characters: 9 digits, then a digit or X
- check digit: weights 10 down to 1, total must divide evenly by 11

## 5. Checking an ISBN-13
- exactly 13 digits, starts with 978 or 979
- check digit: weights 1,3,1,3..., total must divide evenly by 10

## 6. Problem and warning labels
- Wrong ISBN: contains a letter or symbol
- Wrong ISBN: wrong number of digits (N)
- Wrong ISBN: does not start with 978 or 979
- Wrong ISBN: check digit fails
- Missing ISBN        (also when isbn is empty beside a 979 ISBN-13)
- Warning ISBN-10 and ISBN-13 do not match
- Warning duplicate ISBN: also used by book_id N
- Warning: new delivery had no ISBN, kept previous
- Warning: check ISBN numbers for correct one

## 7. When is a repair a guess?
- repairs are only made when every digit is already
  there AND the check digit confirms it, so no repair is a guess;
  anything that would be a guess is labeled, not repaired

## 8. What makes two rows the same book
- same book_id
- a book with no usable ISBN still has a book_id, so it is still handled

## 9. When a book arrives again
- identical: skip, count as "already exists"
- twice in the same file: load the first, skip the second
- something changed: update it, note "Updated: ..."
- compare values after repairs
- never replace a good ISBN with an empty or Wrong one; keep the old one
  and add the warning

## 10. Same ISBN on two different books (different book_id)
- look in the database and in the current file
- both load; only the newcomer gets the warning, naming the other book_id

## 11. The morning report
- Morning report at the top. Show when it ran, which file it ran, and the counts for the outcomes loaded, updated, skipped and rejected. List first every Wrong ISBN, Missing ISBN and Warning. Each shows the line number, book_id, title, the value as it arrived, the note, and what to do. For example: Wrong or Missing ISBN → "find the correct ISBN on the book or from the publisher"; duplicate ISBN → "check which book the ISBN belongs to". Repairs should stay out of the first identified rows and be mixed in with the rows that pass. In the column that indicates changes say, 'Repaired'. Give a repairs count only at the top of the morning report. Skipped rows are listed with their reason.

## 12. Examples
| # | Value | Column | Checks | Result / note |
|---|---|---|---|---|
| 1 | `439023483` | isbn | No hyphens, spaces or lowercase x. 9 characters, so add one zero: `0439023483`. Check digit total 176 = 16 × 11. It passes, so the zero is kept. | Stored as `0439023483`. Note `isbn: Repaired`. Not listed in the report; counted in the repairs total. |
| 2 | `1854433017` | isbn | Nothing to clean. 10 characters, so no zeros are added. Check digit total 210, which doesn't divide evenly by 11. It fails. | Stored as `1854433017`. Note `isbn: Wrong ISBN: check digit fails`. Listed at the top of the report with "find the correct ISBN on the book or from the publisher." |
| 3 | `61120081` | isbn | 8 digits, add two 0's in front. Check digit total must divide evenly by 11 (88 = 8 × 11, passes). | Stored `0061120081`, `isbn: Repaired` |
| 4 | `0-450-19827-8` | isbn | Contains dashes. Check digit total must divide evenly by 11 (187 = 17 × 11, passes). | Stored `0450198278`, `isbn: Repaired` |
| 5 | `␣162 001 4750␣` (spaces at both ends) | isbn | Contains spaces. Check digit total must divide evenly by 11 (132 = 12 × 11, passes). | Stored `1620014750`, `isbn: Repaired` |
| 6 | `031200009x` | isbn | 'x' to capital 'X'. Check digit total must divide evenly by 11 (77 = 7 × 11, passes). | Stored `031200009X`, `isbn: Repaired` |
| 7 | `385535144` | isbn | 9 digits, add '0' at front: `0385535144`. Check digit total 206 fails, so the zero is not kept. | Stored as arrived, `385535144`. Notes `isbn: Wrong ISBN: check digit fails; Wrong ISBN: wrong number of digits (9)`. Listed first in the report with "find the correct ISBN on the book or from the publisher." |
| 8 | `04390A3483` | isbn | Contains a letter. | Stored as arrived. `isbn: Wrong ISBN: contains a letter or symbol`, listed first in the report with "find the correct ISBN on the book or from the publisher." |
| 9 | `15287463097` | isbn | 11 digits, not an ISBN number. | Stored as arrived. `isbn: Wrong ISBN: wrong number of digits (11)`, listed first in the report with "find the correct ISBN on the book or from the publisher." |
| 10 | `9781982147600` | isbn | Appears in the ISBN-10 column but is a valid ISBN-13 number: 13 digits, starts with 978, check digit total 110 = 11 × 10, passes. | Repaired: moved to ISBN-13 column, removed from ISBN-10 column. Notes `isbn13: Repaired; isbn: Missing ISBN`. Listed first in the report because of Missing ISBN, with "find the correct ISBN on the book or from the publisher." |
| 11 | `9.78043902348e+12` | isbn13 | Decimal, letters and symbols are not part of an ISBN. Too many digits (14). | Stored as arrived. `isbn13: Wrong ISBN: contains a letter or symbol; Wrong ISBN: wrong number of digits (14)`. Listed first in the report. |
| 12 | `2.94001623192e+12` | isbn13 | Decimal, letters and symbols are not part of an ISBN. Too many digits (14). Does not start with 978 or 979. | Stored as arrived. `isbn13: Wrong ISBN: contains a letter or symbol; Wrong ISBN: wrong number of digits (14); Wrong ISBN: does not start with 978 or 979`. Listed first in the report. |
| 13 | `1416524797` on *Paper Moons* | isbn | Valid ISBN-10 (check digit total 198 = 18 × 11). book_id 9 (*Angels & Demons*) already in database with this ISBN. | Loaded. `isbn: Warning duplicate ISBN: also used by book_id 9`, listed first with "check which book the ISBN belongs to." |
| 14 | (empty) + (empty) | both | Both columns empty. | Loaded. `isbn: Missing ISBN; isbn13: Missing ISBN`, listed first with "find the correct ISBN on the book or from the publisher." |
| 15 | (empty) beside `9798351220413` | both | ISBN-13 is valid. Starts with 979. 13 digit check passes (100 = 10 × 10). | Loaded. `isbn: Missing ISBN`, listed first with "find the correct ISBN on the book or from the publisher." |

## 13. Answers to Claude's questions
Each line is Claude's question, then my answer in my own words.

### Running the script
1. Is the file chosen by typing its name after the script (`python3 ingest.py books.csv`), with books.db and ingestion-log.json made in the same folder? **Yes**
2. If the file can't be read (missing, or not the expected 23 columns), stop with an error and change nothing? **Only if it is missing.** Follow-up, chosen: Stop only if missing. If the file is missing: stop with an error, change nothing, no log entry. If it exists but has the wrong columns: still load every row (rule 1, nothing is rejected), storing any missing column as empty.

### The database
3. Which columns go in books.db? **all 23CSV columns plus Changes/Repairs.**
4. Are the other 22 columns stored exactly as they arrive, as text? **Yes**
5. The Changes/Repairs column's name in the database? **changes_repairs**
6. A book with nothing repaired and no problems has an empty Changes/Repairs? **Yes.**
7. A row with no book_id? **load it with the note Warning: missing book_id, and never treat it as the same book as any other row.**

### The exact checking order
8. a. Remove hyphens and spaces, x becomes X. b. In the isbn column only, if the value is all digits (plus a final X) and shorter than 10, add zeros. c. If the result is a valid ISBN, store it, note Repaired if anything changed. d. Otherwise store the value as it arrived and label the problems found in the cleaned value from step a: letter or symbol (X allowed only as the last character of an ISBN-10); wrong number of digits (N) (count digits only); does not start with 978 or 979 (ISBN-13, judged on its digits); check digit fails, tested only when the value has the right shape after step b. **Yes**
   Follow-up: example 8 (`04390A3483`) disagreed with "count digits only". Chosen: **Example 8 is right.** Add the digit-count label only when the value also has the wrong number of characters (not 10 or 13). 04390A3483 is 10 characters, so it gets only the letter note.
9. No zeros are added to values in the isbn13 column? **Yes**
10. A 13-digit value in the isbn column that fails the ISBN-13 check is not moved and gets wrong number of digits (13)? **Yes**

### Checks across columns and across books
11. "ISBN-10 and ISBN-13 do not match" is checked only when both values are valid, and the note goes on isbn13:? **Yes**
12. Duplicate ISBNs compare only valid ISBNs, never empty or Wrong ones? **Yes**
13. Compare ISBN-10 with ISBN-10 and ISBN-13 with ISBN-13 only? **same column only**

### A book that arrives again
14. "Identical" means all 23 columns are equal after repairs? **Yes**
15. What follows "Updated:"? **the names of the columns that changed, e.g. Updated: ratings_count, work_ratings_count, ratings_5 with no isbn: prefix.**
16. On an update, Changes/Repairs is replaced by the notes for the new delivery plus the Updated note? **Yes**
17. Does "kept previous" also cover a new ISBN that is Wrong? **use a separate note, Warning: new delivery had a wrong ISBN, kept previous, because "had no ISBN" wouldn't be true.**
18. A "good" ISBN is one that was valid as it arrived, or Repaired? **Yes**

### The report and the log
19. Every books.csv row has an isbn13 problem. Which rows go in the "List first" section? **List s row there only if its isbn has a problem or it has a Warning, and give a count at the top for rows whose only problems is in the isbn13.**
20. The second run of books.csv skips all 10,000 rows; list them all? **list them all, because the assignment requires the rows that weren't loaded.**
21. Are problem rows listed again on later runs? **Recommended: no. List problems only for rows loaded or updated in this run.**
22. Reason text for skipped rows? **Recommended: already exists and appeared twice in this file.**
23. The log also stores the problem rows and the repairs count? **Yes**
24. The counts at the top include "read"? **Yes**
25. Is the repairs count per ISBN value? **per value.**
26. Line number counts the header as line 1, and "value as it arrived" shows both isbn and isbn13? **Yes**
27. "When it ran" is my computer's local time, e.g. 2026-11-06 14:30:05? **Yes**
28. What to do for the notes rule 11 doesn't cover? Chosen: **Use these texts.** ISBN-10 and ISBN-13 do not match → "check which ISBN is correct on the book or from the publisher". Check ISBN numbers for correct one → same text. New delivery had no/a wrong ISBN, kept previous → "check whether the previous ISBN is still correct". Missing book_id → "find the book's book_id". A row with several notes shows one "what to do" per kind of note, in note order.

## 14. If the run stops partway (from the earlier rules)
- if the script crashes in the middle of a run, the whole run is undone: nothing from that run stays in books.db
- the run is still added to ingestion-log.json, marked as not finished, with the error
- the morning report shows whether each run finished

## 15. Runs and the log
- every run adds one entry to the end of ingestion-log.json; earlier entries
  are never changed or removed (a missing file adds nothing, answer 2)
- every row read gets exactly one outcome, so
  loaded + updated + skipped + rejected = read (rejected is always 0, rule 1)
- running the same file again never adds a book twice (a row with no book_id
  is still loaded each time, answer 7)
- every report also has a "Still to fix" list: every book in the database,
  after this run, whose isbn has a problem or which has a Warning, whichever
  run found it
- each entry has:
  - ran_at, file, finished (true/false), and error if it did not finish
  - counts: read, loaded, updated, skipped, rejected, repairs, isbn13_only_problems
  - needs_attention: this run's rows listed first, each with line, book_id, title,
    isbn_as_arrived, isbn13_as_arrived, note, what_to_do
  - not_loaded: every skipped row, with line, book_id, title, reason
  - still_to_fix: every book still needing a person, with book_id, title,
    isbn, isbn13, note, what_to_do
