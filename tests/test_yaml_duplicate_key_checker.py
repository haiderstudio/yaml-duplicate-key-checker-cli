"""Tests for yaml-duplicate-key-checker-cli. Standard library only."""

import ast
import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
SRC = ROOT / "src" / "yaml_duplicate_key_checker.py"

sys.path.insert(0, str(ROOT / "src"))
import yaml_duplicate_key_checker as ydc
from yaml_duplicate_key_checker import (
    Problem, check_file, collect, parse_key_line, scan_text,
    strip_comment, value_kind,
)


def problems_as_tuples(text):
    return [(p.line, p.reason) for p in scan_text(text, "test.yaml")]


class StripCommentTests(unittest.TestCase):
    def test_trailing_comment_removed(self):
        self.assertEqual(strip_comment("a: 1 # note"), "a: 1 ")

    def test_full_line_comment(self):
        self.assertEqual(strip_comment("# full line"), "")

    def test_hash_inside_double_quotes_kept(self):
        self.assertEqual(strip_comment('a: "x # y"'), 'a: "x # y"')

    def test_hash_inside_single_quotes_kept(self):
        self.assertEqual(strip_comment("a: 'x # y'"), "a: 'x # y'")

    def test_hash_without_space_kept(self):
        self.assertEqual(strip_comment("url: http://x#y"),
                         "url: http://x#y")


class ParseKeyLineTests(unittest.TestCase):
    def test_plain(self):
        self.assertEqual(parse_key_line("name: value"), ("name", "value"))

    def test_spaced_key(self):
        self.assertEqual(parse_key_line("my key: 1"), ("my key", "1"))

    def test_space_before_colon(self):
        self.assertEqual(parse_key_line("key : 1"), ("key", "1"))

    def test_empty_value(self):
        self.assertEqual(parse_key_line("key:"), ("key", ""))

    def test_double_quoted_key(self):
        self.assertEqual(parse_key_line('"my key": v'), ("my key", "v"))

    def test_single_quoted_key(self):
        self.assertEqual(parse_key_line("'it''s': v"), ("it's", "v"))

    def test_double_quoted_escape(self):
        self.assertEqual(parse_key_line(r'"a\"b": v'), ('a"b', "v"))

    def test_not_a_key(self):
        self.assertIsNone(parse_key_line("just text"))

    def test_no_space_after_colon_is_not_a_key(self):
        self.assertIsNone(parse_key_line("key:value"))

    def test_url_is_not_a_key(self):
        self.assertIsNone(parse_key_line("http://example.com"))

    def test_url_value_kept_whole(self):
        self.assertEqual(parse_key_line("url: http://x:8080/y"),
                         ("url", "http://x:8080/y"))

    def test_explicit_key_marker_stripped(self):
        self.assertEqual(parse_key_line("? key: v"), ("key", "v"))

    def test_flow_line_is_not_a_key(self):
        self.assertIsNone(parse_key_line("{a: 1}"))


class ValueKindTests(unittest.TestCase):
    def test_empty(self):
        self.assertEqual(value_kind(""), ("empty", ""))

    def test_anchor_only_is_empty(self):
        self.assertEqual(value_kind("&a"), ("empty", ""))
        self.assertEqual(value_kind("&a !tag"), ("empty", ""))

    def test_block_scalar(self):
        self.assertEqual(value_kind("|"), ("block", "|"))
        self.assertEqual(value_kind("|-"), ("block", "|-"))
        self.assertEqual(value_kind(">"), ("block", ">"))
        self.assertEqual(value_kind("&a |"), ("block", "|"))

    def test_flow(self):
        self.assertEqual(value_kind("{a: 1}"), ("flow", "{a: 1}"))

    def test_quoted(self):
        self.assertEqual(value_kind('"text"'), ("quoted", '"text"'))

    def test_plain_scalar(self):
        self.assertEqual(value_kind("plain"), ("scalar", "plain"))


