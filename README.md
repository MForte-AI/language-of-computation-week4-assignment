# Module 4 Assignment — MSAI-5523

This is my Module 4 assignment for MSAI-5523 (The Language of Computation).

- **Student:** Melissa Forte (GitHub: MForte-AI)
- **Partner:** Tio (GitHub: tioluwanimofe)

## How to run the tests

The tests are in `test_ingest.py`. They use **pytest**, a testing framework for Python.
They check that `ingest.py` does what `rules.md` says. They use their own
`test.db` in a temporary folder and never touch `books.db` or `ingestion-log.json`.

### 1. Open the terminal
1. Press **Command (⌘) + Space** to open Spotlight.
2. Type `Terminal` and press **Return**.

### 2. Go to the assignment folder
```bash
cd ~/workspace/language-of-computation/week4-assignment
```

### 3. Install what the tests need (first time only)
Make a private Python setup for this folder, called a virtual environment, and
install pytest into it:
```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install pytest
```
After `source .venv/bin/activate`, the prompt starts with `(.venv)`. The `.venv`
folder is listed in `.gitignore`, so it is never pushed to GitHub.

### 4. Run the tests
Every time you open a new Terminal window, go to the folder (step 2) and
switch the virtual environment on again:
```bash
source .venv/bin/activate
```
Then run the tests:
```bash
python -m pytest -v
```
Each test shows `PASSED` or `FAILED`, and the last line gives the totals.

To run the tests and also save what the terminal prints into a file:
```bash
python -m pytest -v 2>&1 | tee test-results.txt
```
(For the first run, before `ingest.py` is changed, use `test-results-before.txt`.)

## How to run ingest.py

### 1. Go to the assignment folder
```bash
cd ~/workspace/language-of-computation/week4-assignment
```

### 2. Start from an empty database (optional)
This deletes the database and the log, so the next run starts fresh:
```bash
rm -f books.db ingestion-log.json
```

### 3. Load the books
Load books.csv:
```bash
python3 ingest.py books.csv
```
Load books.csv again (every row is already there, so every row is skipped):
```bash
python3 ingest.py books.csv
```
Load the second delivery:
```bash
python3 ingest.py books-batch2.csv
```
Each run prints its counts and adds one entry to `ingestion-log.json`.

### 4. Open the report
```bash
open report.html
```
Click **Open ingestion-log.json** and choose `ingestion-log.json` from this folder.
