// Copyright (C) 2024 The Rivet programming language. Use of this source
// code is governed by an MIT license that can be found in the LICENSE file.

module ast

pub type Expr = EmptyExpr
	| ParenExpr
	| Ident
	| BasicLiteral
	| StringLiteral
	| LoopControl
	| ReturnExpr
	| BuiltinCallExpr
	| CallExpr
	| IfExpr
	| MatchExpr
	| AssignExpr
	| BlockExpr
	| UnaryExpr
	| BinaryExpr

pub struct EmptyExpr {
pub mut:
	type Type
	pos  FilePos
}

pub const empty_expr = Expr(EmptyExpr{})

pub struct ParenExpr {
pub mut:
	expr Expr
	type Type
	pos  FilePos
}

pub struct Ident {
pub mut:
	name  string
	scope &Scope = unsafe { nil }
	type  Type
	pos   FilePos
}

pub enum BasicLiteralKind {
	int
	float
	char
	byte
}

pub struct BasicLiteral {
pub mut:
	value string
	kind  BasicLiteralKind
	type  Type
	pos   FilePos
}

pub enum StringKind {
	default
	c_string
	bytes
	raw_string
}

pub struct StringLiteral {
pub mut:
	value    string
	str_kind StringKind
	type     Type
	pos      FilePos
}

pub struct LoopControl {
pub mut:
	is_continue bool
	type        Type
	pos         FilePos
}

pub struct ReturnExpr {
pub mut:
	expr ?Expr
	type Type
	pos  FilePos
}

pub struct BuiltinCallExpr {
pub mut:
	name string
	args []Expr
	type Type
	pos  FilePos
}

pub struct CallExpr {
pub mut:
	left Expr
	args []Expr
	type Type
	pos  FilePos
}

pub struct BlockExpr {
pub mut:
	stmts []Stmt
	expr  ?Expr
	type  Type
	pos   FilePos
}

pub struct IfExpr {
pub mut:
	branches  []IfBranch
	is_inline bool
	type      Type
	pos       FilePos
}

pub struct IfBranch {
pub mut:
	cond ?Expr
	expr Expr
	type Type
	pos  FilePos
}

pub struct MatchExpr {
pub mut:
	expr     Expr
	branches []MatchBranch
	type     Type
	pos      FilePos
}

pub struct MatchBranch {
pub mut:
	is_else bool
	cases   []Expr
	expr    Expr
	type    Type
	pos     FilePos
}

@[inline]
pub fn (ib IfBranch) is_else() bool {
	return ib.cond == none
}

pub enum AssignOp {
	unknown
	assign         // =
	plus_assign    // +=
	minus_assign   // -=
	div_assign     // /=
	mul_assign     // *=
	xor_assign     // ^=
	mod_assign     // %=
	or_assign      // |=
	and_assign     // &=
	rshift_assign  // <<=
	lshift_assign  // >>=
	log_and_assign // &&=
	log_or_assign  // ||=
}

pub struct AssignExpr {
pub mut:
	left  Expr
	op    AssignOp
	right Expr
	type  Type
	pos   FilePos
}

pub enum UnaryOp {
	unknown
	amp     // &
	bang    // !
	bit_not // ~
	minus   // -
}

pub struct UnaryExpr {
pub mut:
	right Expr
	op    UnaryOp
	type  Type
	pos   FilePos
}

pub enum BinaryOp {
	unknown
	plus    // +
	minus   // -
	mul     // *
	div     // /
	mod     // %
	xor     // ^
	pipe    // |
	amp     // &
	log_and // &&
	log_or  // ||
	lshift  // <<
	rshift  // >>
	not_in  // !in
	not_is  // !is
	eq      // ==
	ne      // !=
	gt      // >
	lt      // <
	ge      // >=
	le      // <=
	or_else // ??
	kw_in   // !in
	kw_is   // !is
}

pub struct BinaryExpr {
pub mut:
	left  Expr
	op    BinaryOp
	right Expr
	type  Type
	pos   FilePos
}