class ScanTextTests(unittest.TestCase):
    def test_clean_file(self):
        self.assertEqual(problems_as_tuples("a: 1\nb: 2\n"), [])

    def test_duplicate_same_level(self):
        self.assertEqual(
            problems_as_tuples("a: 1\na: 2\n"),
            [(2, "duplicate key 'a' (first on line 1: 1; this line: 2)")])

    def test_three_occurrences_reported_twice(self):
        self.assertEqual(
            problems_as_tuples("a: 1\na: 2\na: 3\n"),
            [(2, "duplicate key 'a' (first on line 1: 1; this line: 2)"),
             (3, "duplicate key 'a' (first on line 1: 1; this line: 3)")])

    def test_same_key_different_levels_is_fine(self):
        text = ("top:\n"
                "  name: outer\n"
                "  inner:\n"
                "    name: inner\n")
        self.assertEqual(problems_as_tuples(text), [])

    def test_same_key_in_two_list_items_is_fine(self):
        self.assertEqual(problems_as_tuples("- name: a\n- name: b\n"), [])

    def test_same_key_twice_in_one_list_item_fails(self):
        self.assertEqual(
            problems_as_tuples("- name: a\n  name: b\n- name: c\n"),
            [(2, "duplicate key 'name' (first on line 1: a; this line: b)")])

    def test_bare_dash_items_are_separate(self):
        text = "-\n  name: a\n-\n  name: b\n"
        self.assertEqual(problems_as_tuples(text), [])

    def test_nested_lists(self):
        text = "- - a: 1\n  - a: 2\n- - a: 3\n"
        self.assertEqual(problems_as_tuples(text), [])

    def test_quoted_key_matches_plain_key(self):
        text = '"name": one\n\'name\': two\n'
        self.assertEqual(
            problems_as_tuples(text),
            [(2, "duplicate key 'name' (first on line 1: one; this line: two)")])

    def test_keys_are_case_sensitive(self):
        self.assertEqual(problems_as_tuples("Name: 1\nname: 2\n"), [])

    def test_comments_skipped(self):
        text = "# a: 1\na: 1 # trailing\na: 2\n"
        self.assertEqual(
            problems_as_tuples(text),
            [(3, "duplicate key 'a' (first on line 2: 1; this line: 2)")])

    def test_hash_inside_quoted_value(self):
        text = 'note: "a # b"\nnote: "c"\n'
        self.assertEqual(
            problems_as_tuples(text),
            [(2, "duplicate key 'note' (first on line 1: \"a # b\"; "
                  "this line: \"c\")")])

    def test_block_scalar_lines_skipped(self):
        text = ("notes: |\n"
                "  fake: key\n"
                "  fake: key2\n"
                "real: 1\n"
                "real: 2\n")
        self.assertEqual(
            problems_as_tuples(text),
            [(5, "duplicate key 'real' (first on line 4: 1; this line: 2)")])

    def test_folded_scalar_lines_skipped(self):
        text = "notes: >\n  fake: key\nreal: 1\n"
        self.assertEqual(problems_as_tuples(text), [])

    def test_flow_mapping_on_one_line_skipped(self):
        # Documented gap: flow style is not checked.
        self.assertEqual(problems_as_tuples("settings: {a: 1, a: 2}\n"), [])

    def test_flow_mapping_over_lines_skipped(self):
        text = "settings: {a: 1,\n  a: 2}\nother: 1\nother: 2\n"
        self.assertEqual(
            problems_as_tuples(text),
            [(4, "duplicate key 'other' (first on line 3: 1; this line: 2)")])

    def test_multiline_plain_value_is_one_value(self):
        text = ("summary: a long value\n"
                "  that keeps going\n"
                "  over two lines\n"
                "other: 1\n")
        self.assertEqual(problems_as_tuples(text), [])

    def test_continuation_line_that_looks_like_a_key(self):
        # A plain value's continuation is not a key, even when it
        # contains a colon. (The file is not valid YAML for other
        # reasons; this tool checks duplicates only.)
        text = ("summary: a long value\n"
                "  that keeps: going\n"
                "other: 1\n")
        self.assertEqual(problems_as_tuples(text), [])

    def test_multiline_quoted_value(self):
        text = ('desc: "first line\n'
                '  second line"\n'
                "name: 1\n"
                "name: 2\n")
        self.assertEqual(
            problems_as_tuples(text),
            [(4, "duplicate key 'name' (first on line 3: 1; this line: 2)")])

    def test_document_markers_reset_the_check(self):
        text = "---\nname: one\n---\nname: two\n"
        self.assertEqual(problems_as_tuples(text), [])

    def test_tab_indentation_is_a_problem(self):
        text = "a:\n\tb: 1\n"
        self.assertEqual(
            problems_as_tuples(text),
            [(2, "tab character used for indentation "
                  "(YAML forbids tabs for indentation)")])

    def test_anchor_then_nested_keys(self):
        text = ("defaults: &defaults\n"
                "  timeout: 30\n"
                "service:\n"
                "  timeout: 60\n")
        self.assertEqual(problems_as_tuples(text), [])

    def test_merge_key_not_expanded(self):
        text = ("defaults: &d\n"
                "  timeout: 30\n"
                "service:\n"
                "  <<: *d\n"
                "  timeout: 60\n")
        self.assertEqual(problems_as_tuples(text), [])

    def test_empty_value_then_nested_duplicate(self):
        text = "a:\n  b: 1\n  b: 2\n"
        self.assertEqual(
            problems_as_tuples(text),
            [(3, "duplicate key 'b' (first on line 2: 1; this line: 2)")])

    def test_nested_block_value_shown_as_nested_block(self):
        text = "a:\n  x: 1\na:\n  y: 2\n"
        self.assertEqual(
            problems_as_tuples(text),
            [(3, "duplicate key 'a' (first on line 1: nested block; "
                  "this line: nested block)")])

    def test_key_with_spaces(self):
        text = "my key: 1\nmy key: 2\n"
        self.assertEqual(
            problems_as_tuples(text),
            [(2, "duplicate key 'my key' (first on line 1: 1; this line: 2)")])

    def test_url_value(self):
        text = ("site: http://example.com:8080/x\n"
                "site: http://other.com\n")
        self.assertEqual(
            problems_as_tuples(text),
            [(2, "duplicate key 'site' (first on line 1: "
                  "http://example.com:8080/x; this line: http://other.com)")])

    def test_numeric_keys(self):
        text = "8080: a\n8080: b\n"
        self.assertEqual(
            problems_as_tuples(text),
            [(2, "duplicate key '8080' (first on line 1: a; this line: b)")])

    def test_crlf_line_endings(self):
        text = "a: 1\r\na: 2\r\n"
        self.assertEqual(
            problems_as_tuples(text),
            [(2, "duplicate key 'a' (first on line 1: 1; this line: 2)")])

    def test_long_value_is_shortened(self):
        text = "a: " + "x" * 70 + "\na: short\n"
        problems = problems_as_tuples(text)
        self.assertEqual(len(problems), 1)
        self.assertEqual(
            problems[0][1],
            "duplicate key 'a' (first on line 1: " + "x" * 57 + "...; "
            "this line: short)")


