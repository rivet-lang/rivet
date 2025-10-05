// Copyright (C) 2024 The Rivet programming language. Use of this source
// code is governed by an MIT license that can be found in the LICENSE file.

module sema

import rivetc.ast
import rivetc.parser
import rivetc.context
import rivetc.importer
import rivetc.reporter

enum Stage as u8 {
	quiet
	symbol_reg // srg_
	symbol_res
	type_check // tc_
	_end_
}

pub struct Sema {
mut:
	ctx   &context.Context = unsafe { nil }
	stage Stage

	// Since modules can be imported using the `mod` expression,
	// we need access to the parser to generate the corresponding
	// AST for each imported file.
	parser &parser.Parser     = unsafe { nil }
	imp    &importer.Importer = unsafe { nil }

	file  &ast.File = unsafe { nil }
	sym   ast.Symbol
	scope &ast.Scope = unsafe { nil }
}

@[inline]
pub fn new(ctx &context.Context) &Sema {
	return &Sema{
		ctx: ctx
	}
}

pub fn (mut sema Sema) analyze(p &parser.Parser, imp &importer.Importer) {
	sema.parser = unsafe { p }
	sema.imp = unsafe { imp }

	sema.ctx.log(@METHOD)
	sema.ctx.load_builtin_symbols()

	sema.check_files(mut sema.ctx.files)
}

fn (mut sema Sema) check_files(mut files []&ast.File) {
	for i in int(Stage.quiet) + 1 .. int(Stage._end_) {
		sema.stage = unsafe { Stage(i) }
		sema.ctx.log('>> Stage: ${sema.stage}')
		for mut file in files {
			sema.check_file(mut *file)
		}
	}
}

fn (mut sema Sema) check_file(mut file ast.File) {
	if file.stage == .new {
		// the file was added during semantic analysis, so we parse the file
		if !sema.parser.parse_file(mut file) {
			return
		}
	}

	sema.file = file

	if sema.stage == .symbol_reg {
		sema.sym = sema.ctx.universe.find_or_add_module(file.mod_name, file.is_pkg) or {
			reporter.ic_error(err.msg())
		}
	}

	sema.file.scope = sema.sym.scope
	sema.scope = sema.file.scope

	sema.stmts(mut sema.file.stmts)

	file.stage = .checked
	if sema.ctx.code_has_errors() {
		return
	}
}

fn (sema &Sema) find_symbol(name string) !ast.Symbol {
	match name {
		'true' {
			return sema.ctx.true_sym
		}
		'false' {
			return sema.ctx.false_sym
		}
		'null' {
			return sema.ctx.null_sym
		}
		else {
			// local
			if sym := sema.scope.lookup(name) {
				return sym
			}
			// global
			if sym := sema.ctx.universe.find(name) {
				return sym
			}
		}
	}
	return error('cannot find symbol `${name}` in this scope')
}
