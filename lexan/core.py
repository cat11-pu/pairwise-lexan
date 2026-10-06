r"""A lexer kernel for a small C-like language (standard library only).

The kernel reads a whole piece of source text and hands back one flat list of
tokens.  It touches no disk, no network, no clock and no random number
generator: the same text always produces the same tokens.

Kinds
-----

``name``     a letter or an underscore followed by letters, digits and
             underscores.
``keyword``  a word of ``KEYWORDS``; the words are compared case sensitively,
             so ``if`` is a keyword while ``IF`` is a name.
``number``   a run of digits; a dot belongs to the number only when a digit
             follows it, so ``1.5`` is one token while ``1.`` is a number and
             a dot.
``string``   a double quoted literal; ``value`` holds the decoded text, so
             the value of ``"a\nb"`` holds a line break; the span of the
             token covers the quotes as well.
``punct``    one of ``OPERATORS``, the longest match winning, so ``<=`` is one
             token rather than ``<`` followed by ``=``.
``eof``      the end of the source; every run of tokens ends with exactly one.

Trivia
------

Blanks are skipped, ``#`` and ``//`` skip the rest of the line, and
``/* ... */`` skips everything up to the closing pair.  A marker inside a
string literal is text, not the start of a comment.

Positions
---------

``line`` and ``column`` are counted from one.  A newline, a lone carriage
return and a CRLF pair each count as one line break.  A line break inside a
comment moves the position like any other character.  Every token carries the
half open span ``[start, end)`` of the source it was read from, so that
``source[token.start:token.end]`` is the text of the token.
"""

#: Words that are tokens of their own; a name is any other word.
KEYWORDS = frozenset((
    "break", "continue", "elif", "else", "false", "for", "func", "if",
    "let", "null", "return", "true", "var", "while",
))

#: Punctuation and operators; the longer spelling wins where both fit.
OPERATORS = (
    "->", "::", "..", "<=", ">=", "==", "!=", "&&", "||",
    "(", ")", "{", "}", "[", "]", ",", ";", ":", ".",
    "?", "+", "-", "*", "/", "%", "<", ">", "=", "!",
)

#: The kinds a token can carry.
NAME = "name"
KEYWORD = "keyword"
NUMBER = "number"
STRING = "string"
PUNCT = "punct"
EOF = "eof"

DIGITS = frozenset("0123456789")
LETTERS = frozenset("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ")
NAME_START = LETTERS | frozenset("_")
NAME_BODY = NAME_START | DIGITS
#: Characters that separate tokens and carry no token of their own.
BLANKS = frozenset(" \t\f\v\r\n")
ESCAPES = {'"': '"', "\\": "\\", "n": "\n", "t": "\t", "r": "\r"}


class LexError(Exception):
    """Raised when the source cannot be read as a token stream.

    ``line``, ``column`` and ``index`` point at the character the trouble
    starts at, so a caller can show the reader the place in the source.
    """

    def __init__(self, message, line, column, index):
        super().__init__("%s at line %d column %d" % (message, line, column))
        self.message = message
        self.line = line
        self.column = column
        self.index = index


class Token:
    """One token: its kind, its value and where it sits in the source."""

    __slots__ = ("kind", "value", "line", "column", "start", "end")

    def __init__(self, kind, value, line, column, start, end):
        self.kind = kind
        self.value = value
        self.line = line
        self.column = column
        self.start = start
        self.end = end

    def __eq__(self, other):
        if isinstance(other, Token):
            return self.as_tuple() == other.as_tuple()
        return NotImplemented

    def __hash__(self):
        return hash(self.as_tuple())

    def __repr__(self):
        return "Token(%r, %r, line=%r, column=%r, start=%r, end=%r)" % (
            self.kind, self.value, self.line, self.column, self.start, self.end)

    def as_tuple(self):
        """The token as a plain tuple, handy for comparisons."""
        return (self.kind, self.value, self.line, self.column, self.start, self.end)


