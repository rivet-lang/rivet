// Copyright (C) 2024-present The Rivet programming language. Use of this source code
// is governed by an MIT license that can be found in the LICENSE file.

module parser

import rivetc.ast
import rivetc.reporter

fn (mut p Parser) parse_tags() ast.Tags {
	mut tags := ast.Tags{}

	for p.accept(.hash) {
		p.expect(.lbracket)
		for {
			name_pos := p.tok.pos
			name := p.parse_ident()
			mut args := []ast.TagArg{}
			if p.accept(.lparen) {
				for {
					mut arg_name := ?string(none)
					if p.tok.kind == .ident && p.next_tok.kind == .colon {
						arg_name = p.tok.lit
						p.advance(2)
					}
					arg_value := p.parse_expr()
					args << ast.TagArg{arg_name, arg_value}
					if !p.accept(.comma) || p.should_abort() {
						break
					}
				}
				p.expect(.rparen)
			}
			tags.add(name, args) or { reporter.err(err.msg(), name_pos + p.prev_tok.pos).report() }
			if !p.accept(.semicolon) {
				break
			}
		}
		p.expect(.rbracket)
	}

	return tags
}
