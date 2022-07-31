# Copyright (C) 2022 The Rivet Team. All rights reserved.
# Use of this source code is governed by an MIT license
# that can be found in the LICENSE file.

from enum import IntEnum as Enum, auto as auto_enum

class Kind(Enum):
	Unknown = auto_enum() # unknown
	EOF = auto_enum() # end of file
	DocComment = auto_enum() # doc-comment
	Name = auto_enum() # name
	Number = auto_enum() # number
	Char = auto_enum() # character
	String = auto_enum() # string
	Plus = auto_enum() # +
	Minus = auto_enum() # -
	Mult = auto_enum() # *
	Div = auto_enum() # /
	Mod = auto_enum() # %
	Inc = auto_enum() # ++
	Dec = auto_enum() # --
	Assign = auto_enum() # =
	PlusAssign = auto_enum() # +=
	MinusAssign = auto_enum() # -=
	MultAssign = auto_enum() # *=
	DivAssign = auto_enum() # /=
	ModAssign = auto_enum() # %=
	AmpAssign = auto_enum() # &=
	PipeAssign = auto_enum() # |=
	XorAssign = auto_enum() # ^=
	Eq = auto_enum() # ==
	Ne = auto_enum() # !=
	Lt = auto_enum() # <
	Gt = auto_enum() # >
	Le = auto_enum() # <=
	Ge = auto_enum() # >=
	Lshift = auto_enum() # <<
	Rshift = auto_enum() # >>
	Dot = auto_enum() # .
	DotDot = auto_enum() # ..
	Ellipsis = auto_enum() # ...
	Arrow = auto_enum() # =>
	Comma = auto_enum() # ,
	Colon = auto_enum() # :
	DoubleColon = auto_enum() # ::
	Semicolon = auto_enum() # ;
	Question = auto_enum() # ?
	Bang = auto_enum() # !
	Amp = auto_enum() # &
	Pipe = auto_enum() # |
	Xor = auto_enum() # ^
	BitNot = auto_enum() # ~
	Hash = auto_enum() # #
	Dollar = auto_enum() # $
	Lbrace = auto_enum() # {
	Rbrace = auto_enum() # }
	Lbracket = auto_enum() # [
	Rbracket = auto_enum() # ]
	Lparen = auto_enum() # (
	Rparen = auto_enum() # )

	# 6 literals, 38 keywords; Total: 44 keywords,
	# +1 extra keyword (`!is` = `!` + keyword).
	KeywordBegin = auto_enum()
	# ========== literals ==========
	KeyNone = auto_enum() # none
	KeyTrue = auto_enum() # true
	KeyFalse = auto_enum() # false
	KeySuper = auto_enum() # super
	KeySelf = auto_enum() # self
	KeySelfTy = auto_enum() # Self
	# ==============================

	# ========== keywords ==========
	KeyPkg = auto_enum() # pkg
	KeyPub = auto_enum() # pub
	KeyUsing = auto_enum() # using
	KeyAs = auto_enum() # as
	KeyConst = auto_enum() # const
	KeyStatic = auto_enum() # static
	KeyMod = auto_enum() # mod
	KeyExtern = auto_enum() # extern
	KeyTrait = auto_enum() # trait
	KeyUnion = auto_enum() # union
	KeyStruct = auto_enum() # struct
	KeyEnum = auto_enum() # enum
	KeyErrType = auto_enum() # errtype
	KeyType = auto_enum() # type
	KeyExtend = auto_enum() # extend
	KeyTest = auto_enum() # test
	KeyFn = auto_enum() # fn
	KeyLet = auto_enum() # let
	KeyMut = auto_enum() # mut
	KeyIf = auto_enum() # if
	KeyElif = auto_enum() # elif
	KeyElse = auto_enum() # else
	KeyMatch = auto_enum() # match
	KeyWhile = auto_enum() # while
	KeyFor = auto_enum() # for
	KeyContinue = auto_enum() # continue
	KeyBreak = auto_enum() # break
	KeyReturn = auto_enum() # return
	KeyRaise = auto_enum() # raise
	KeyGoto = auto_enum() # goto
	KeyAnd = auto_enum() # and
	KeyOr = auto_enum() # or
	KeyIn = auto_enum() # in
	KeyIs = auto_enum() # is
	KeyNotIs = auto_enum() # !is
	KeyUnsafe = auto_enum() # unsafe
	KeyOrElse = auto_enum() # orelse
	KeyCatch = auto_enum() # catch
	# ==============================

	KeywordEnd = auto_enum()

	def is_start_of_type(self):
		return self in (
		    Kind.Bang, Kind.Name, Kind.Lparen, Kind.Amp, Kind.Mult,
		    Kind.Lbracket, Kind.Question, Kind.KeySelf, Kind.KeySuper,
		    Kind.KeySelfTy
		)

	def is_assign(self):
		return self in (
		    Kind.Assign, Kind.PlusAssign, Kind.MinusAssign, Kind.MultAssign,
		    Kind.DivAssign, Kind.ModAssign, Kind.AmpAssign, Kind.PipeAssign,
		    Kind.XorAssign,
		)

	def is_relational(self):
		return self in (
		    Kind.Eq, Kind.Ne, Kind.Lt, Kind.Gt, Kind.Le, Kind.Ge, Kind.KeyIs,
		    Kind.KeyNotIs,
		)

	def is_overloadable_op(self):
		return self in OVERLOADABLE_OPERATORS

	def __repr__(self):
		return TOKEN_STRINGS[self] if self in TOKEN_STRINGS else "unknown"

	def __str__(self):
		return self.__repr__()

