// Copyright (C) 2024 The Weld programming language. Use of this source
// code is governed by an MIT license that can be found in the LICENSE file.

module ast

pub type Stmt = FnStmt | ExprStmt | LetStmt | WhileStmt

pub struct ExprStmt {
pub:
	tags Tags
pub mut:
	expr Expr
}

pub struct FnStmt {
pub:
	tags        Tags
	is_pub      bool
	name        string
	name_pos    FilePos
	args        []FnArg
	return_type Type
	has_body    bool
pub mut:
	stmts []Stmt
	sym   &Function = unsafe { nil }
	scope &Scope    = unsafe { nil }
}

pub struct FnArg {
pub:
	name     string
	name_pos FilePos
	is_mut   bool
	is_ref   bool
	pos      FilePos
pub mut:
	type         Type
	default_expr ?Expr
}

pub struct WhileStmt {
pub:
	tags Tags
pub mut:
	init_stmt     ?LetStmt
	cond          Expr
	continue_expr ?Expr
	stmts         []Stmt
}

pub struct LetStmt {
pub:
	tags   Tags
	is_pub bool
	pos    FilePos
pub mut:
	lefts []Variable
	right ?Expr
}
