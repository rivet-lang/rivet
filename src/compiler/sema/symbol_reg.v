// Copyright (C) 2024-present The Rivet programming language. Use of this source code
// is governed by an MIT license that can be found in the LICENSE file.

module sema

import compiler.ast
import compiler.context

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
			is_let:   !arg.is_var
			is_ref:   arg.is_ref
			type:     arg.type
		}) or { context.error(err.msg(), arg.pos, context.note('inside function `${stmt.name}`')) }
	}
	sema.stmts(mut stmt.stmts)
}

fn (mut sema Sema) sr_var_stmt(mut stmt ast.VarStmt) {
	sema.scope.add_symbol(stmt.left, lookup: stmt.left.is_local) or {
		context.error(err.msg(), stmt.left.pos, context.note('inside ${sema.sym.type_of()} `${sema.sym.name}`'))
	}
}
