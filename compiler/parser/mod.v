// Copyright (C) 2024-present The Rivet programming language. Use of this source code
// is governed by an MIT license that can be found in the LICENSE file.

module parser

import compiler.ast
import compiler.context
import compiler.token
import compiler.token.tokenizer

pub struct Parser {
mut:
	ctx &context.CContext

	tokenizer tokenizer.Tokenizer
	prev_tok  token.Token
	tok       token.Token
	next_tok  token.Token

	file &ast.File = unsafe { nil }
	tags ast.Tags

	inside_root_file   bool
	inside_expr        bool
	inside_block_expr  bool
	inside_local_scope bool
	expect_semicolon   bool
	abort              bool
}

@[inline]
pub fn new(ctx &context.CContext) &Parser {
	return &Parser{
		ctx: ctx
	}
}

@[inline]
pub fn (mut p Parser) parse() {
	for i, input in p.ctx.options.input_files {
		p.inside_root_file = i == 0
		if file := p.parse_file(input, p.ctx.options.input_dir) {
			p.ctx.files << file
		}
	}
}

fn (mut p Parser) parse_file(filename string, root_dir string) ?&ast.File {
	p.file = ast.File.new(filename)
	p.file.set_mod_name(root_dir)
	if p.inside_root_file && isnil(p.ctx.root_file) {
		p.ctx.root_file = p.file
	}

	p.tokenizer = tokenizer.from_file(p.ctx, p.file)
	if p.file.errors > 0 {
		// if the tokenizer found errors in the file, let's skip it
		return none
	}

	p.advance(2)
	for {
		p.file.stmts << p.parse_stmt()
		if p.should_abort() {
			break
		}
	}

	return p.file
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
		context.error('expected `${kind}`, but found ${p.tok}', p.tok.pos)
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

fn (mut p Parser) parse_ident() string {
	if p.tok.kind == .ident {
		ident := p.tok.lit
		p.next()
		return ident
	}
	p.abort = true
	context.error('expected identifier, but found ${p.tok}', p.tok.pos)
	p.next()
	return ''
}

@[inline]
fn (p &Parser) should_abort() bool {
	return p.tok.kind == .eof || p.abort
}
