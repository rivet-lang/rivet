// Copyright (C) 2024 The Weld programming language. Use of this source
// code is governed by an MIT license that can be found in the LICENSE file.

module ast

import weldc.ice

pub type Symbol = Module | Const | Function | Variable | TypeSym

@[inline]
pub fn (sym Symbol) as_type() Type {
	return match sym {
		TypeSym {
			sym.as_type()
		}
		Variable {
			sym.type
		}
		else {
			ice.ice('Symbol.as_type(): attempt to convert a symbol to type: ${sym}')
		}
	}
}

@[inline]
pub fn (sym Symbol) type_of() string {
	return match sym {
		Module {
			sym.type_of()
		}
		Const {
			'constant'
		}
		Function {
			'function'
		}
		Variable {
			sym.type_of()
		}
		TypeSym {
			sym.type_of()
		}
	}
}

pub struct Module {
pub:
	name   string
	is_pkg bool
	pos    FilePos
pub mut:
	scope &Scope = unsafe { nil }
}

@[inline]
pub fn (m &Module) type_of() string {
	return if m.is_pkg {
		'package'
	} else {
		'module'
	}
}

pub struct Const {
pub:
	name   string
	is_pub bool
	type   Type
	pos    FilePos
	scope  &Scope = unsafe { nil }
}

pub struct TypeSym {
pub:
	name   string
	kind   TypeKind
	fields []Field
	scope  &Scope = unsafe { nil }
	pos    FilePos
}

@[inline]
pub fn (ts &TypeSym) type_of() string {
	return match ts.kind {
		.enum { 'enum' }
		.struct { 'struct' }
		.union { 'union' }
		.trait { 'trait' }
		else { 'type' }
	}
}

@[inline]
pub fn (ts &TypeSym) as_type() Type {
	return SymbolType{
		sym: ts
	}
}

pub enum TypeKind as u8 {
	unknown
	alias

	i8
	i16
	i32
	i64
	int

	u8
	u16
	u32
	u64
	uint

	f32
	f64
	float

	bool // alias? => u8
	rune // alias? => i32

	array
	slice
	tuple

	enum
	struct
	union
	trait

	function
}

pub struct Field {
pub:
	name string
	type Type
	pos  FilePos
}

pub struct Function {
pub:
	name  string
	args  []FnArg
	node  &FnStmt = unsafe { nil }
	scope &Scope  = unsafe { nil }
	pos   FilePos
}

pub struct Variable {
pub:
	name     string
	is_local bool
	is_mut   bool
	is_pub   bool
	is_arg   bool
	is_ref   bool
	type     Type
	pos      FilePos
	scope    &Scope = unsafe { nil }
}

@[inline]
pub fn (v &Variable) type_of() string {
	return if v.is_arg {
		'argument'
	} else {
		'variable'
	}
}