class CheckFileTests(unittest.TestCase):
    def test_non_utf8_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "bad.yaml"
            path.write_bytes(b"a: \xff\n")
            problems = check_file(path)
            self.assertEqual(len(problems), 1)
            self.assertIn("not valid UTF-8", problems[0].reason)

    def test_null_byte_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "bad.yaml"
            path.write_bytes(b"a: 1\x00\n")
            problems = check_file(path)
            self.assertEqual(len(problems), 1)
            self.assertIn("null byte", problems[0].reason)


class CollectTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def write(self, rel, text):
        path = self.root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
        return path

    def test_folder_walks_yaml_only(self):
        self.write("a.yaml", "x: 1\nx: 2\n")
        self.write("b.yml", "y: 1\n")
        self.write("c.txt", "x: 1\nx: 2\n")
        self.write("d.json", '{"x": 1, "x": 2}')
        checked, problems = collect([str(self.root)])
        names = sorted(p.name for p in checked)
        self.assertEqual(names, ["a.yaml", "b.yml"])
        self.assertEqual(len(problems), 1)

    def test_git_folder_never_walked(self):
        self.write(".git/evil.yaml", "x: 1\nx: 2\n")
        self.write("good.yaml", "x: 1\n")
        checked, problems = collect([str(self.root)])
        self.assertEqual([p.name for p in checked], ["good.yaml"])
        self.assertEqual(problems, [])

    def test_no_recursive(self):
        self.write("top.yaml", "x: 1\n")
        self.write("sub/inner.yaml", "x: 1\nx: 2\n")
        checked, problems = collect([str(self.root)], recursive=False)
        self.assertEqual([p.name for p in checked], ["top.yaml"])
        self.assertEqual(problems, [])

    def test_exclude_pattern(self):
        self.write("keep.yaml", "x: 1\nx: 2\n")
        self.write("skip.yaml", "x: 1\nx: 2\n")
        checked, problems = collect([str(self.root)], exclude=["skip.yaml"])
        self.assertEqual([p.name for p in checked], ["keep.yaml"])
        self.assertEqual(len(problems), 1)

    def test_direct_file_any_name_is_checked(self):
        path = self.write("plain.txt", "x: 1\nx: 2\n")
        checked, problems = collect([str(path)])
        self.assertEqual(checked, [path])
        self.assertEqual(len(problems), 1)

    def test_missing_path_is_a_problem(self):
        checked, problems = collect([str(self.root / "nope.yaml")])
        self.assertEqual(checked, [])
        self.assertEqual(len(problems), 1)
        self.assertIn("no such file or folder", problems[0].reason)


