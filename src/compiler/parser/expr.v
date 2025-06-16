// Copyright (C) 2024-present The Rivet programming language. Use of this source code
// is governed by an MIT license that can be found in the LICENSE file.

module parser

import compiler.ast
import compiler.util
import compiler.context

fn (mut p Parser) parse_surrounded_expr() ast.Expr {
	p.expect(.lparen)
	expr := p.parse_expr()
	p.expect(.rparen)
	return expr
}

fn (mut p Parser) parse_expr() ast.Expr {
	if p.should_abort() {
		return ast.empty_expr
	}
	old_inside_expr := p.inside_expr
	defer { p.inside_expr = old_inside_expr }
	p.inside_expr = true
	return p.parse_or_expr()
}

fn (mut p Parser) parse_or_expr() ast.Expr {
	mut left := p.parse_and_expr()
	for p.accept(.log_or) {
		right := p.parse_and_expr()
		left = ast.BinaryExpr{
			left:  left
			op:    .log_or
			right: right
			pos:   left.pos + right.pos
		}
	}
	return left
}

fn (mut p Parser) parse_and_expr() ast.Expr {
	mut left := p.parse_equality_expr()
	for p.accept(.log_and) {
		right := p.parse_equality_expr()
		left = ast.BinaryExpr{
			left:  left
			op:    .log_and
			right: right
			pos:   left.pos + right.pos
		}
	}
	return left
}

fn (mut p Parser) parse_equality_expr() ast.Expr {
	mut left := p.parse_relational_expr()
	for p.tok.kind in [.eq, .ne] {
		op := p.tok.kind
		p.next()
		right := p.parse_relational_expr()
		left = ast.BinaryExpr{
			left:  left
			op:    if op == .eq { .eq } else { .ne }
			right: right
			pos:   left.pos + right.pos
		}
	}
	return left
}

fn (mut p Parser) parse_relational_expr() ast.Expr {
	mut left := p.parse_shift_expr()
	for p.tok.kind in [.gt, .lt, .le, .or_else, .kw_in, .not_in, .kw_is, .not_is] {
		op := p.tok.kind
		p.next()
		right := p.parse_shift_expr()
		left = ast.BinaryExpr{
			left:  left
			op:    match op {
				.gt { .gt }
				.lt { .lt }
				.ge { .ge }
				.or_else { .or_else }
				.kw_in { .kw_in }
				.kw_is { .kw_is }
				else { .unknown }
			}
			right: right
			pos:   left.pos + right.pos
		}
	}
	return left
}

fn (mut p Parser) parse_shift_expr() ast.Expr {
	mut left := p.parse_additive_expr()
	for p.tok.kind in [.amp, .pipe, .xor, .lshift, .rshift] {
		op := p.tok.kind
		p.next()
		right := p.parse_additive_expr()
		left = ast.BinaryExpr{
			left:  left
			op:    match op {
				.amp { .amp }
				.pipe { .pipe }
				.xor { .xor }
				.lshift { .lshift }
				.rshift { .rshift }
				else { .unknown }
			}
			right: right
			pos:   left.pos + right.pos
		}
	}
	return left
}

fn (mut p Parser) parse_additive_expr() ast.Expr {
	mut left := p.parse_multiplicative_expr()
	for p.tok.kind in [.plus, .minus] {
		op := p.tok.kind
		p.next()
		right := p.parse_multiplicative_expr()
		left = ast.BinaryExpr{
			left:  left
			op:    match op {
				.plus { .plus }
				.minus { .minus }
				else { .unknown }
			}
			right: right
			pos:   left.pos + right.pos
		}
	}
	return left
}

fn (mut p Parser) parse_multiplicative_expr() ast.Expr {
	mut left := p.parse_unary_expr()
	for p.tok.kind in [.mul, .div, .mod] {
		op := p.tok.kind
		p.next()
		right := p.parse_unary_expr()
		left = ast.BinaryExpr{
			left:  left
			op:    match op {
				.mul { .mul }
				.div { .div }
				.mod { .mod }
				else { .unknown }
			}
			right: right
			pos:   left.pos + right.pos
		}
	}
	return left
}

