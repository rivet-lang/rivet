// Copyright (C) 2024-present The Rivet programming language. Use of this source code
// is governed by an MIT license that can be found in the LICENSE file.

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

pub fn (mut sc Scope) find_or_add_module(mod_name string) !Symbol {
	if existing_sym := sc.find(mod_name) {
		if existing_sym is Module {
			return existing_sym
		}
		return error('cannot register module `${mod_name}` because a ${existing_sym.type_of()} with that name exists')
	}
	mut sym := &Module{
		name: mod_name
	}
	sym.scope = Scope.new(sc, Symbol(sym))
	sc.syms << sym
	return Symbol(sym)
}

pub fn (mut sc Scope) add_symbol(sym Symbol, params AddSymbolParams) ! {
	func := if params.lookup { sc.lookup } else { sc.find }
	if other := func(sym.name) {
		m := if (other is Variable && other.is_arg) && (sym is Variable && !sym.is_arg) {
			'${sym.type_of()} `${sym.name}` has the same name as an argument'
		} else if other.type_of() == sym.type_of() {
			'duplicate ${sym.type_of()} `${sym.name}`'
		} else {
			'another symbol exists with the same name as `${sym.name}`'
		}
		return error(m)
	}
	sc.syms << sym
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
