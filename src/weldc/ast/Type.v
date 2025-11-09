// Copyright (C) 2024 The Weld programming language. Use of this source
// code is governed by an MIT license that can be found in the LICENSE file.

module ast

pub type Type = Untyped
	| VoidType
	| NullType
	| NeverType
	| UnresolvedType
	| SimpleType
	| PointerType

pub struct Untyped {}

pub struct UnresolvedType {
pub:
	expr Expr
	pos  FilePos
}

pub struct VoidType {}

pub struct NullType {}

pub struct NeverType {}

pub struct SimpleType {
pub:
	sym Symbol
	pos FilePos
}

pub struct PointerType {
pub:
	inner Type
	pos   FilePos
}
