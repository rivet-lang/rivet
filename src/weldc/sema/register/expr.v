// Copyright (C) 2024 The Weld programming language. Use of this source
// code is governed by an MIT license that can be found in the LICENSE file.

module register

import weldc.ast

fn (mut reg Register) expr(mut expr ast.Expr) {
	match mut expr {
		ast.BlockExpr {
			old_scope := reg.scope
			reg.scope = ast.Scope.new(reg.scope, reg.sym)
			reg.stmts(mut expr.stmts)
			reg.scope = old_scope
		}
		ast.ParenExpr {
			reg.expr(mut expr.expr)
		}
		ast.ReturnExpr {
			if expr.expr != none {
				reg.expr(mut expr.expr)
			}
		}
		ast.BuiltinCallExpr {
			for mut arg in expr.args {
				reg.expr(mut arg)
			}
		}
		ast.CallExpr {
			reg.expr(mut expr.left)
			for mut arg in expr.args {
				reg.expr(mut arg)
			}
		}
		ast.IfExpr {
			for mut b in expr.branches {
				if b.cond != none {
					reg.expr(mut b.cond)
				}
				reg.expr(mut b.expr)
			}
		}
		ast.MatchExpr {
			for mut b in expr.branches {
				for mut case in b.cases {
					reg.expr(mut case)
				}
				reg.expr(mut b.expr)
			}
		}
		ast.UnaryExpr {
			reg.expr(mut expr.right)
		}
		ast.AssignExpr, ast.BinaryExpr {
			reg.expr(mut expr.left)
			reg.expr(mut expr.right)
		}
		else {}
	}
}
