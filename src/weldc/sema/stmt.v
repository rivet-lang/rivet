// Copyright (C) 2024 The Weld programming language. Use of this source
// code is governed by an MIT license that can be found in the LICENSE file.

module sema

import weldc.ast
import weldc.ice

fn (mut sema Sema) stmts(mut stmts []ast.Stmt) {
	for mut stmt in stmts {
		sema.stmt(mut stmt)
	}
}

fn (mut sema Sema) stmt(mut stmt ast.Stmt) {
	match mut stmt {
		ast.FnStmt {
			sema.fn_stmt(mut stmt)
		}
		ast.LetStmt {
			sema.let_stmt(mut stmt)
		}
		ast.WhileStmt {
			sema.while_stmt(mut stmt)
		}
		ast.ExprStmt {
			sema.expr_stmt(mut stmt)
		}
		ast.EmptyStmt {
			ice.ice('empty statement detected - ${stmt.pos}')
		}
	}
}

fn (mut sema Sema) fn_stmt(mut stmt ast.FnStmt) {
	old_scope := sema.scope
	old_sym := sema.sym
	defer {
		sema.scope = old_scope
		sema.sym = old_sym
	}

	sema.scope = stmt.scope

	for mut arg in stmt.args {
		if arg.default_expr != none {
			_ = sema.expr(mut arg.default_expr)
		}
	}
	sema.stmts(mut stmt.stmts)
}

fn (mut sema Sema) let_stmt(mut stmt ast.LetStmt) {
	if mut right := stmt.right {
		_ = sema.expr(mut right)
	}
}

fn (mut sema Sema) while_stmt(mut stmt ast.WhileStmt) {
	if stmt.init_stmt != none {
		sema.let_stmt(mut stmt.init_stmt)
	}
	_ = sema.expr(mut stmt.cond)
	if stmt.continue_expr != none {
		_ = sema.expr(mut stmt.continue_expr)
	}
	sema.stmts(mut stmt.stmts)
}

fn (mut sema Sema) expr_stmt(mut stmt ast.ExprStmt) {
	_ = sema.expr(mut stmt.expr)
}
