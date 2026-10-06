# lexan

A lexer kernel for a small C-like language, built on the Python standard
library only.  It reads a whole piece of source text in one go and hands back
a flat list of tokens; it never touches the disk, the network, the clock or
the random number generator.  The kernel lives in `lexan/core.py`.

## Tokens

- `name` — a letter or an underscore followed by letters, digits and
  underscores.
- `keyword` — one of `KEYWORDS`, matched case sensitively, so `if` is a
  keyword while `IF` is a name.
- `number` — a run of digits; a dot belongs to the number only when a digit
  follows it, so `1.5` is one number while `1.` is a number and a dot.
- `string` — a double quoted literal; `value` holds the decoded text
  (`\n`, `\t`, `\r`, `\"`, `\\`), while the span covers the quotes.
- `punct` — one of `OPERATORS`, the longest match winning, so `<=` is one
  token rather than `<` followed by `=`.
- `eof` — the end of the source; every run of tokens ends with exactly one,
  sitting right after the last character.

## Trivia and positions

Blanks are skipped, `#` and `//` skip the rest of the line, and `/* ... */`
skips everything up to the closing pair.  Token `line` and `column` are
counted from one; a newline, a lone carriage return and a CRLF pair each
count as one line break.  Every token also carries the half open span
`[start, end)` of the source it was read from.

A character no rule accepts, a string that is never closed and a block
comment that is never closed all raise `LexError`, carrying the line, the
column and the index of the character the trouble starts at.

## Directory

- `lexan/core.py` — the scanner, the token type and the error type
- `tests/test_core.py` — behaviour tests

## Running the tests

From the project root:

    python3 -m unittest discover -s tests -v
