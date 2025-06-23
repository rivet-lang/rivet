// Copyright (C) 2024-present The Rivet programming language. Use of this source code
// is governed by an MIT license that can be found in the LICENSE file.

module ast

pub type Symbol = Module | Function | Variable | TypeSym

pub fn (sym Symbol) type_of() string {
	return match sym {
		Module {
			'module'
		}
		Function {
			'function'
		}
		Variable {
			if sym.is_arg {
				'argument'
			} else if sym.is_mut {
				'variable'
			} else {
				'constant'
			}
		}
		TypeSym {
			'type'
		}
	}
}

pub struct Module {
pub:
	name   string
	is_pkg bool
pub mut:
	scope &Scope = unsafe { nil }
}

pub struct TypeSym {
pub:
	name   string
	kind   TypeKind
	fields []Field
	scope  &Scope = unsafe { nil }
}

pub enum TypeKind {
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

	bool
	rune

	array
	slice
	tuple
	struct
	trait
	enum
	function
}

pub struct Field {
pub:
	name string
	type Type
}

pub struct Function {
pub:
	name  string
	args  []FnArg
	node  &FnStmt = unsafe { nil }
	scope &Scope  = unsafe { nil }
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