TOKEN_STRINGS = {
    Kind.Unknown: "unknown",
    Kind.EOF: "end of file",
    Kind.DocComment: "documentation comment",
    Kind.Name: "name",
    Kind.Number: "number",
    Kind.Char: "character",
    Kind.String: "string",
    Kind.Plus: "+",
    Kind.Minus: "-",
    Kind.Mult: "*",
    Kind.Div: "/",
    Kind.Mod: "%",
    Kind.Inc: "++",
    Kind.Dec: "--",
    Kind.Assign: "=",
    Kind.PlusAssign: "+=",
    Kind.MinusAssign: "-=",
    Kind.MultAssign: "*=",
    Kind.DivAssign: "/=",
    Kind.ModAssign: "%=",
    Kind.AmpAssign: "&=",
    Kind.PipeAssign: "|=",
    Kind.XorAssign: "^=",
    Kind.Eq: "==",
    Kind.Ne: "!=",
    Kind.Lt: "<",
    Kind.Gt: ">",
    Kind.Le: "<=",
    Kind.Ge: ">=",
    Kind.Lshift: "<<",
    Kind.Rshift: ">>",
    Kind.Dot: ".",
    Kind.DotDot: "..",
    Kind.Ellipsis: "...",
    Kind.Arrow: "=>",
    Kind.Comma: ",",
    Kind.Colon: ":",
    Kind.DoubleColon: "::",
    Kind.Semicolon: ";",
    Kind.Question: "?",
    Kind.Bang: "!",
    Kind.Amp: "&",
    Kind.Pipe: "|",
    Kind.Xor: "^",
    Kind.BitNot: "~",
    Kind.Hash: "#",
    Kind.Dollar: "$",
    Kind.Lbrace: "{",
    Kind.Rbrace: "}",
    Kind.Lbracket: "[",
    Kind.Rbracket: "]",
    Kind.Lparen: "(",
    Kind.Rparen: ")",

    # ========== literals ==========
    Kind.KeyNone: "none",
    Kind.KeyTrue: "true",
    Kind.KeyFalse: "false",
    Kind.KeySuper: "super",
    Kind.KeySelf: "self",
    # ==============================

    # ========== keywords ==========
    Kind.KeySelfTy: "Self",
    Kind.KeyPkg: "pkg",
    Kind.KeyPub: "pub",
    Kind.KeyUsing: "using",
    Kind.KeyAs: "as",
    Kind.KeyConst: "const",
    Kind.KeyStatic: "static",
    Kind.KeyMod: "mod",
    Kind.KeyExtern: "extern",
    Kind.KeyTrait: "trait",
    Kind.KeyUnion: "union",
    Kind.KeyStruct: "struct",
    Kind.KeyEnum: "enum",
    Kind.KeyErrType: "errtype",
    Kind.KeyType: "type",
    Kind.KeyExtend: "extend",
    Kind.KeyTest: "test",
    Kind.KeyFn: "fn",
    Kind.KeyLet: "let",
    Kind.KeyMut: "mut",
    Kind.KeyIf: "if",
    Kind.KeyElif: "elif",
    Kind.KeyElse: "else",
    Kind.KeyMatch: "match",
    Kind.KeyWhile: "while",
    Kind.KeyFor: "for",
    Kind.KeyContinue: "continue",
    Kind.KeyBreak: "break",
    Kind.KeyReturn: "return",
    Kind.KeyRaise: "raise",
    Kind.KeyGoto: "goto",
    Kind.KeyAnd: "and",
    Kind.KeyOr: "or",
    Kind.KeyIn: "in",
    Kind.KeyIs: "is",
    Kind.KeyNotIs: "!is",
    Kind.KeyUnsafe: "unsafe",
    Kind.KeyOrElse: "orelse",
    Kind.KeyCatch: "catch",
    # ==============================
}

