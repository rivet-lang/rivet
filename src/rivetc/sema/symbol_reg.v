// Copyright (C) 2024-present The Rivet programming language. Use of this source code
// is governed by an MIT license that can be found in the LICENSE file.

module sema

import rivetc.ast
import rivetc.context
import rivetc.reporter

fn (mut sema Sema) sr_fn_stmt(mut stmt ast.FnStmt) {
	stmt.sym = &ast.Function{
		name: stmt.name
		args: stmt.args
		node: unsafe { stmt }
	}
	sema.sym = stmt.sym
	stmt.scope = ast.Scope.new(sema.scope, sema.sym)
	sema.scope.add_symbol(stmt.sym) or { context.error(err.msg(), stmt.name_pos) }
	sema.scope = stmt.scope
	for arg in stmt.args {
		sema.scope.add_symbol(ast.Variable{
			name:     arg.name
			is_local: true
			is_arg:   true
			is_mut:   arg.is_mut
			is_ref:   arg.is_ref
			type:     arg.type
		}) or { context.error(err.msg(), arg.pos, context.note('inside function `${stmt.name}`')) }
	}
	sema.stmts(mut stmt.stmts)
}

fn (mut sema Sema) sr_let_stmt(mut stmt ast.LetStmt) {
	for mut left in stmt.lefts {
		sema.scope.add_symbol(left, lookup: left.is_local) or {
			context.error(err.msg(), left.pos, context.note('inside ${sema.sym.type_of()} `${sema.sym.name}`'))
			// mut d := reporter.diagnostic_with_pos(.err, err.msg(), left.pos)
			// d.add_note('inside ${sema.sym.type_of()} `${sema.sym.name}`')
			// reporter.report(d)
		}
	}
	reporter.print()
}
