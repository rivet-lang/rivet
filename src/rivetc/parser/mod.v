// Copyright (C) 2024 The Rivet programming language. Use of this source
// code is governed by an MIT license that can be found in the LICENSE file.

module parser

import rivetc.ast
import rivetc.token
import rivetc.context
import rivetc.reporter
import rivetc.importer
import rivetc.tokenizer

pub struct Parser {
mut:
	ctx &context.Context

	tokenizer &tokenizer.Tokenizer = unsafe { nil }
	prev_tok  token.Token
	tok       token.Token
	next_tok  token.Token

	file &ast.File = unsafe { nil }
	tags ast.Tags

	inside_expr        bool
	inside_block_expr  bool
	inside_local_scope bool
	expect_semicolon   bool

	abort bool
}

@[inline]
pub fn new(ctx &context.Context) &Parser {
	return &Parser{
		ctx: ctx
	}
}

@[inline]
pub fn (mut p Parser) parse(mut imp importer.ImportedMod) {
	p.ctx.log(@METHOD)
	for mut file in imp.files {
		if p.parse_file(mut *file) {
			p.ctx.files << *file
		}
	}
}

pub fn (mut p Parser) parse_file(mut file ast.File) bool {
	p.file = file
	file.stage = .parsed

	defer { p.reset() }

	p.tokenizer = tokenizer.from_file(p.ctx, p.file)
	if p.file.errors > 0 {
		// if the tokenizer found errors in the file, let's skip it
		return false
	}

	p.advance(2)
	if p.tok.kind == .eof {
		return true
	}

	for {
		p.file.stmts << p.parse_stmt()
		if p.should_abort() {
			break
		}
	}
	return true
}

fn (mut p Parser) reset() {
	p.inside_expr = false
	p.inside_block_expr = false
	p.inside_local_scope = false
	p.expect_semicolon = false

	p.abort = false
}

fn (mut p Parser) next() {
	p.prev_tok = p.tok
	p.tok = p.next_tok
	p.next_tok = p.tokenizer.next()
}

fn (mut p Parser) advance(n int) {
	for _ in 0 .. n {
		p.next()
	}
}

fn (mut p Parser) expect(kind token.Kind) {
	if !p.accept(kind) {
		reporter.err('expected `${kind}`, but found ${p.tok}', p.tok.pos).report()
		p.abort = true
	}
}

fn (mut p Parser) accept(kind token.Kind) bool {
	if p.tok.kind == kind {
		p.next()
		return true
	}
	return false
}

@[params]
struct ParseIdentParams {
	allow_kw bool
}

fn (mut p Parser) parse_ident(params ParseIdentParams) string {
	if p.tok.kind == .ident {
		ident := p.tok.lit
		p.next()
		return ident
	}
	if params.allow_kw && p.tok.kind.is_keyword() {
		kw_str := p.tok.kind.str()
		p.next()
		return kw_str
	}
	mut d := reporter.err('expected identifier, but found ${p.tok}', p.tok.pos)
	if p.tok.kind == .string && p.tok.lit.is_identifier() {
		d.add_help('remove the quotes around `${p.tok.lit}`')
	} else if p.tok.kind.is_keyword() {
		d.add_help('add a `_` before the keyword: `_${p.tok.kind}`')
	}
	d.report()
	p.next()
	return ''
}

@[inline]
fn (p &Parser) should_abort() bool {
	return p.tok.kind == .eof || p.abort
}
