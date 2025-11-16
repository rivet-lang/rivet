// Copyright (C) 2024 The Weld programming language. Use of this source
// code is governed by an MIT license that can be found in the LICENSE file.

@[has_globals]
module context

import term
import weldc.ast
import weldc.reporter

@[heap; noinit]
pub struct Context {
pub:
	options Options
pub mut:
	// Universe is the main scope of all symbols that both the user and the compiler define.
	universe &ast.Scope = ast.Scope.new(unsafe { nil }, none)

	// Name of the main package with which the compiler was called.
	root_name string

	// The compiler groups each parsed file by package, this way we can analyze it package by
	// package in the following phases.
	pkgs []&ast.Package

	// Types.
	// NOTE: All of these types are initialized in the semantic analyzer,
	// see `Sema.analyze`.
	untyped    ast.Type
	void_type  ast.Type
	null_type  ast.Type
	never_type ast.Type

	bool_type ast.Type
	rune_type ast.Type

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

	true_sym  ast.Symbol
	false_sym ast.Symbol
	null_sym  ast.Symbol
}

@[inline]
pub fn new(options Options) &Context {
	return &Context{
		options: options
	}
}

pub fn (mut ctx Context) find_or_add_pkg(name string) &ast.Package {
	for pkg in ctx.pkgs {
		if pkg.name == name {
			return pkg
		}
	}
	pkg := &ast.Package{
		name: name
	}
	ctx.pkgs << pkg
	return pkg
}

pub fn (mut ctx Context) load_builtin_symbols() {
	ctx.load_builtin_types()
	ctx.load_builtin_constants()
}

pub fn (mut ctx Context) load_builtin_types() {
	ctx.untyped = ast.Untyped{}
	ctx.void_type = ast.VoidType{}
	ctx.never_type = ast.NeverType{}
	ctx.null_type = ast.NullType{}

	ctx.bool_type = ctx.universe.add_and_get_symbol(ast.TypeSym{
		name: 'bool'
		kind: .bool
	}) or { reporter.ic_error(err.msg()) }.as_type()
	ctx.rune_type = ctx.universe.add_and_get_symbol(ast.TypeSym{
		name: 'rune'
		kind: .rune
	}) or { reporter.ic_error(err.msg()) }.as_type()

	ctx.i8_type = ctx.universe.add_and_get_symbol(ast.TypeSym{
		name: 'i8'
		kind: .i8
	}) or { reporter.ic_error(err.msg()) }.as_type()
	ctx.i16_type = ctx.universe.add_and_get_symbol(ast.TypeSym{
		name: 'i16'
		kind: .i16
	}) or { reporter.ic_error(err.msg()) }.as_type()
	ctx.i32_type = ctx.universe.add_and_get_symbol(ast.TypeSym{
		name: 'i32'
		kind: .i32
	}) or { reporter.ic_error(err.msg()) }.as_type()
	ctx.i64_type = ctx.universe.add_and_get_symbol(ast.TypeSym{
		name: 'i64'
		kind: .i64
	}) or { reporter.ic_error(err.msg()) }.as_type()
	ctx.int_type = ctx.universe.add_and_get_symbol(ast.TypeSym{
		name: 'int'
		kind: .int
	}) or { reporter.ic_error(err.msg()) }.as_type()

	ctx.u8_type = ctx.universe.add_and_get_symbol(ast.TypeSym{
		name: 'u8'
		kind: .u8
	}) or { reporter.ic_error(err.msg()) }.as_type()
	ctx.u16_type = ctx.universe.add_and_get_symbol(ast.TypeSym{
		name: 'u16'
		kind: .u16
	}) or { reporter.ic_error(err.msg()) }.as_type()
	ctx.u32_type = ctx.universe.add_and_get_symbol(ast.TypeSym{
		name: 'u32'
		kind: .u32
	}) or { reporter.ic_error(err.msg()) }.as_type()
	ctx.u64_type = ctx.universe.add_and_get_symbol(ast.TypeSym{
		name: 'u64'
		kind: .u64
	}) or { reporter.ic_error(err.msg()) }.as_type()
	ctx.uint_type = ctx.universe.add_and_get_symbol(ast.TypeSym{
		name: 'uint'
		kind: .uint
	}) or { reporter.ic_error(err.msg()) }.as_type()

	ctx.f32_type = ctx.universe.add_and_get_symbol(ast.TypeSym{
		name: 'f32'
		kind: .f32
	}) or { reporter.ic_error(err.msg()) }.as_type()
	ctx.f64_type = ctx.universe.add_and_get_symbol(ast.TypeSym{
		name: 'f64'
		kind: .f64
	}) or { reporter.ic_error(err.msg()) }.as_type()
	ctx.float_type = ctx.universe.add_and_get_symbol(ast.TypeSym{
		name: 'float'
		kind: .float
	}) or { reporter.ic_error(err.msg()) }.as_type()
}

pub fn (mut ctx Context) load_builtin_constants() {
	ctx.true_sym = ctx.universe.add_and_get_symbol(ast.Variable{
		name: 'true'
		type: ctx.bool_type
	}) or { reporter.ic_error(err.msg()) }
	ctx.false_sym = ctx.universe.add_and_get_symbol(ast.Variable{
		name: 'false'
		type: ctx.bool_type
	}) or { reporter.ic_error(err.msg()) }
	ctx.null_sym = ctx.universe.add_and_get_symbol(ast.Variable{
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
