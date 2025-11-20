// Copyright (C) 2024 The Weld programming language. Use of this source
// code is governed by an MIT license that can be found in the LICENSE file.

module ast

pub type Type = Untyped
	| VoidType
	| NullType
	| NeverType
	| AnyptrType
	| UnresolvedType
	| SymbolType
	| PointerType
	| ArrayType

pub struct Untyped {}

pub struct UnresolvedType {
pub:
	expr Expr
	pos  FilePos
}

pub struct VoidType {}

pub struct NullType {}

pub struct NeverType {}

pub struct AnyptrType {}

pub struct SymbolType {
pub:
	sym Symbol
	pos FilePos
}

pub struct PointerType {
pub:
	inner  Type
	is_mut bool
	pos    FilePos
}

pub struct ArrayType {
pub:
	size   ?Expr // none = slice
	inner  Type
	is_mut bool
	pos    FilePos
}
