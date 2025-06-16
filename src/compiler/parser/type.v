// Copyright (C) 2024-present The Rivet programming language. Use of this source code
// is governed by an MIT license that can be found in the LICENSE file.

module parser

import compiler.ast
import compiler.context as _

fn (mut p Parser) parse_type() ast.Type {
	expr := p.parse_expr()
	return ast.UnresolvedType{expr, expr.pos}
}
