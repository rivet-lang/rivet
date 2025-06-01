// Copyright (C) 2024-present The Rivet programming language. Use of this source code
// is governed by an MIT license that can be found in the LICENSE file.

module parser

import compiler.ast
import compiler.context

// parses a list of statements that are enclosed in `{` `}`, it can also parse a
// single-statement if the form `: <stmt>` is used.
fn (mut p Parser) parse_stmts() []ast.Stmt {
	if p.tok.kind == .eof {
		return []
	}

	if p.accept(.colon) {
		// single-statement: `if (is_online): player.kick();`
		stmt := p.parse_stmt()
		p.expect_semicolon = false
		return [stmt]
	}

	p.expect_semicolon = false
	if p.tok.kind != .lbrace {
		p.abort = true
		context.error('expected block, found ${p.tok}', p.tok.pos, context.help('if you want to write a single-statement, use `:`: `if (is_online): player.kick()`'))
		return []
	}

	old_inside_local_scope := p.inside_local_scope
	defer { p.inside_local_scope = old_inside_local_scope }
	p.inside_local_scope = true

	stmts, _ := p.parse_simple_block()
	return stmts
}

fn (mut p Parser) parse_simple_block() ([]ast.Stmt, ?ast.Expr) {
	lbrace_pos := p.tok.pos
	if p.accept(.lbrace) && p.accept(.rbrace) {
		// empty block: `{}`
		return []ast.Stmt{}, none
	}

	mut expr := ?ast.Expr(none)

	mut is_finished := false
	mut stmts := []ast.Stmt{}
	for {
		p.expect_semicolon = true
		stmt := p.parse_stmt()
		p.expect_semicolon = false

		if p.inside_block_expr && p.tok.kind == .rbrace && stmt is ast.ExprStmt {
			// this is an expression that is being used as the value returned by the block
			expr = stmt.expr
		} else {
			stmts << stmt
		}

		is_finished = p.accept(.rbrace)
		if is_finished || p.should_abort() {
			break
		}
	}

	if !is_finished && !p.abort {
		// we give an error because the block has not been finished (`}` was not found),
		// but it has not been aborted (due to poor formation of expressions or statements)
		context.error('unfinished block, expected `}` and found ${p.tok}', lbrace_pos)
		p.abort = true
	}

	return stmts, expr
}

fn (mut p Parser) parse_stmt() ast.Stmt {
	if p.should_abort() {
		return ast.empty_stmt(p.tok.pos)
	}

	mut old_expect_semicolon := p.expect_semicolon
	mut old_tags := p.tags
	defer {
		p.expect_semicolon = old_expect_semicolon
		p.tags = old_tags
	}

	p.tags = p.parse_tags()

	// module stmts: fns, vars, etc.
	is_pub := !p.inside_local_scope && p.accept(.kw_pub)
	mut stmt := ast.empty_stmt(p.tok.pos)
	match p.tok.kind {
		.kw_fn {
			stmt = p.parse_fn_stmt(is_pub)
		}
		.kw_var, .kw_val {
			stmt = p.parse_var_stmt(is_pub)
		}
		.semicolon {
			// an orphaned semicolon indicates that `p.stmt()` is not properly
			// handling the `;`
			context.error('orphan semicolon detected', p.tok.pos)
			p.abort = true
		}
		else {
			// local stmts: if, while, match, etc.
			if p.inside_local_scope {
				match p.tok.kind {
					.kw_for {}
					.kw_while {
						stmt = p.parse_while_stmt()
					}
					.kw_defer {
						stmt = p.parse_defer_stmt()
					}
					else {
						// `.kw_if`, `.kw_match`, `.kw_break`/`.kw_continue` and `.kw_return` are
						// handled in `p.parse_expr()`
						expr := p.parse_expr()
						if expr in [ast.MatchExpr, ast.BlockExpr] {
							p.expect_semicolon = false
						} else if expr is ast.IfExpr {
							// true = `if (abc): x, else: y;`
							p.expect_semicolon = expr.is_inline
						}
						stmt = ast.ExprStmt{p.tags, expr}
					}
				}
			} else {
				context.error('invalid declaration: unexpected ${p.tok}', p.tok.pos)
				p.abort = true
			}
		}
	}

	// NOTE: if the previous token was a semicolon, it means that the parser no longer needs
	// to wait for another semicolon.
	if p.expect_semicolon && !p.should_abort() && !(p.inside_block_expr && p.tok.kind == .rbrace)
		&& p.prev_tok.kind != .semicolon {
		p.expect(.semicolon)
		p.expect_semicolon = false
	}

	return stmt
}

