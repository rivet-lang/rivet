// Copyright (C) 2024 The Weld programming language. Use of this source
// code is governed by an MIT license that can be found in the LICENSE file.

module register

import weldc.ast
import weldc.context
import weldc.reporter

struct Register {
mut:
	ctx &context.Context = unsafe { nil }

	pkg   &ast.Package = unsafe { nil }
	file  &ast.File    = unsafe { nil }
	sym   ast.Symbol
	scope &ast.Scope = unsafe { nil }
}

pub fn register_symbols(ctx &context.Context) {
	mut reg := &Register{
		ctx: ctx
	}
	for mut pkg in reg.ctx.pkgs {
		ctx.log('${@FN}() for package `${pkg.name}`')
		reg.sym = reg.ctx.universe.find_or_add_module(pkg.name, true) or {
			reporter.ic_error(err.msg())
		}
		pkg.sym = &(reg.sym as ast.Module)
		reg.pkg = pkg
		for mut file in pkg.files {
			reg.check_file(mut file)
		}
	}
}

fn (mut reg Register) check_file(mut file ast.File) {
	reg.file = file

	if !file.is_pkg {
		old_sym := reg.sym
		defer(fn) { reg.sym = old_sym }
		reg.sym = reg.sym.scope.find_or_add_module(file.mod_name, false) or {
			reporter.ic_error(err.msg())
		}
	}

	reg.file.scope = reg.sym.scope
	reg.scope = reg.file.scope

	reg.stmts(mut reg.file.stmts)
}
