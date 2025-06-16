// Copyright (C) 2024-present The Rivet programming language. Use of this source code
// is governed by an MIT license that can be found in the LICENSE file.

module sema

import compiler.ast
import compiler.parser
import compiler.context

enum Stage {
	quiet
	symbol_reg    // srg_
	module_import // mi_
	symbol_res
	type_checking // tc_
	_end_
}

pub struct Sema {
pub:
	// Since modules can be imported using the `import` statement,
	// we need access to the parser to generate the corresponding
	// AST for each imported file.
	parser &parser.Parser
mut:
	ctx   &context.CContext = unsafe { nil }
	stage Stage

	file  &ast.File = unsafe { nil }
	sym   ast.Symbol
	scope &ast.Scope = unsafe { nil }
}

pub fn (mut sema Sema) analyze(ctx &context.CContext) {
	sema.ctx = ctx
	sema.ctx.log(@METHOD)
	sema.ctx.load_builtin_symbols()

	for i in int(Stage.quiet) + 1 .. int(Stage._end_) {
		sema.stage = unsafe { Stage(i) }
		sema.ctx.log('>> Stage: ${sema.stage}')
		for mut file in sema.ctx.files {
			sema.check_file(mut *file)
		}
	}
}

fn (mut sema Sema) check_file(mut file ast.File) {
	sema.file = file

	if sema.stage == .symbol_reg {
		sema.sym = sema.ctx.universe.find_or_add_module(file.mod_name) or {
			context.ic_error(err.msg())
		}
	}

	sema.file.scope = sema.sym.scope
	sema.scope = sema.file.scope

	sema.stmts(mut sema.file.stmts)

	if sema.ctx.code_has_errors() {
		return
	}
}

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
		ast.ExprStmt {
			sema.expr_stmt(mut stmt)
		}
		ast.WhileStmt {
			sema.while_stmt(mut stmt)
		}
		ast.VarStmt {
			sema.var_stmt(mut stmt)
		}
		ast.DeferStmt {
			sema.defer_stmt(mut stmt)
		}
		ast.EmptyStmt {
			context.error('empty statement detected', stmt.pos)
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

	match sema.stage {
		.symbol_reg {
			sema.sr_fn_stmt(mut stmt)
		}
		else {
			sema.scope = stmt.scope
			sema.stmts(mut stmt.stmts)
		}
	}
}

fn (mut sema Sema) expr_stmt(mut stmt ast.ExprStmt) {
	sema.expr(mut stmt.expr)
}

fn (mut sema Sema) while_stmt(mut stmt ast.WhileStmt) {
	if stmt.init_stmt != none {
		sema.var_stmt(mut stmt.init_stmt)
	}
	sema.expr(mut stmt.cond)
	if stmt.continue_expr != none {
		sema.expr(mut stmt.continue_expr)
	}
	sema.stmts(mut stmt.stmts)
}

fn (mut sema Sema) var_stmt(mut stmt ast.VarStmt) {
	match sema.stage {
		.symbol_reg {
			sema.sr_var_stmt(mut stmt)
		}
		else {
			// TODO
		}
	}
}

fn (mut sema Sema) defer_stmt(mut stmt ast.DeferStmt) {
	sema.stmts(mut stmt.stmts)
}

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
