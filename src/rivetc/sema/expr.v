// Copyright (C) 2024 The Rivet programming language. Use of this source
// code is governed by an MIT license that can be found in the LICENSE file.

module sema

import rivetc.ast
import rivetc.ice
import rivetc.reporter

fn (mut sema Sema) expr(mut expr ast.Expr) ? {
	match mut expr {
		ast.BasicLiteral {
			sema.basic_literal(mut expr)?
		}
		ast.Ident {
			sema.ident_expr(mut expr)?
		}
		ast.BlockExpr {
			sema.block_expr(mut expr)?
		}
		ast.EmptyExpr {
			ice.ice('empty expression detected - ${expr.pos}')
		}
		else {}
	}
}

fn (mut sema Sema) basic_literal(mut expr ast.BasicLiteral) ? {
	if sema.stage != .type_check {
		return
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
}

fn (mut sema Sema) ident_expr(mut expr ast.Ident) ? {
	if sema.stage == .symbol_res {
		if sym := sema.find_symbol(expr.name) {
			expr.sym = sym
		} else {
			reporter.emit_error(err.msg(), expr.pos)
			return none
		}
		return
	}
}

fn (mut sema Sema) block_expr(mut expr ast.BlockExpr) ? {
	old_scope := sema.scope
	defer {
		sema.scope = old_scope
	}
	sema.scope = ast.Scope.new(sema.scope, sema.sym)
	sema.stmts(mut expr.stmts)
}
