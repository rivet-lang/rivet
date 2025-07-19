// Copyright (C) 2024 The Rivet programming language. Use of this source
// code is governed by an MIT license that can be found in the LICENSE file.

module sema

import rivetc.ast
import rivetc.reporter

fn (mut sema Sema) register_function(mut stmt ast.FnStmt) {
	stmt.sym = &ast.Function{
		name: stmt.name
		args: stmt.args
		node: unsafe { stmt }
	}
	sema.sym = stmt.sym
	stmt.scope = ast.Scope.new(sema.scope, sema.sym)
	sema.scope.add_symbol(stmt.sym) or { reporter.err(err.msg(), stmt.name_pos).report() }
	sema.scope = stmt.scope
	for arg in stmt.args {
		sema.scope.add_symbol(ast.Variable{
			name:     arg.name
			is_local: true
			is_arg:   true
			is_mut:   arg.is_mut
			is_ref:   arg.is_ref
			type:     arg.type
		}) or {
			mut d := reporter.err(err.msg(), arg.pos)
			d.add_note('inside function `${stmt.name}`')
			d.report()
		}
	}
	sema.stmts(mut stmt.stmts)
}

fn (mut sema Sema) register_variables(mut stmt ast.LetStmt) {
	for mut left in stmt.lefts {
		sema.scope.add_symbol(left, lookup: left.is_local) or {
			mut d := reporter.err(err.msg(), left.pos)
			d.add_note('inside ${sema.sym.type_of()} `${sema.sym.name}`')
			d.report()
		}
	}
}
