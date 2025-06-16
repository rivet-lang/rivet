// Copyright (C) 2024-present The Rivet programming language. Use of this source code
// is governed by an MIT license that can be found in the LICENSE file.

module ast

pub type Type = VoidType | NoneType | NeverType | UnresolvedType | SimpleType | PointerType

pub struct UnresolvedType {
pub:
	expr Expr
	pos  FilePos
}

pub struct VoidType {}

pub struct NoneType {}

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
