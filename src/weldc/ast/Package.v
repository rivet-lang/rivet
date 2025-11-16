// Copyright (C) 2024 The Weld programming language. Use of this source
// code is governed by an MIT license that can be found in the LICENSE file.

module ast

@[heap]
pub struct Package {
pub:
	name string
pub mut:
	files []&File
	sym   &Module = unsafe { nil }
}