fn (mut p Parser) parse_unary_expr() ast.Expr {
	mut expr := ast.empty_expr
	if p.tok.kind in [.amp, .bang, .bit_not, .minus] {
		op := p.tok.kind
		pos := p.tok.pos
		p.next()
		right := p.parse_unary_expr()
		expr = ast.UnaryExpr{
			right: expr
			op:    match op {
				.amp { .amp }
				.bang { .bang }
				.bit_not { .bit_not }
				.minus { .minus }
				else { .unknown }
			}
			pos:   pos + right.pos
		}
	} else {
		expr = p.parse_primary_expr()
	}
	return expr
}

fn (mut p Parser) parse_primary_expr() ast.Expr {
	mut expr := ast.empty_expr
	match p.tok.kind {
		.char, .number, .string {
			expr = p.parse_literal()
		}
		.ident {
			if p.next_tok.kind == .bang {
				// builtin call expr
				mut pos := p.tok.pos
				name := p.parse_ident()
				p.expect(.bang)
				p.expect(.lparen)
				mut args := []ast.Expr{}
				for {
					args << p.parse_expr()
					if !p.accept(.comma) || p.should_abort() {
						break
					}
				}
				pos += p.tok.pos
				p.expect(.rparen)
				expr = ast.BuiltinCallExpr{
					name: name
					args: args
					pos:  pos
				}
			} else if p.next_tok.kind == .char {
				if p.tok.lit == 'b' {
					expr = p.parse_char_literal()
				} else {
					context.error('only `b` is recognized as a valid prefix for a character literal',
						p.tok.pos)
					p.next()
				}
			} else if p.next_tok.kind == .string {
				expr = p.parse_string_literal()
			} else {
				expr = p.parse_ident_expr()
			}
		}
		.lparen {
			pos := p.tok.pos
			p.next()
			expr = ast.ParenExpr{p.parse_expr(), pos + p.tok.pos}
			p.expect(.rparen)
		}
		.kw_if {
			expr = p.parse_if_expr()
		}
		.kw_match {
			expr = p.parse_match_expr()
		}
		.kw_break, .kw_continue {
			expr = p.parse_loop_control()
		}
		.kw_return {
			expr = p.parse_return_expr()
		}
		.lbrace {
			expr = p.parse_block_expr()
		}
		else {}
	}

	if p.should_abort() {
		return expr
	}

	for {
		match true {
			p.accept(.lparen) {
				// call expr
				mut pos := p.prev_tok.pos
				mut args := []ast.Expr{}
				for {
					args << p.parse_expr()
					if !p.accept(.comma) || p.should_abort() {
						break
					}
				}
				pos += p.tok.pos
				p.expect(.rparen)
				expr = ast.CallExpr{
					left: expr
					args: args
					pos:  pos
				}
			}
			p.tok.kind.is_assign() {
				op := match p.tok.kind {
					.assign { ast.AssignOp.assign }
					.plus_assign { .plus_assign }
					.minus_assign { .minus_assign }
					.div_assign { .div_assign }
					.mul_assign { .mul_assign }
					.xor_assign { .xor_assign }
					.mod_assign { .mod_assign }
					.or_assign { .or_assign }
					.and_assign { .and_assign }
					.lshift_assign { .lshift_assign }
					.rshift_assign { .rshift_assign }
					.log_and_assign { .log_and_assign }
					.log_or_assign { .log_or_assign }
					else { .unknown }
				}
				p.next()
				expr = ast.AssignExpr{
					left:  expr
					op:    op
					right: p.parse_expr()
				}
			}
			p.should_abort() {
				break
			}
			else {
				break
			}
		}
	}

	return expr
}

fn (mut p Parser) parse_literal() ast.Expr {
	return match p.tok.kind {
		.char {
			p.parse_char_literal()
		}
		.number {
			p.parse_number_literal()
		}
		.string {
			p.parse_string_literal()
		}
		else {
			context.error('invalid literal expression: found ${p.tok}', p.tok.pos)
			ast.empty_expr
		}
	}
}

fn (mut p Parser) parse_number_literal() ast.Expr {
	pos := p.tok.pos
	value := p.tok.lit
	p.next()
	no_has_prefix := !util.numeric_value_has_prefix(value)
	return if no_has_prefix && value.index_any('.eE') >= 0 {
		ast.FloatLiteral{
			value: value
			pos:   pos
		}
	} else {
		ast.IntegerLiteral{
			value: value
			pos:   pos
		}
	}
}

