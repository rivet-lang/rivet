// Copyright (C) 2024 The Weld programming language. Use of this source
// code is governed by an MIT license that can be found in the LICENSE file.

module ast

@[heap]
pub struct Scope {
pub mut:
	owner Symbol
mut:
	parent &Scope
	syms   []Symbol
}

@[inline]
pub fn Scope.new(parent &Scope, owner ?Symbol) &Scope {
	mut sc := &Scope{
		parent: parent
	}
	if owner != none {
		sc.owner = owner
	}
	return sc
}

@[inline]
pub fn (sc &Scope) derive() &Scope {
	return &Scope{
		owner:  sc.owner
		parent: sc
	}
}

@[params]
pub struct AddSymbolParams {
pub:
	lookup bool
}

pub fn (mut sc Scope) find_or_add_module(mod_name string, is_pkg bool) !Symbol {
	if existing_sym := sc.find(mod_name) {
		if existing_sym is Module {
			return existing_sym
		}
		return error('cannot register module `${mod_name}` because a ${existing_sym.type_of()} with that name exists')
	}
	mut sym := &Module{
		name:   mod_name
		is_pkg: is_pkg
	}
	sym.scope = Scope.new(sc, Symbol(sym))
	sc.syms << sym
	return Symbol(sym)
}

pub struct DuplicatedSymbolError implements IError {
pub:
	m string
	s Symbol
}

pub fn (d DuplicatedSymbolError) msg() string {
	return d.m
}

pub fn (d DuplicatedSymbolError) code() int {
	return 101
}

pub fn (mut sc Scope) add_symbol(sym Symbol, params AddSymbolParams) ! {
	func := if params.lookup { sc.lookup } else { sc.find }
	if other := func(sym.name) {
		return DuplicatedSymbolError{
			m: 'redeclaration of symbol `${sym.name}`'
			s: other
		}
	}
	sc.syms << sym
}

pub fn (mut sc Scope) add_and_get_symbol(sym Symbol, params AddSymbolParams) !Symbol {
	sc.add_symbol(sym, params)!
	return sym
}

pub fn (sc &Scope) find(name string) ?Symbol {
	for sym in sc.syms {
		if sym.name == name {
			return sym
		}
	}
	return none
}

pub fn (sc &Scope) lookup(name string) ?Symbol {
	if sym := sc.find(name) {
		return sym
	}
	if sc.owner !is Function || isnil(sc.parent) {
		return none
	}
	return sc.parent.lookup(name)
}
