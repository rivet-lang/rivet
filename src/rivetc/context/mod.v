// Copyright (C) 2024 The Rivet programming language. Use of this source
// code is governed by an MIT license that can be found in the LICENSE file.

@[has_globals]
module context

import term
import rivetc.ast
import rivetc.reporter

@[heap; noinit]
pub struct Context {
pub mut:
	options Options

	// Universe is the main scope of all symbols that both the user and the compiler define.
	universe &ast.Scope = ast.Scope.new(unsafe { nil }, none)

	// Name of the main package with which the compiler was called.
	root_name string

	// Rivet source code files, sorted by package.
	files []&ast.File

	// Types.
	// NOTE: All of these types are initialized in the semantic analyzer,
	// see `Sema.analyze`.
	untyped    ast.Type
	void_type  ast.Type
	null_type  ast.Type
	never_type ast.Type

	i8_type  ast.Type
	i16_type ast.Type
	i32_type ast.Type
	i64_type ast.Type
	int_type ast.Type

	u8_type   ast.Type
	u16_type  ast.Type
	u32_type  ast.Type
	u64_type  ast.Type
	uint_type ast.Type

	f32_type   ast.Type
	f64_type   ast.Type
	float_type ast.Type

	bool_type ast.Type
	rune_type ast.Type
}

@[inline]
pub fn new() &Context {
	return &Context{}
}

pub fn (mut ctx Context) load_builtin_symbols() {
	ctx.load_universe()
	ctx.load_primitive_types()
	ctx.load_builtin_constants()
}

pub fn (mut ctx Context) load_universe() {
	ctx.universe.add_symbol(ast.TypeSym{
		name: 'i8'
		kind: .i8
	}) or { reporter.ic_error(err.msg()) }
	ctx.universe.add_symbol(ast.TypeSym{
		name: 'i16'
		kind: .i16
	}) or { reporter.ic_error(err.msg()) }
	ctx.universe.add_symbol(ast.TypeSym{
		name: 'i32'
		kind: .i32
	}) or { reporter.ic_error(err.msg()) }
	ctx.universe.add_symbol(ast.TypeSym{
		name: 'i64'
		kind: .i64
	}) or { reporter.ic_error(err.msg()) }
	ctx.universe.add_symbol(ast.TypeSym{
		name: 'int'
		kind: .int
	}) or { reporter.ic_error(err.msg()) }

	ctx.universe.add_symbol(ast.TypeSym{
		name: 'u8'
		kind: .u8
	}) or { reporter.ic_error(err.msg()) }
	ctx.universe.add_symbol(ast.TypeSym{
		name: 'u16'
		kind: .u16
	}) or { reporter.ic_error(err.msg()) }
	ctx.universe.add_symbol(ast.TypeSym{
		name: 'u32'
		kind: .u32
	}) or { reporter.ic_error(err.msg()) }
	ctx.universe.add_symbol(ast.TypeSym{
		name: 'u64'
		kind: .u64
	}) or { reporter.ic_error(err.msg()) }
	ctx.universe.add_symbol(ast.TypeSym{
		name: 'uint'
		kind: .uint
	}) or { reporter.ic_error(err.msg()) }

	ctx.universe.add_symbol(ast.TypeSym{
		name: 'f32'
		kind: .f32
	}) or { reporter.ic_error(err.msg()) }
	ctx.universe.add_symbol(ast.TypeSym{
		name: 'f64'
		kind: .f64
	}) or { reporter.ic_error(err.msg()) }
	ctx.universe.add_symbol(ast.TypeSym{
		name: 'float'
		kind: .float
	}) or { reporter.ic_error(err.msg()) }

	ctx.universe.add_symbol(ast.TypeSym{
		name: 'bool'
		kind: .bool
	}) or { reporter.ic_error(err.msg()) }
	ctx.universe.add_symbol(ast.TypeSym{
		name: 'rune'
		kind: .rune
	}) or { reporter.ic_error(err.msg()) }
}

pub fn (mut ctx Context) load_primitive_types() {
	ctx.untyped = ast.Untyped{}
	ctx.void_type = ast.VoidType{}
	ctx.never_type = ast.NeverType{}
	ctx.null_type = ast.NullType{}

	ctx.i8_type = ast.SimpleType{
		sym: ctx.universe.find('i8') or { reporter.ic_error(err.msg()) }
	}
	ctx.i16_type = ast.SimpleType{
		sym: ctx.universe.find('i16') or { reporter.ic_error(err.msg()) }
	}
	ctx.i32_type = ast.SimpleType{
		sym: ctx.universe.find('i32') or { reporter.ic_error(err.msg()) }
	}
	ctx.i64_type = ast.SimpleType{
		sym: ctx.universe.find('i64') or { reporter.ic_error(err.msg()) }
	}
	ctx.int_type = ast.SimpleType{
		sym: ctx.universe.find('int') or { reporter.ic_error(err.msg()) }
	}

	ctx.u8_type = ast.SimpleType{
		sym: ctx.universe.find('u8') or { reporter.ic_error(err.msg()) }
	}
	ctx.u16_type = ast.SimpleType{
		sym: ctx.universe.find('u16') or { reporter.ic_error(err.msg()) }
	}
	ctx.u32_type = ast.SimpleType{
		sym: ctx.universe.find('u32') or { reporter.ic_error(err.msg()) }
	}
	ctx.u64_type = ast.SimpleType{
		sym: ctx.universe.find('u64') or { reporter.ic_error(err.msg()) }
	}
	ctx.uint_type = ast.SimpleType{
		sym: ctx.universe.find('uint') or { reporter.ic_error(err.msg()) }
	}

	ctx.f32_type = ast.SimpleType{
		sym: ctx.universe.find('f32') or { reporter.ic_error(err.msg()) }
	}
	ctx.f64_type = ast.SimpleType{
		sym: ctx.universe.find('f64') or { reporter.ic_error(err.msg()) }
	}

	ctx.bool_type = ast.SimpleType{
		sym: ctx.universe.find('bool') or { reporter.ic_error(err.msg()) }
	}
	ctx.rune_type = ast.SimpleType{
		sym: ctx.universe.find('rune') or { reporter.ic_error(err.msg()) }
	}
}

pub fn (mut ctx Context) load_builtin_constants() {
	ctx.universe.add_symbol(ast.Variable{
		name: 'true'
		type: ctx.bool_type
	}) or { reporter.ic_error(err.msg()) }
	ctx.universe.add_symbol(ast.Variable{
		name: 'false'
		type: ctx.bool_type
	}) or { reporter.ic_error(err.msg()) }
	ctx.universe.add_symbol(ast.Variable{
		name: 'null'
		type: ctx.null_type
	}) or { reporter.ic_error(err.msg()) }
}

@[inline]
pub fn (ctx &Context) code_has_errors() bool {
	return reporter_.errors > 0
}

pub fn (ctx &Context) log(msg string) {
	if ctx.options.is_verbose {
		println(term.bold(term.green('>> ')) + msg)
	}
}

pub fn (ctx &Context) abort_if_errors() {
	if ctx.code_has_errors() {
		reporter.print()
		reason := if reporter_.errors == 1 {
			'aborting due to previous error'
		} else {
			'aborting due to ${reporter_.errors} previous errors'
		}
		reporter.ic_error('could not compile `${ctx.root_name}` module, ${reason}')
	}
}