OVERLOADABLE_OPERATORS = (
    Kind.Plus, Kind.Minus, Kind.Mult, Kind.Div, Kind.Mod, Kind.Eq, Kind.Ne,
    Kind.Lt, Kind.Gt, Kind.Le, Kind.Ge
)

def generate_overloadable_op_map():
	map = {}
	for op in OVERLOADABLE_OPERATORS:
		if op == Kind.Plus: gname = "_add_"
		elif op == Kind.Minus: gname = "_sub_"
		elif op == Kind.Mult: gname = "_mult_"
		elif op == Kind.Div: gname = "_div_"
		elif op == Kind.Mod: gname = "_mod_"
		elif op == Kind.Eq: gname = "_eq_"
		elif op == Kind.Ne: gname = "_ne_"
		elif op == Kind.Lt: gname = "_lt_"
		elif op == Kind.Gt: gname = "_gt_"
		elif op == Kind.Le: gname = "_le_"
		elif op == Kind.Ge: gname = "_ge_"
		else: assert False
		map[str(op)] = gname
	return map

OVERLOADABLE_OPERATORS_STR = generate_overloadable_op_map()

def generate_keyword_map():
	res = {}
	for i, k in enumerate(Kind):
		if i > Kind.KeywordBegin - 1 and i < Kind.KeywordEnd - 1:
			res[str(k)] = k
	return res

KEYWORDS = generate_keyword_map()

def lookup(lit):
	return KEYWORDS[lit] if lit in KEYWORDS else Kind.Name

def is_key(lit):
	return lit in KEYWORDS

class Pos:
	def __init__(self, file, line, col, pos):
		self.file = file
		self.line = line
		self.col = col
		self.pos = pos

	def __repr__(self):
		return f"{self.file}:{self.line+1}:{self.col}"

	def __str__(self):
		return self.__repr__()

class Token:
	def __init__(self, lit, kind, pos):
		self.lit = lit
		self.kind = kind
		self.pos = pos

	def __str__(self):
		string = str(self.kind)
		if not string[0].isalpha():
			return f"token `{string}`"
		if is_key(self.lit):
			string = "keyword"
		if self.lit != "" and self.kind != Kind.DocComment:
			string += f" `{self.lit}`"
		return string

	def __repr__(self):
		return f'rivet.Token(kind: "{self.kind}", lit: "{self.lit}", pos: "{self.pos}")'