class _Scanner:
    """Walks the source once, remembering where the cursor sits."""

    def __init__(self, source):
        self.source = source
        self.size = len(source)
        self.index = 0
        self.line = 1
        self.column = 1

    def error(self, message, line=None, column=None, index=None):
        """Build a LexError; without a place of its own it points at the cursor."""
        if line is None:
            line, column, index = self.line, self.column, self.index
        return LexError(message, line, column, index)

    def advance(self):
        """Step over the character at the cursor, moving line and column."""
        ch = self.source[self.index]
        self.index += 1
        if ch == "\r" or ch == "\n":
            self.line += 1
            self.column = 1
        else:
            self.column += 1

    def skip_trivia(self):
        """Step over blanks and comments up to the next token."""
        while self.index < self.size:
            ch = self.source[self.index]
            if ch in BLANKS:
                self.advance()
                continue
            if ch == "#":
                self.skip_line()
                continue
            if ch == "/" and self.index + 1 < self.size:
                follower = self.source[self.index + 1]
                if follower == "/":
                    self.skip_line()
                    continue
                if follower == "*":
                    self.skip_block()
                    continue
            return

    def skip_line(self):
        """Step over the rest of the line, leaving the line break alone."""
        while self.index < self.size and self.source[self.index] not in "\r\n":
            self.advance()

    def skip_block(self):
        """Step over a block comment the cursor sits at the start of."""
        line, column, start = self.line, self.column, self.index
        self.advance()
        self.advance()
        while self.index < self.size:
            if (self.source[self.index] == "*"
                    and self.index + 1 < self.size
                    and self.source[self.index + 1] == "/"):
                self.advance()
                self.advance()
                return
            self.index += 1
        raise self.error("block comment is never closed", line, column, start)

    def next_token(self):
        """Read the token at the cursor and step past it."""
        self.skip_trivia()
        start, line, column = self.index, self.line, self.column
        if self.index >= self.size:
            return Token(EOF, "", line, column, start, start)
        ch = self.source[self.index]
        if ch in NAME_START:
            return self.read_name(start, line, column)
        if ch in DIGITS:
            return self.read_number(start, line, column)
        if ch == '"':
            return self.read_string(start, line, column)
        return self.read_punct(start, line, column)

    def read_name(self, start, line, column):
        """Read a name; the keyword table decides what kind it gets."""
        self.advance()
        while self.index < self.size and self.source[self.index] in NAME_START:
            self.advance()
        value = self.source[start:self.index]
        kind = KEYWORD if value.lower() in KEYWORDS else NAME
        return Token(kind, value, line, column, start, self.index)

    def read_number(self, start, line, column):
        """Read a number, its digits and its fraction if it has one."""
        while self.index < self.size and self.source[self.index] in DIGITS:
            self.advance()
        if self.index < self.size and self.source[self.index] == ".":
            self.advance()
            while self.index < self.size and self.source[self.index] in DIGITS:
                self.advance()
        return Token(NUMBER, self.source[start:self.index], line, column, start, self.index)

    def read_string(self, start, line, column):
        """Read a string literal, decoding the escapes on the way."""
        self.advance()
        decoded = []
        while True:
            if self.index >= self.size:
                raise self.error("string is never closed", line, column, start)
            ch = self.source[self.index]
            if ch == "\n" or ch == "\r":
                raise self.error("string is never closed", line, column, start)
            if ch == '"':
                self.advance()
                break
            if ch == "\\":
                escape_line, escape_column = self.line, self.column
                escape_start = self.index
                self.advance()
                if self.index >= self.size:
                    raise self.error("string is never closed", line, column, start)
                letter = self.source[self.index]
                if letter not in ESCAPES:
                    raise self.error(
                        "unknown escape %r" % (letter,),
                        escape_line, escape_column, escape_start)
                decoded.append(letter)
                self.advance()
                continue
            decoded.append(ch)
            self.advance()
        return Token(STRING, "".join(decoded), line, column, start, self.index)

    def read_punct(self, start, line, column):
        """Read one punctuation token."""
        for size in (1, 2):
            candidate = self.source[self.index:self.index + size]
            if len(candidate) == size and candidate in OPERATORS:
                for _ in range(size):
                    self.advance()
                return Token(PUNCT, candidate, line, column, start, self.index)
        raise self.error("unexpected character %r" % (self.source[self.index],))


def tokenize(source):
    """Read a whole source text into a list of tokens that ends with EOF."""
    if not isinstance(source, str):
        raise TypeError("a source must be text, not %s" % type(source).__name__)
    scanner = _Scanner(source)
    tokens = []
    while True:
        token = scanner.next_token()
        if token.kind == EOF:
            return tokens
        tokens.append(token)