class CliTests(unittest.TestCase):
    def run_cli(self, args, stdin_text=None):
        return subprocess.run(
            [sys.executable, str(SRC)] + args,
            input=stdin_text, capture_output=True, text=True, cwd=ROOT)

    def test_clean_file_exits_zero(self):
        result = self.run_cli(["examples/good.yaml"])
        self.assertEqual(result.returncode, 0)
        self.assertEqual(
            result.stdout,
            "OK — 1 file(s) checked, all YAML files are clean.\n")

    def test_duplicates_file_exits_one(self):
        result = self.run_cli(["examples/duplicates.yaml"])
        self.assertEqual(result.returncode, 1)
        self.assertIn("Checked 1 file(s), 5 problem(s) in 1 file(s).",
                      result.stdout)

    def test_no_args_exits_two(self):
        result = self.run_cli([])
        self.assertEqual(result.returncode, 2)

    def test_stdin_with_paths_exits_two(self):
        result = self.run_cli(["--stdin", "examples/good.yaml"])
        self.assertEqual(result.returncode, 2)

    def test_stdin_clean(self):
        result = self.run_cli(["--stdin"], stdin_text="a: 1\nb: 2\n")
        self.assertEqual(result.returncode, 0)
        self.assertIn("all YAML files are clean.", result.stdout)

    def test_stdin_duplicate(self):
        result = self.run_cli(["--stdin"], stdin_text="name: one\nname: two\n")
        self.assertEqual(result.returncode, 1)
        self.assertIn(
            "<stdin>:2: duplicate key 'name' (first on line 1: one; "
            "this line: two)", result.stdout)

    def test_json_output(self):
        result = self.run_cli(["examples/configs/app.yaml", "--json"])
        self.assertEqual(result.returncode, 1)
        data = json.loads(result.stdout)
        self.assertEqual(data["files_checked"], 1)
        self.assertEqual(data["files_with_problems"], 1)
        self.assertEqual(len(data["problems"]), 1)
        self.assertEqual(data["problems"][0]["line"], 3)
        self.assertIn("duplicate key 'host'", data["problems"][0]["reason"])
        # In JSON mode the human lines go to standard error.
        self.assertIn("duplicate key 'host'", result.stderr)

    def test_version(self):
        result = self.run_cli(["--version"])
        self.assertEqual(result.returncode, 0)
        self.assertIn("yaml_duplicate_key_checker 1.0.0", result.stdout)


