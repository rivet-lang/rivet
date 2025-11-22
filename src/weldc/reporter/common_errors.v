// Copyright (C) 2024 The Weld programming language. Use of this source
// code is governed by an MIT license that can be found in the LICENSE file.

@[has_globals]
module reporter

import weldc.ice
import weldc.ast

pub fn emit_ierr(err_ IError, pos ast.FilePos) {
	d := ierr(err_, pos)
	d.emit()
}

pub fn ierr(err_ IError, pos ast.FilePos) Diagnostic {
	match err_ {
		ast.DuplicatedSymbolError {
			mut d := err(err_.m, pos)
			d.add_note('previous declaration of `${err_.s.name}` was here', pos: err_.s.pos)
			return d
		}
		else {
			ice.ice('invalid compiler common error `${err_}` in ${pos}')
		}
	}
}
