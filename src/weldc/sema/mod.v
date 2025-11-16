// Copyright (C) 2024 The Weld programming language. Use of this source
// code is governed by an MIT license that can be found in the LICENSE file.

module sema

import weldc.ast
import weldc.parser
import weldc.context
import weldc.importer
import weldc.sema.register

pub struct Sema {
mut:
	ctx &context.Context = unsafe { nil }

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
	register.register_symbols(sema.ctx, mut files)
	if sema.ctx.code_has_errors() {
		return
	}
	for mut file in files {
		sema.check_file(mut file)
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
	sema.scope = sema.file.scope
	sema.stmts(mut sema.file.stmts)
	file.stage = .checked
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
