// Copyright (C) 2024 The Weld programming language. Use of this source
// code is governed by an MIT license that can be found in the LICENSE file.

module register

import weldc.ast
import weldc.context
import weldc.reporter

struct Register {
mut:
	ctx &context.Context = unsafe { nil }

	file  &ast.File = unsafe { nil }
	sym   ast.Symbol
	scope &ast.Scope = unsafe { nil }
}

pub fn register_symbols(ctx &context.Context, mut files []&ast.File) {
	ctx.log(@METHOD)
	mut reg := &Register{
		ctx: ctx
	}
	for mut file in files {
		reg.check_file(mut file)
	}
}

fn (mut reg Register) check_file(mut file ast.File) {
	reg.file = file

	reg.sym = reg.ctx.universe.find_or_add_module(file.mod_name, file.is_pkg) or {
		reporter.ic_error(err.msg())
	}

	reg.file.scope = reg.sym.scope
	reg.scope = reg.file.scope

	reg.stmts(mut reg.file.stmts)
}
