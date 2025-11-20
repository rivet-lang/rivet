// Copyright (C) 2024 The Weld programming language. Use of this source
// code is governed by an MIT license that can be found in the LICENSE file.

module parser

import weldc.ast
import weldc.reporter

fn (mut p Parser) parse_type() ast.Type {
	pos := p.tok.pos
	match true {
		p.accept(.amp) {
			// pointer types: *T, *mut T
			return ast.PointerType{
				is_mut: p.accept(.kw_mut)
				inner:  p.parse_type()
				pos:    pos + p.prev_tok.pos
			}
		}
		p.accept(.lbracket) {
			// array types | slice types: [5]int, []int
			mut size := ?ast.Expr(none)
			if p.tok.kind != .rbracket {
				size = p.parse_expr()
			}
			p.expect(.rbracket)
			return ast.ArrayType{
				size:   size
				is_mut: p.accept(.kw_mut)
				inner:  p.parse_type()
			}
		}
		else {}
	}
	expr := p.parse_expr()
	if expr !in [ast.Ident, ast.BuiltinCallExpr] {
		reporter.emit_err('invalid type declaration', expr.pos)
	}
	return ast.UnresolvedType{expr, expr.pos}
}