fn (mut p Parser) parse_char_literal() ast.Expr {
	is_byte := if p.tok.kind == .ident && p.tok.lit == 'b' {
		p.next()
		true
	} else {
		false
	}
	value := p.tok.lit
	pos := p.tok.pos
	p.expect(.char)
	return ast.CharLiteral{
		value:   value
		is_byte: is_byte
		pos:     pos
	}
}

fn (mut p Parser) parse_string_literal() ast.Expr {
	literal_type := if p.accept(.ident) {
		match p.prev_tok.lit {
			'b' {
				ast.StringType.bytes
			}
			'c' {
				ast.StringType.c_string
			}
			'r' {
				ast.StringType.raw_string
			}
			else {
				context.error('only `b`, `c` and `r` are recognized as valid prefixes for a string literal',
					p.prev_tok.pos)
				ast.StringType.normal
			}
		}
	} else {
		.normal
	}
	value := p.tok.lit
	pos := p.tok.pos
	p.expect(.string)
	return ast.StringLiteral{
		value:        value
		literal_type: literal_type
		pos:          pos
	}
}

fn (mut p Parser) parse_ident_expr() ast.Expr {
	pos := p.tok.pos
	name := p.parse_ident()
	return ast.Ident{
		name: name
		pos:  pos
	}
}

fn (mut p Parser) parse_match_expr() ast.Expr {
	pos := p.tok.pos
	mut branches := []ast.MatchBranch{}

	p.expect(.kw_match)
	expr := p.parse_surrounded_expr()
	p.expect(.lbrace)
	for {
		mut is_else := false
		mut cases := []ast.Expr{}
		if p.accept(.kw_else) {
			is_else = true
		} else {
			for {
				cases << p.parse_expr()
				if !p.accept(.comma) || p.should_abort() {
					break
				}
			}
		}
		p.expect(.colon)
		branch_expr := p.parse_expr()
		branches << ast.MatchBranch{
			is_else: is_else
			cases:   cases
			expr:    branch_expr
		}
		if !p.accept(.comma) || p.should_abort() {
			break
		}
	}
	p.expect(.rbrace)

	return ast.MatchExpr{
		expr:     expr
		branches: branches
		pos:      pos
	}
}

fn (mut p Parser) parse_if_expr() ast.Expr {
	mut is_inline := false
	mut branches := []ast.IfBranch{}
	pos := p.tok.pos
	for {
		if p.accept(.kw_else) && p.tok.kind != .kw_if {
			if p.tok.kind != .lbrace {
				p.expect(.colon)
			}
			branches << ast.IfBranch{none, p.parse_expr(), pos}
			break
		}
		p.expect(.kw_if)
		cond := p.parse_surrounded_expr()
		mut expect_comma := false
		if p.tok.kind != .lbrace {
			p.expect(.colon)
			expect_comma = true
			is_inline = true
		}
		branches << ast.IfBranch{cond, p.parse_expr(), pos}
		if expect_comma && p.next_tok.kind == .kw_else {
			p.expect(.comma)
		}
		if p.tok.kind != .kw_else || p.should_abort() {
			break
		}
	}
	return ast.IfExpr{branches, is_inline, pos}
}

fn (mut p Parser) parse_loop_control() ast.Expr {
	pos := p.tok.pos
	is_continue := p.tok.kind == .kw_continue
	p.next()
	return ast.LoopControl{is_continue, pos}
}

fn (mut p Parser) parse_return_expr() ast.Expr {
	pos := p.tok.pos
	p.expect(.kw_return)
	mut expr := ?ast.Expr(none)
	if p.tok.kind !in [.semicolon, .comma, .rparen, .rbrace] {
		expr = p.parse_expr()
	}
	return ast.ReturnExpr{
		expr: expr
		pos:  pos + p.prev_tok.pos
	}
}

fn (mut p Parser) parse_block_expr() ast.Expr {
	old_inside_block_expr := p.inside_block_expr
	defer { p.inside_block_expr = old_inside_block_expr }
	p.inside_block_expr = p.inside_expr

	stmts, expr := p.parse_simple_block()
	return ast.BlockExpr{
		stmts: stmts
		expr:  expr
	}
}
