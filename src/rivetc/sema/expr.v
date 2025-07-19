// Copyright (C) 2024 The Rivet programming language. Use of this source
// code is governed by an MIT license that can be found in the LICENSE file.

module sema

import rivetc.ast

fn (mut sema Sema) expr(mut expr ast.Expr) {
	match mut expr {
		ast.BlockExpr {
			sema.block_expr(mut expr)
		}
		else {}
	}
}

fn (mut sema Sema) block_expr(mut expr ast.BlockExpr) {
	old_scope := sema.scope
	defer {
		sema.scope = old_scope
	}
	sema.scope = ast.Scope.new(sema.scope, sema.sym)
	sema.stmts(mut expr.stmts)
}
