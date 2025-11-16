// Copyright (C) 2024 The Weld programming language. Use of this source
// code is governed by an MIT license that can be found in the LICENSE file.

module register

import weldc.ast
import weldc.ice

fn (mut reg Register) expr(mut expr ast.Expr) {
	match mut expr {
		ast.BlockExpr {
			old_scope := reg.scope
			defer {
				reg.scope = old_scope
			}
			reg.scope = ast.Scope.new(reg.scope, reg.sym)
			reg.stmts(mut expr.stmts)
		}
		ast.EmptyExpr {
			ice.ice('empty expression detected - ${expr.pos}')
		}
		else {}
	}
}
