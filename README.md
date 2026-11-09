# yaml-duplicate-key-checker-cli

Find duplicate keys in YAML files, fail CI when a key appears twice.

[![CI](https://github.com/haiderstudio/yaml-duplicate-key-checker-cli/actions/workflows/ci.yml/badge.svg)](https://github.com/haiderstudio/yaml-duplicate-key-checker-cli/actions/workflows/ci.yml) [![Licence: MIT](https://img.shields.io/badge/Licence-MIT-yellow.svg)](LICENSE)

## What it does

`yaml_duplicate_key_checker` reads a YAML file and finds every
mapping key that appears twice at the same level — the same key,
any value — and reports each duplicate with the file, the line
numbers, and both values. It exits 1 when any duplicate is found,
so it can fail a CI run. A clean file exits 0.

- YAML silently keeps the last value when a key repeats and drops
  the earlier one, with no error at all. A duplicated key in a CI
  config, a Docker Compose file, or a GitHub Actions workflow
  deletes a setting without a sound. This tool catches the
  duplicate before the file ships, and points at both lines.
- Every repeat is reported, not just the first: a key listed three
  times is reported twice, at lines 2 and 3.
- The same key at a different nesting level is not a duplicate —
  `name` under `app` and `name` under `server` are different keys.
  The same key in two different list items is not a duplicate
  either — each item is its own mapping.
- Quoted keys count the same as plain keys: `"name"` and `'name'`
  are the same key as `name`. Keys are case-sensitive, the way
  YAML is: `Name` and `name` are different keys.
- A key repeated in a second document (after `---`) is not a
  duplicate — each document is checked on its own.
- Blank lines and comments are skipped. Block scalars (`|` and
  `>`) are skipped — lines inside them can look like keys and
  are not. Flow mappings (`{a: 1, b: 2}`) are skipped, not
  guessed at. A plain value that runs over several lines is read
  as one value, the way YAML reads it.
- A file given directly on the command line is always checked,
  whatever its name. A folder is walked for `.yaml` and `.yml`
  files, recursively by default (`--no-recursive` stops at the
  top level). `.git` folders are never walked, and directory
  links are never followed. `--exclude` skips files and folders
  by name pattern.
- `--json` prints the result as JSON (the human-readable lines
  go to standard error), and `--stdin` checks one YAML file read
  from standard input.

## Who it is for

Anyone who edits YAML by hand — developers writing CI configs,
Docker Compose files, GitHub Actions workflows, and app settings,
and anyone who has lost a setting to a duplicated key and only
found out when something broke.

## What it does NOT do

- It does not check whether a YAML file is valid in any other
  way — it is a duplicate-key check, not a YAML validator. A file
  can pass this check and still fail a real YAML parser for
  another reason.
- It does not check flow mappings (`{a: 1, a: 2}` on one line).
  Those lines are skipped, and a duplicate inside one is missed.
- It does not resolve anchors or merge keys (`<<: *defaults`).
  A merge key is treated like any other key; the keys it merges
  in are not expanded, so a duplicate smuggled in through a
  merge is missed.
- It does not check whether a value is the right type, or
  whether a key is spelled the way some other tool expects.
  That is a schema's job, not a duplicate check.
- It does not convert or rewrite anything. It is report-only,
  and it never touches the network.
- It uses no YAML library at all — the Python standard library
  has no YAML parser, so this tool is a hand-rolled line scanner
  (see "How it works" below), not a full parser.

## How this differs

- A GitHub search for `"yaml-duplicate-key-checker-cli"` returns
  0 results, and a search for `yaml duplicate key checker`
  returns 0 results (checked Nov 8, 2026) — no dedicated tool
  owns this job.
- Repo #48 (json-duplicate-key-checker-cli) checks the same
  silent failure in JSON; YAML is a different format with the
  same problem, and needs its own scanner because the two
  formats do not parse alike.

## How it works

The scanner reads block mappings line by line and tracks keys by
indentation level, so it knows which mapping a key belongs to. A
list item (`- `) starts a fresh mapping, so the same key in two
items is not a duplicate. A key with an inline plain value makes
deeper lines continuations of that value, not new keys — the way
YAML reads them. Block scalars and flow collections are skipped
whole, and a new document after `---` starts with empty keys.
The scanner was cross-checked against a real YAML parser on the
bundled examples and on tricky cases (nested lists, quoted keys,
block scalars, multi-line values, document markers): on every
case the parser can read, the scanner reports the same
duplicates at the same lines.

## Install

Python 3.10 or newer, nothing else to install.

```sh
git clone https://github.com/haiderstudio/yaml-duplicate-key-checker-cli.git
cd yaml-duplicate-key-checker-cli
```

## Usage

Check one clean file:

```sh
python3 src/yaml_duplicate_key_checker.py examples/good.yaml
```

```text
OK — 1 file(s) checked, all YAML files are clean.
```

Check a file with duplicates:

```sh
python3 src/yaml_duplicate_key_checker.py examples/duplicates.yaml
```

```text
examples/duplicates.yaml:5: duplicate key 'name' (first on line 3: first-app; this line: second-app)
examples/duplicates.yaml:9: duplicate key 'host' (first on line 8: localhost; this line: 127.0.0.1)
examples/duplicates.yaml:11: duplicate key 'port' (first on line 10: 8080; this line: 9090)
examples/duplicates.yaml:12: duplicate key 'port' (first on line 10: 8080; this line: 9091)
examples/duplicates.yaml:14: duplicate key 'quoted' (first on line 13: one; this line: two)
Checked 1 file(s), 5 problem(s) in 1 file(s).
```

The exit code is 1, so a CI run fails.

Check a whole folder:

```sh
python3 src/yaml_duplicate_key_checker.py examples
```

```text
examples/duplicates.yaml:5: duplicate key 'name' (first on line 3: first-app; this line: second-app)
examples/duplicates.yaml:9: duplicate key 'host' (first on line 8: localhost; this line: 127.0.0.1)
examples/duplicates.yaml:11: duplicate key 'port' (first on line 10: 8080; this line: 9090)
examples/duplicates.yaml:12: duplicate key 'port' (first on line 10: 8080; this line: 9091)
examples/duplicates.yaml:14: duplicate key 'quoted' (first on line 13: one; this line: two)
examples/configs/app.yaml:3: duplicate key 'host' (first on line 2: db.example.com; this line: db-backup.example.com)
Checked 4 file(s), 6 problem(s) in 2 file(s).
```

Check one file from standard input:

```sh
printf 'name: one\nname: two\n' | python3 src/yaml_duplicate_key_checker.py --stdin
```

```text
<stdin>:2: duplicate key 'name' (first on line 1: one; this line: two)
Checked 1 file(s), 1 problem(s) in 1 file(s).
```

Machine-readable output:

```sh
python3 src/yaml_duplicate_key_checker.py examples/configs/app.yaml --json
```

```json
{
  "files_checked": 1,
  "problems": [
    {
      "file": "examples/configs/app.yaml",
      "line": 3,
      "reason": "duplicate key 'host' (first on line 2: db.example.com; this line: db-backup.example.com)"
    }
  ],
  "files_with_problems": 1
}
```

## Examples

- `examples/good.yaml` — a clean config: nested mappings, the
  same key name at different levels, the same key in two list
  items, a block scalar holding lines that look like keys, and
  a quoted value holding a colon. Passes.
- `examples/duplicates.yaml` — five problems in one file: the
  same key twice, the same key three times, and a quoted key
  matching a plain key. Fails with exit 1.
- `examples/server.yaml` — a clean server config. Passes.
- `examples/configs/app.yaml` — one duplicate, in a subfolder.
  Fails with exit 1.
- `sh examples/run-example.sh` runs the checker on the whole
  `examples/` folder. Its output is in
  `examples/sample-output.md`.

## How it is tested

```sh
python3 tests/test_yaml_duplicate_key_checker.py
```

The tests cover: key parsing (plain, quoted, spaced keys,
`key : value`, URLs, lines that are not keys), every duplicate
shape with exact line numbers and both values (same level,
three occurrences, quoted vs plain, case-sensitive keys),
same key in different nesting levels passing, list items
(same key in two items passing, twice in one item failing,
bare dashes, nested lists), skipped lines (blank, comment,
block scalar, folded scalar, flow mapping, multi-line plain
value), document markers resetting the check, tab
indentation, anchors and merge keys, folder walking
(`.yaml`/`.yml` only, `.git` skipped, `--no-recursive`,
`--exclude`), `--stdin`, `--json`, exit codes 0/1/2,
unreadable and non-UTF-8 files, and the bundled examples
(the sample output is compared byte-for-byte against a fresh
run, and the outputs quoted in this README are checked
against real runs).

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md).

## Licence

MIT — see [LICENSE](LICENSE).

## Original work

This tool was written from scratch for this repo. The scanner
is hand-rolled because the Python standard library has no YAML
parser; the duplicate-key problem it solves is the same silent
failure as repo #48 (json-duplicate-key-checker-cli), in a
different format. The code, the wording, and the tests are
original.
