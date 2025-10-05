// Copyright (C) 2024 The Rivet programming language. Use of this source
// code is governed by an MIT license that can be found in the LICENSE file.

module sema

import rivetc.ast
import rivetc.ice
import rivetc.reporter

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

	if sema.stage == .symbol_reg {
		sema.register_function(mut stmt)
		return
	}

	sema.scope = stmt.scope

	for arg in stmt.args {
		if mut default_expr := arg.default_expr {
			sema.expr(mut default_expr) or { reporter.err(err.msg(), arg.pos).report() }
		}
	}
	sema.stmts(mut stmt.stmts)
}

fn (mut sema Sema) let_stmt(mut stmt ast.LetStmt) {
	if sema.stage == .symbol_reg {
		sema.register_variables(mut stmt)
		return
	}
	if mut right := stmt.right {
		sema.expr(mut right) or { reporter.err(err.msg(), right.pos).report() }
	}
}

fn (mut sema Sema) while_stmt(mut stmt ast.WhileStmt) {
	if stmt.init_stmt != none {
		sema.let_stmt(mut stmt.init_stmt)
	}
	sema.expr(mut stmt.cond) or { return }
	if stmt.continue_expr != none {
		sema.expr(mut stmt.continue_expr) or { return }
	}
	sema.stmts(mut stmt.stmts)
}

fn (mut sema Sema) expr_stmt(mut stmt ast.ExprStmt) {
	sema.expr(mut stmt.expr) or { return }
}
