// Copyright (C) 2024-present The Rivet programming language. Use of this source code
// is governed by an MIT license that can be found in the LICENSE file.

module main

import os
import compiler

fn main() {
	compiler.run(os.args[1..])
}
