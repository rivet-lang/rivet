// Copyright (C) 2024 The Weld programming language. Use of this source
// code is governed by an MIT license that can be found in the LICENSE file.

module sema

import weldc.ast
import weldc.ice
import weldc.reporter

fn (mut sema Sema) expr(mut expr ast.Expr) bool {
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
		ast.EmptyExpr {
			ice.ice('empty expression detected - ${expr.pos}')
		}
		else {
			false
		}
	}
}

fn (mut sema Sema) basic_literal(mut expr ast.BasicLiteral) bool {
	if sema.stage != .type_check {
		return true
	}
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
	return true
}

fn (mut sema Sema) ident_expr(mut expr ast.Ident) bool {
	if sema.stage == .symbol_res {
		if sym := sema.find_symbol(expr.name) {
			expr.sym = sym
		} else {
			reporter.emit_err(err.msg(), expr.pos)
			return false
		}
		return true
	}
	return true
}

fn (mut sema Sema) block_expr(mut expr ast.BlockExpr) bool {
	old_scope := sema.scope
	defer {
		sema.scope = old_scope
	}
	sema.scope = ast.Scope.new(sema.scope, sema.sym)
	sema.stmts(mut expr.stmts)
	return true
}
