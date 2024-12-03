// Copyright (C) 2024-present Jose Mendoza - All rights reserved. Use of this
// source code is governed by an MIT license that can be found in the LICENSE
// file.

module ast

pub type Expr = RuneLit | IntegerLit

pub struct RuneLit {
pub:
	value   string
	is_byte bool
	pos     FilePos
}

pub struct IntegerLit {
pub:
	value string
	pos   FilePos
}
