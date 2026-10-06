"""Behaviour tests for the lexer kernel.

The tests describe what a caller of the kernel is allowed to observe: the
tokens a piece of source turns into, the line, column and span each token
reports, the errors a broken source raises, and the EOF token that closes a
run.  Run them from the project root:

    python3 -m unittest discover -s tests -v
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import lexan


def scan(source):
    """The tokens of source; a source the kernel refuses fails the test."""
    try:
        return lexan.tokenize(source)
    except lexan.LexError as error:
        raise AssertionError("source %r was refused: %s" % (source, error))


def body(source):
    """The (kind, value) pairs of the tokens, without the closing EOF."""
    tokens = scan(source)
    if tokens and tokens[-1].kind == lexan.EOF:
        tokens = tokens[:-1]
    return [(token.kind, token.value) for token in tokens]


def places(source):
    """The (value, line, column, start, end) of the tokens, without EOF."""
    return [
        (token.value, token.line, token.column, token.start, token.end)
        for token in scan(source)
        if token.kind != lexan.EOF
    ]


class TokenStreamTests(unittest.TestCase):
    """The tokens a piece of source turns into."""

    def test_a_plain_run_is_read_in_order_and_cut_from_the_source(self):
        source = "total = price + 7 * count"
        self.assertEqual(body(source), [
            (lexan.NAME, "total"),
            (lexan.PUNCT, "="),
            (lexan.NAME, "price"),
            (lexan.PUNCT, "+"),
            (lexan.NUMBER, "7"),
            (lexan.PUNCT, "*"),
            (lexan.NAME, "count"),
        ])
        first = scan(source)[0]
        self.assertEqual(
            (first.kind, first.value, first.line, first.column,
             first.start, first.end),
            (lexan.NAME, "total", 1, 1, 0, 5),
        )
        self.assertEqual(body(""), [])
        self.assertEqual(body("   \n\t "), [])

        spelled = 'if (x > 10) {\n    y = "a\\nb";  # note\n}\n'
        tokens = [token for token in scan(spelled) if token.kind != lexan.EOF]
        self.assertEqual([token.kind for token in tokens], [
            lexan.KEYWORD, lexan.PUNCT, lexan.NAME, lexan.PUNCT,
            lexan.NUMBER, lexan.PUNCT, lexan.PUNCT, lexan.NAME,
            lexan.PUNCT, lexan.STRING, lexan.PUNCT, lexan.PUNCT,
        ])
        previous = 0
        for token in tokens:
            self.assertLessEqual(previous, token.start)
            if token.kind == lexan.STRING:
                self.assertEqual(spelled[token.start], '"')
                self.assertEqual(spelled[token.end - 1], '"')
            else:
                self.assertEqual(
                    spelled[token.start:token.end], token.value)
            previous = token.end

    def test_keywords_are_told_apart_from_the_names_around_them(self):
        source = "if while return let IF Return True ifx for_each returning"
        self.assertEqual(body(source), [
            (lexan.KEYWORD, "if"),
            (lexan.KEYWORD, "while"),
            (lexan.KEYWORD, "return"),
            (lexan.KEYWORD, "let"),
            (lexan.NAME, "IF"),
            (lexan.NAME, "Return"),
            (lexan.NAME, "True"),
            (lexan.NAME, "ifx"),
            (lexan.NAME, "for_each"),
            (lexan.NAME, "returning"),
        ])

    def test_identifiers_keep_their_digits(self):
        source = "x1 count9 _9 a1b2"
        self.assertEqual(body(source), [
            (lexan.NAME, "x1"),
            (lexan.NAME, "count9"),
            (lexan.NAME, "_9"),
            (lexan.NAME, "a1b2"),
        ])
        self.assertEqual(places("k9 + v0"), [
            ("k9", 1, 1, 0, 2),
            ("+", 1, 4, 3, 4),
            ("v0", 1, 6, 5, 7),
        ])

    def test_a_dot_joins_a_number_only_when_a_digit_follows(self):
        self.assertEqual(body("1.5"), [(lexan.NUMBER, "1.5")])
        self.assertEqual(body("1."), [
            (lexan.NUMBER, "1"),
            (lexan.PUNCT, "."),
        ])
        self.assertEqual(body(".5"), [
            (lexan.PUNCT, "."),
            (lexan.NUMBER, "5"),
        ])
        self.assertEqual(body("1..2"), [
            (lexan.NUMBER, "1"),
            (lexan.PUNCT, ".."),
            (lexan.NUMBER, "2"),
        ])
        self.assertEqual(body("x.5"), [
            (lexan.NAME, "x"),
            (lexan.PUNCT, "."),
            (lexan.NUMBER, "5"),
        ])

    def test_the_longest_operator_wins(self):
        source = "a <= b >= c == d != e -> f :: g && h || i .. j"
        self.assertEqual(body(source), [
            (lexan.NAME, "a"),
            (lexan.PUNCT, "<="),
            (lexan.NAME, "b"),
            (lexan.PUNCT, ">="),
            (lexan.NAME, "c"),
            (lexan.PUNCT, "=="),
            (lexan.NAME, "d"),
            (lexan.PUNCT, "!="),
            (lexan.NAME, "e"),
            (lexan.PUNCT, "->"),
            (lexan.NAME, "f"),
            (lexan.PUNCT, "::"),
            (lexan.NAME, "g"),
            (lexan.PUNCT, "&&"),
            (lexan.NAME, "h"),
            (lexan.PUNCT, "||"),
            (lexan.NAME, "i"),
            (lexan.PUNCT, ".."),
            (lexan.NAME, "j"),
        ])
        self.assertEqual(body("a<b"), [
            (lexan.NAME, "a"),
            (lexan.PUNCT, "<"),
            (lexan.NAME, "b"),
        ])

    def test_string_values_have_their_escapes_decoded(self):
        self.assertEqual(body('"a\\nb"'), [(lexan.STRING, "a\nb")])
        self.assertEqual(body('"tab\\tend"'), [(lexan.STRING, "tab\tend")])
        self.assertEqual(body('"say \\"hi\\""'), [(lexan.STRING, 'say "hi"')])
        self.assertEqual(body('"back\\\\slash"'), [(lexan.STRING, "back\\slash")])
        self.assertEqual(body('"a\\nb" + c'), [
            (lexan.STRING, "a\nb"),
            (lexan.PUNCT, "+"),
            (lexan.NAME, "c"),
        ])
        self.assertEqual(places('"a\\nb" + c')[1:], [
            ("+", 1, 8, 7, 8),
            ("c", 1, 10, 9, 10),
        ])


class PositionTests(unittest.TestCase):
    """The place every token reports."""

    def test_line_breaks_move_line_and_column(self):
        self.assertEqual(places("a\nb"), [
            ("a", 1, 1, 0, 1),
            ("b", 2, 1, 2, 3),
        ])
        self.assertEqual(places("a\r\nb"), [
            ("a", 1, 1, 0, 1),
            ("b", 2, 1, 3, 4),
        ])
        self.assertEqual(places("a\rb"), [
            ("a", 1, 1, 0, 1),
            ("b", 2, 1, 2, 3),
        ])
        self.assertEqual(places("a\n\nb"), [
            ("a", 1, 1, 0, 1),
            ("b", 3, 1, 3, 4),
        ])
        self.assertEqual(places("ab cd\n  ef"), [
            ("ab", 1, 1, 0, 2),
            ("cd", 1, 4, 3, 5),
            ("ef", 2, 3, 8, 10),
        ])

    def test_positions_stay_right_across_comments(self):
        self.assertEqual(places("a /* x */ b"), [
            ("a", 1, 1, 0, 1),
            ("b", 1, 11, 10, 11),
        ])
        self.assertEqual(places("a # x\nb"), [
            ("a", 1, 1, 0, 1),
            ("b", 2, 1, 6, 7),
        ])
        self.assertEqual(places("a // x\nb"), [
            ("a", 1, 1, 0, 1),
            ("b", 2, 1, 7, 8),
        ])
        self.assertEqual(places("/* one\ntwo */ c"), [
            ("c", 2, 8, 14, 15),
        ])
        self.assertEqual(places("/* a\r\nb */ c"), [
            ("c", 2, 6, 11, 12),
        ])


class ErrorTests(unittest.TestCase):
    """The places a broken source is refused at."""

    def test_broken_sources_report_the_place_that_broke(self):
        with self.assertRaises(lexan.LexError) as caught:
            lexan.tokenize("value = 1\n   $ 2")
        self.assertEqual(
            (caught.exception.line, caught.exception.column,
             caught.exception.index),
            (2, 4, 13),
        )
        with self.assertRaises(lexan.LexError) as caught:
            lexan.tokenize('x = "abc\ny"')
        self.assertEqual(
            (caught.exception.line, caught.exception.column,
             caught.exception.index),
            (1, 5, 4),
        )
        with self.assertRaises(lexan.LexError) as caught:
            lexan.tokenize('x = "a\\q"')
        self.assertEqual(
            (caught.exception.line, caught.exception.column,
             caught.exception.index),
            (1, 7, 6),
        )
        with self.assertRaises(lexan.LexError) as caught:
            lexan.tokenize("x = 1 /* oops")
        self.assertEqual(
            (caught.exception.line, caught.exception.column,
             caught.exception.index),
            (1, 7, 6),
        )

    def test_the_token_run_ends_with_one_eof_token(self):
        tokens = scan("a + 1")
        last = tokens[-1]
        self.assertEqual(
            (last.kind, last.value, last.line, last.column,
             last.start, last.end),
            (lexan.EOF, "", 1, 6, 5, 5),
        )
        self.assertEqual([token.kind for token in scan("")], [lexan.EOF])
        self.assertEqual([token.kind for token in scan("   ")], [lexan.EOF])
        tail = scan("a\n")[-1]
        self.assertEqual(
            (tail.kind, tail.line, tail.column, tail.start, tail.end),
            (lexan.EOF, 2, 1, 2, 2),
        )
        self.assertEqual([token.kind for token in tokens[:-1]], [
            lexan.NAME,
            lexan.PUNCT,
            lexan.NUMBER,
        ])


if __name__ == "__main__":
    unittest.main()
