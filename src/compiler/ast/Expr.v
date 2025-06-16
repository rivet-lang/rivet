// Copyright (C) 2024-present The Rivet programming language. Use of this source code
// is governed by an MIT license that can be found in the LICENSE file.

module ast

pub type Expr = EmptyExpr
	| ParenExpr
	| Ident
	| CharLiteral
	| IntegerLiteral
	| FloatLiteral
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
pub:
	pos FilePos
}

pub const empty_expr = Expr(EmptyExpr{})

pub struct ParenExpr {
pub:
	expr Expr
	pos  FilePos
}

pub struct Ident {
pub:
	name  string
	scope &Scope = unsafe { nil }
	pos   FilePos
}

pub struct IntegerLiteral {
pub:
	value string
	pos   FilePos
}

pub struct FloatLiteral {
pub:
	value string
	pos   FilePos
}

pub struct CharLiteral {
pub:
	value   string
	is_byte bool
	pos     FilePos
}

pub enum StringType {
	normal
	c_string
	bytes
	raw_string
}

pub struct StringLiteral {
pub:
	value        string
	literal_type StringType
	pos          FilePos
}

pub struct LoopControl {
pub:
	is_continue bool
	pos         FilePos
}

pub struct ReturnExpr {
pub:
	expr ?Expr
	pos  FilePos
}

pub struct BuiltinCallExpr {
pub:
	name string
	args []Expr
	pos  FilePos
}

pub struct CallExpr {
pub:
	left Expr
	args []Expr
	pos  FilePos
}

pub struct BlockExpr {
pub mut:
	stmts []Stmt
	expr  ?Expr
pub:
	pos FilePos
}

pub struct IfExpr {
pub:
	branches  []IfBranch
	is_inline bool
	pos       FilePos
}

pub struct IfBranch {
pub:
	cond ?Expr
	expr Expr
	pos  FilePos
}

pub struct MatchExpr {
pub:
	expr     Expr
	branches []MatchBranch
	pos      FilePos
}

pub struct MatchBranch {
pub:
	is_else bool
	cases   []Expr
	expr    Expr
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
pub:
	left  Expr
	op    AssignOp
	right Expr
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
pub:
	right Expr
	op    UnaryOp
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
pub:
	left  Expr
	op    BinaryOp
	right Expr
	pos   FilePos
}