class ExampleTests(unittest.TestCase):
    def run_cli(self, args, stdin_text=None):
        return subprocess.run(
            [sys.executable, str(SRC)] + args,
            input=stdin_text, capture_output=True, text=True, cwd=ROOT)

    def test_sample_output_matches_fresh_run(self):
        sample = (ROOT / "examples" / "sample-output.md").read_text()
        block = re.search(r"```text\n(.*?)```", sample, re.S).group(1)
        result = subprocess.run(
            ["sh", "examples/run-example.sh"],
            capture_output=True, text=True, cwd=ROOT)
        self.assertEqual(result.returncode, 0)
        self.assertEqual(block.strip(), result.stdout.strip())

    def test_readme_text_blocks_match_real_runs(self):
        readme = (ROOT / "README.md").read_text()
        blocks = re.findall(r"```text\n(.*?)```", readme, re.S)
        self.assertEqual(len(blocks), 4)
        runs = [
            self.run_cli(["examples/good.yaml"]),
            self.run_cli(["examples/duplicates.yaml"]),
            self.run_cli(["examples"]),
            self.run_cli(["--stdin"], stdin_text="name: one\nname: two\n"),
        ]
        for block, result in zip(blocks, runs):
            self.assertEqual(block.strip(), result.stdout.strip())

    def test_readme_json_block_matches_real_run(self):
        readme = (ROOT / "README.md").read_text()
        blocks = re.findall(r"```json\n(.*?)```", readme, re.S)
        self.assertEqual(len(blocks), 1)
        result = self.run_cli(["examples/configs/app.yaml", "--json"])
        self.assertEqual(blocks[0].strip(), result.stdout.strip())


class HygieneTests(unittest.TestCase):
    def test_gitignore_first_line_is_env(self):
        lines = (ROOT / ".gitignore").read_text().splitlines()
        self.assertEqual(lines[0], ".env")

    def test_no_banned_words_outside_tests(self):
        banned = ["TODO", "FIXME", "XXX", "lorem", "coming soon"]
        for path in ROOT.rglob("*"):
            if not path.is_file():
                continue
            if ".git" in path.parts or "__pycache__" in path.parts:
                continue
            if "tests" in path.parts:
                continue
            text = path.read_text(errors="replace")
            for word in banned:
                self.assertNotIn(word, text,
                                 f"{word} found in {path.relative_to(ROOT)}")

    def test_no_absolute_paths(self):
        for path in ROOT.rglob("*"):
            if not path.is_file():
                continue
            if ".git" in path.parts or "__pycache__" in path.parts:
                continue
            if "tests" in path.parts:
                continue
            text = path.read_text(errors="replace")
            self.assertNotIn("/home/hatch", text,
                             f"absolute path in {path.relative_to(ROOT)}")
            self.assertNotIn("/Users/", text,
                             f"absolute path in {path.relative_to(ROOT)}")
            self.assertNotIn("/tmp/", text,
                             f"absolute path in {path.relative_to(ROOT)}")

    def test_stdlib_only_imports(self):
        allowed_src = {
            "argparse", "fnmatch", "json", "os", "re", "sys", "pathlib",
        }
        allowed_tests = allowed_src | {
            "io", "subprocess", "tempfile", "unittest", "ast",
            "yaml_duplicate_key_checker",
        }
        for path, allowed in [(SRC, allowed_src),
                              (Path(__file__), allowed_tests)]:
            tree = ast.parse(path.read_text())
            imported = set()
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    imported.update(a.name.split(".")[0] for a in node.names)
                elif isinstance(node, ast.ImportFrom):
                    if node.module:
                        imported.add(node.module.split(".")[0])
            self.assertTrue(imported <= allowed,
                            f"{path.name} imports non-stdlib: "
                            f"{imported - allowed}")
            self.assertNotIn("yaml", imported)

    def test_no_yaml_library_import_in_source(self):
        text = SRC.read_text()
        self.assertNotIn("import yaml\n", text)
        self.assertNotIn("from yaml ", text)
        self.assertNotIn("from yaml.", text)

    def test_no_secrets_in_repo(self):
        for path in ROOT.rglob("*"):
            if not path.is_file():
                continue
            if ".git" in path.parts or "__pycache__" in path.parts:
                continue
            if "tests" in path.parts:
                continue
            text = path.read_text(errors="replace").lower()
            for marker in ["api_key", "api-key", "password =", "secret ="]:
                self.assertNotIn(marker, text,
                                 f"possible secret in {path.relative_to(ROOT)}")


if __name__ == "__main__":
    unittest.main()
