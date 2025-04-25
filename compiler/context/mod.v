// Copyright (C) 2024-present The Rivet programming language. Use of this source code
// is governed by an MIT license that can be found in the LICENSE file.

@[has_globals]
module context

import compiler.ast

__global stack = []&CContext{}

pub fn push(ctx &CContext) {
	unsafe {
		mut s := &stack
		s << ctx
	}
}

pub fn get() &CContext {
	if stack == [] {
		panic('context.get: empty CContext stack')
	}
	return stack.last()
}

pub fn pop() {
	if stack == [] {
		panic('context.pop: empty CContext stack')
	}
	unsafe {
		mut s := &stack
		_ = s.pop()
	}
}

@[heap]
pub struct CContext {
pub mut:
	options Options
	report  Report

	universe &ast.Scope = ast.Scope.new(unsafe { nil }, none)

	root_file &ast.File = unsafe { nil }
	files     []&ast.File

	// Types.
	// NOTE: All of these types are initialized in the semantic analyzer,
	// see `Sema.analyze`.
	void_type  ast.Type
	none_type  ast.Type
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

	f32_type ast.Type
	f64_type ast.Type

	bool_type ast.Type
	rune_type ast.Type
}

pub fn (mut ctx CContext) load_builtin_symbols() {
	ctx.load_universe()
	ctx.load_primitive_types()
}

pub fn (mut ctx CContext) load_universe() {
	ctx.universe.add_symbol(ast.TypeSym{
		name: 'i8'
		kind: .i8
	}) or { ic_error(err.msg()) }
	ctx.universe.add_symbol(ast.TypeSym{
		name: 'i16'
		kind: .i16
	}) or { ic_error(err.msg()) }
	ctx.universe.add_symbol(ast.TypeSym{
		name: 'i32'
		kind: .i32
	}) or { ic_error(err.msg()) }
	ctx.universe.add_symbol(ast.TypeSym{
		name: 'i64'
		kind: .i64
	}) or { ic_error(err.msg()) }
	ctx.universe.add_symbol(ast.TypeSym{
		name: 'int'
		kind: .int
	}) or { ic_error(err.msg()) }

	ctx.universe.add_symbol(ast.TypeSym{
		name: 'u8'
		kind: .u8
	}) or { ic_error(err.msg()) }
	ctx.universe.add_symbol(ast.TypeSym{
		name: 'u16'
		kind: .u16
	}) or { ic_error(err.msg()) }
	ctx.universe.add_symbol(ast.TypeSym{
		name: 'u32'
		kind: .u32
	}) or { ic_error(err.msg()) }
	ctx.universe.add_symbol(ast.TypeSym{
		name: 'u64'
		kind: .u64
	}) or { ic_error(err.msg()) }
	ctx.universe.add_symbol(ast.TypeSym{
		name: 'uint'
		kind: .uint
	}) or { ic_error(err.msg()) }

	ctx.universe.add_symbol(ast.TypeSym{
		name: 'f32'
		kind: .f32
	}) or { ic_error(err.msg()) }
	ctx.universe.add_symbol(ast.TypeSym{
		name: 'f64'
		kind: .f64
	}) or { ic_error(err.msg()) }

	ctx.universe.add_symbol(ast.TypeSym{
		name: 'bool'
		kind: .bool
	}) or { ic_error(err.msg()) }
	ctx.universe.add_symbol(ast.TypeSym{
		name: 'rune'
		kind: .rune
	}) or { ic_error(err.msg()) }
}

pub fn (mut ctx CContext) load_primitive_types() {
	ctx.void_type = ast.VoidType{}
	ctx.never_type = ast.NeverType{}
	ctx.none_type = ast.NoneType{}

	ctx.i8_type = ast.SimpleType{
		sym: ctx.universe.find('i8') or { ic_error(err.msg()) }
	}
	ctx.i16_type = ast.SimpleType{
		sym: ctx.universe.find('i16') or { ic_error(err.msg()) }
	}
	ctx.i32_type = ast.SimpleType{
		sym: ctx.universe.find('i32') or { ic_error(err.msg()) }
	}
	ctx.i64_type = ast.SimpleType{
		sym: ctx.universe.find('i64') or { ic_error(err.msg()) }
	}
	ctx.int_type = ast.SimpleType{
		sym: ctx.universe.find('int') or { ic_error(err.msg()) }
	}

	ctx.u8_type = ast.SimpleType{
		sym: ctx.universe.find('u8') or { ic_error(err.msg()) }
	}
	ctx.u16_type = ast.SimpleType{
		sym: ctx.universe.find('u16') or { ic_error(err.msg()) }
	}
	ctx.u32_type = ast.SimpleType{
		sym: ctx.universe.find('u32') or { ic_error(err.msg()) }
	}
	ctx.u64_type = ast.SimpleType{
		sym: ctx.universe.find('u64') or { ic_error(err.msg()) }
	}
	ctx.uint_type = ast.SimpleType{
		sym: ctx.universe.find('uint') or { ic_error(err.msg()) }
	}

	ctx.f32_type = ast.SimpleType{
		sym: ctx.universe.find('f32') or { ic_error(err.msg()) }
	}
	ctx.f64_type = ast.SimpleType{
		sym: ctx.universe.find('f64') or { ic_error(err.msg()) }
	}

	ctx.bool_type = ast.SimpleType{
		sym: ctx.universe.find('bool') or { ic_error(err.msg()) }
	}
	ctx.rune_type = ast.SimpleType{
		sym: ctx.universe.find('rune') or { ic_error(err.msg()) }
	}
}

@[inline]
pub fn (ctx &CContext) code_has_errors() bool {
	return ctx.report.errors > 0
}

pub fn (ctx &CContext) abort_if_errors() {
	if ctx.code_has_errors() {
		reason := if ctx.report.errors == 1 {
			'aborting due to previous error'
		} else {
			'aborting due to ${ctx.report.errors} previous errors'
		}
		ic_error('could not compile `${ctx.root_file.mod_name}` module, ${reason}')
	}
}