fn (mut p Parser) parse_fn_stmt(is_pub bool) ast.FnStmt {
	p.expect(.kw_fn)
	name_pos := p.tok.pos
	name := p.parse_ident()
	p.expect(.lparen)
	mut args := []ast.FnArg{}
	if !p.accept(.rparen) {
		for {
			mut arg_pos := p.tok.pos
			arg_is_ref := p.accept(.amp)
			arg_is_var := p.accept(.kw_var)
			arg_name := p.parse_ident()
			arg_name_pos := p.prev_tok.pos
			p.expect(.colon)
			arg_type := p.parse_type()
			mut arg_default_expr := ast.empty_expr
			if p.accept(.assign) {
				arg_default_expr = p.parse_expr()
			}
			arg_pos += p.prev_tok.pos
			args << ast.FnArg{arg_name, arg_name_pos, arg_type, arg_default_expr, arg_is_var, arg_is_ref, arg_pos}
			if !p.accept(.comma) || p.should_abort() {
				break
			}
		}
		p.expect(.rparen)
	}
	return_type := if p.tok.kind !in [.lbrace, .semicolon] {
		p.parse_type()
	} else {
		p.ctx.void_type
	}
	has_body := !p.accept(.semicolon)
	mut stmts := []ast.Stmt{}
	if has_body {
		stmts = p.parse_stmts()
	}
	return ast.FnStmt{
		tags:        p.tags
		is_pub:      is_pub
		name:        name
		name_pos:    name_pos
		args:        args
		return_type: return_type
		has_body:    has_body
		stmts:       stmts
	}
}

fn (mut p Parser) parse_var_stmt(is_pub bool) ast.VarStmt {
	is_val := p.accept(.kw_val)
	if !is_val {
		p.expect(.kw_var)
	}
	mut lefts := []ast.Variable{}
	for {
		mut left_pos := p.tok.pos
		name := p.parse_ident()
		type := if p.accept(.colon) {
			p.parse_type()
		} else {
			p.ctx.void_type
		}
		left_pos += p.prev_tok.pos
		lefts << ast.Variable{
			name:     name
			is_local: p.inside_local_scope
			is_pub:   is_pub
			is_val:   is_val
			type:     type
			pos:      left_pos
		}
		if !p.accept(.comma) || p.should_abort() {
			break
		}
	}
	p.expect(.assign)
	right := p.parse_expr()
	p.expect_semicolon = true
	return ast.VarStmt{
		tags:   p.tags
		lefts:  lefts
		right:  right
		is_pub: is_pub
	}
}

fn (mut p Parser) parse_while_stmt() ast.WhileStmt {
	p.expect(.kw_while)
	p.expect(.lparen)
	mut init_stmt := ?ast.VarStmt(none)
	if p.tok.kind == .kw_var {
		init_stmt = p.parse_var_stmt(false)
		p.expect(.semicolon)
	}
	cond := p.parse_expr()
	mut continue_expr := ?ast.Expr(none)
	if p.accept(.semicolon) {
		continue_expr = p.parse_expr()
	}
	p.expect(.rparen)
	stmts := p.parse_stmts()
	return ast.WhileStmt{p.tags, init_stmt, cond, continue_expr, stmts}
}

fn (mut p Parser) parse_defer_stmt() ast.DeferStmt {
	p.expect(.kw_defer)
	mut defer_mode := ast.DeferMode.default
	if p.accept(.lparen) {
		mode_pos := p.tok.pos
		mode := p.parse_ident()
		match mode {
			'success' {
				defer_mode = .success
			}
			'error' {
				defer_mode = .error
			}
			else {
				context.error('unknown `defer` mode', mode_pos, context.note('valid `defer` modes are `success` and `error`'))
			}
		}
		p.expect(.rparen)
	}
	stmts := p.parse_stmts()
	return ast.DeferStmt{
		tags:  p.tags
		mode:  defer_mode
		stmts: stmts
	}
}
