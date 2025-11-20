// Copyright (C) 2024 The Weld programming language. Use of this source
// code is governed by an MIT license that can be found in the LICENSE file.

module sema

import weldc.ast
import weldc.reporter

fn (mut sema Sema) expr(mut expr ast.Expr) ?ast.Type {
	return match mut expr {
		ast.BasicLiteral {
			sema.basic_literal(mut expr)
		}
		ast.Ident {
			sema.ident_expr(mut expr)
		}
		ast.BlockExpr {
			sema.block_expr(mut expr)
		}
		else {
			none
		}
	}
}

fn (mut sema Sema) basic_literal(mut expr ast.BasicLiteral) ?ast.Type {
	match expr.kind {
		.int {
			expr.type = sema.ctx.int_type
		}
		.float {
			expr.type = sema.ctx.float_type
		}
		.rune {
			expr.type = sema.ctx.rune_type
		}
		.byte {
			expr.type = sema.ctx.u8_type
		}
	}
	return expr.type
}

fn (mut sema Sema) ident_expr(mut expr ast.Ident) ?ast.Type {
	if sym := sema.find_symbol(expr.name) {
		expr.sym = sym
	} else {
		reporter.emit_err(err.msg(), expr.pos)
		return none
	}
	if mut expr.sym is ast.Variable && expr.sym.is_local {
		if expr.sym.pos > expr.pos {
			reporter.emit_err('variable `${expr.name}` used before declaration', expr.pos)
			return none
		}
	}
	return expr.type
}

fn (mut sema Sema) block_expr(mut expr ast.BlockExpr) ?ast.Type {
	old_scope := sema.scope
	defer {
		sema.scope = old_scope
	}
	sema.scope = ast.Scope.new(sema.scope, sema.sym)
	sema.stmts(mut expr.stmts)
	return expr.type
}
