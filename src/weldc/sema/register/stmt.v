// Copyright (C) 2024 The Weld programming language. Use of this source
// code is governed by an MIT license that can be found in the LICENSE file.

module register

import weldc.ast
import weldc.reporter

fn (mut reg Register) stmts(mut stmts []ast.Stmt) {
	for mut stmt in stmts {
		reg.stmt(mut stmt)
	}
}

fn (mut reg Register) stmt(mut stmt ast.Stmt) {
	match mut stmt {
		ast.FnStmt {
			reg.fn_stmt(mut stmt)
		}
		ast.LetStmt {
			reg.let_stmt(mut stmt)
		}
		ast.WhileStmt {
			if stmt.init_stmt != none {
				reg.let_stmt(mut stmt.init_stmt)
			}
			reg.expr(mut stmt.cond)
			if stmt.continue_expr != none {
				reg.expr(mut stmt.continue_expr)
			}
			reg.stmts(mut stmt.stmts)
		}
		ast.ExprStmt {
			reg.expr(mut stmt.expr)
		}
	}
}

fn (mut reg Register) fn_stmt(mut stmt ast.FnStmt) {
	old_scope := reg.scope
	old_sym := reg.sym
	defer {
		reg.scope = old_scope
		reg.sym = old_sym
	}

	stmt.sym = &ast.Function{
		name: stmt.name
		args: stmt.args
		node: unsafe { stmt }
	}
	reg.sym = stmt.sym
	stmt.scope = ast.Scope.new(reg.scope, reg.sym)
	reg.scope.add_symbol(stmt.sym) or { reporter.emit_err(err.msg(), stmt.name_pos) }
	reg.scope = stmt.scope
	for mut arg in stmt.args {
		reg.scope.add_symbol(ast.Variable{
			name:     arg.name
			is_local: true
			is_arg:   true
			is_mut:   arg.is_mut
			is_ref:   arg.is_ref
			type:     arg.type
		}) or {
			mut d := reporter.err(err.msg(), arg.pos)
			d.add_note('inside function `${stmt.name}`')
			d.emit()
		}
		if arg.default_expr != none {
			reg.expr(mut arg.default_expr)
		}
	}
	reg.stmts(mut stmt.stmts)
}

fn (mut reg Register) let_stmt(mut stmt ast.LetStmt) {
	for mut left in stmt.lefts {
		reg.scope.add_symbol(left, lookup: left.is_local) or {
			mut d := reporter.err(err.msg(), left.pos)
			d.add_note('inside ${reg.sym.type_of()} `${reg.sym.name}`')
			d.emit()
		}
	}
	if mut right := stmt.right {
		reg.expr(mut right)
	}
}
