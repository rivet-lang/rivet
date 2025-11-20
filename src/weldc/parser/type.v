// Copyright (C) 2024 The Weld programming language. Use of this source
// code is governed by an MIT license that can be found in the LICENSE file.

module parser

import weldc.ast
import weldc.reporter

fn (mut p Parser) parse_type() ?ast.Type {
	pos := p.tok.pos
	return match true {
		p.accept(.question) {
			// option types: ?T
			ast.OptionType{
				inner: p.parse_type()?
				pos:   pos + p.prev_tok.pos
			}
		}
		p.accept(.amp) {
			// pointer types: *T, *mut T
			ast.PointerType{
				is_mut: p.accept(.kw_mut)
				inner:  p.parse_type()?
				pos:    pos + p.prev_tok.pos
			}
		}
		p.accept(.lbracket) {
			// array or slice types: [5]int, []int
			mut size := ?ast.Expr(none)
			if p.tok.kind != .rbracket {
				size = p.parse_expr()
			}
			p.expect(.rbracket)
			ast.ArrayType{
				size:   size
				is_mut: p.accept(.kw_mut)
				inner:  p.parse_type()?
				pos:    pos + p.prev_tok.pos
			}
		}
		else {
			expr := p.parse_expr()?
			if expr !in [ast.Ident, ast.BuiltinCallExpr] {
				reporter.emit_err('invalid type declaration', expr.pos)
			}
			ast.UnresolvedType{expr, expr.pos}
		}
	}
}
