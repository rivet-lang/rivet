// Copyright (C) 2024-present The Rivet programming language. Use of this source code
// is governed by an MIT license that can be found in the LICENSE file.

module tokenizer

import compiler.ast
import compiler.context
import compiler.util
import compiler.token { Token, lookup }

const lf = 10
const cr = 13
const backslash = `\\`
const num_sep = `_`

@[inline]
fn is_new_line(ch u8) bool {
	return ch in [cr, lf]
}

@[minify]
pub struct Tokenizer {
	ctx &context.CContext = unsafe { nil }
mut:
	file        &ast.File = unsafe { nil }
	text        string
	line        int
	last_nl_pos int
	pos         int = -1
	eofs        int

	is_started bool
	is_cr_lf   bool

	all_tokens []Token
	tidx       int
}

pub fn from_file(ctx &context.CContext, file &ast.File) &Tokenizer {
	mut t := &Tokenizer{
		ctx:        ctx
		file:       file
		text:       file.content
		all_tokens: []Token{cap: file.content.len / 3}
	}
	t.tokenize_remaining_text()
	return t
}

pub fn from_memory(ctx &context.CContext, text string) &Tokenizer {
	mut t := &Tokenizer{
		ctx:        ctx
		file:       ast.File.from_memory(text)
		text:       text
		all_tokens: []Token{cap: text.len / 3}
	}
	t.tokenize_remaining_text()
	return t
}

fn (mut t Tokenizer) tokenize_remaining_text() {
	for {
		tok := t.internal_next()
		t.all_tokens << tok
		if tok.kind == .eof {
			break
		}
	}
}

@[inline]
fn (t &Tokenizer) current_pos() ast.FilePos {
	cur_loc := t.current_loc()
	return ast.FilePos{
		file:  t.file
		begin: cur_loc
		end:   cur_loc
	}
}

fn (t &Tokenizer) current_loc() ast.FileLoc {
	mut col := t.current_column()
	if col < 1 {
		col = 1
	}
	return ast.FileLoc{t.pos, t.line, col}
}

@[inline]
fn (t &Tokenizer) current_column() int {
	return t.pos - t.last_nl_pos
}

fn (mut t Tokenizer) ignore_line() {
	t.eat_to_end_of_line()
	t.inc_line_number()
}

@[direct_array_access; inline]
fn (mut t Tokenizer) eat_to_end_of_line() {
	for t.pos < t.text.len && t.text[t.pos] != lf {
		t.pos++
	}
}

fn (mut t Tokenizer) inc_line_number() {
	t.last_nl_pos = t.text.len - 1
	if t.last_nl_pos > t.pos {
		t.last_nl_pos = t.pos
	}
	if t.is_cr_lf {
		t.last_nl_pos++
	}
	t.line++
}

@[direct_array_access]
fn (mut t Tokenizer) skip_whitespace() {
	for t.pos < t.text.len {
		c := t.text[t.pos]
		if c == 8 {
			t.pos++
			continue
		}
		if !c.is_space() {
			return
		}
		if t.pos + 1 < t.text.len && c == cr && t.text[t.pos + 1] == lf {
			t.is_cr_lf = true
		}
		if is_new_line(c) && !(t.pos > 0 && t.text[t.pos - 1] == cr && c == lf) {
			t.inc_line_number()
		}
		t.pos++
	}
}

@[direct_array_access]
fn (t &Tokenizer) matches(want string, start_pos int) bool {
	end_pos := start_pos + want.len
	if start_pos < 0 || end_pos < 0 || start_pos >= t.text.len || end_pos > t.text.len {
		return false
	}
	for pos in start_pos .. end_pos {
		if t.text[pos] != want[pos - start_pos] {
			return false
		}
	}
	return true
}

@[direct_array_access]
fn (mut t Tokenizer) peek_token(n int) Token {
	idx := t.tidx + n
	if idx >= t.all_tokens.len {
		return t.eof_token()
	}
	return t.all_tokens[idx]
}

@[direct_array_access]
fn (t &Tokenizer) look_ahead(pos int) u8 {
	return if t.pos + pos < t.text.len {
		t.text[t.pos + pos]
	} else {
		0
	}
}

@[inline]
pub fn (mut t Tokenizer) end_of_file() Token {
	t.eofs++
	if t.pos != t.text.len && t.eofs == 1 {
		t.inc_line_number()
	}
	t.pos = t.text.len
	return t.eof_token()
}

@[inline]
fn (t &Tokenizer) eof_token() Token {
	return Token{
		kind: .eof
		pos:  t.current_pos()
	}
}

@[inline]
pub fn (t &Tokenizer) get_all_tokens() []Token {
	return t.all_tokens
}

@[direct_array_access]
pub fn (mut t Tokenizer) next() Token {
	for {
		cidx := t.tidx
		t.tidx++
		if cidx >= t.all_tokens.len {
			return t.end_of_file()
		}
		return t.all_tokens[cidx]
	}
	return t.eof_token()
}

@[direct_array_access]
fn (mut t Tokenizer) internal_next() Token {
	for {
		t.pos++
		t.skip_whitespace()
		if t.pos >= t.text.len {
			return t.end_of_file()
		}
		ch := t.text[t.pos]
		nextc := t.look_ahead(1)
		mut pos := t.current_pos()
		if util.is_valid_name(ch) {
			lit := t.read_ident()
			pos.end = t.current_loc()
			return Token{
				lit:  lit
				kind: lookup(lit)
				pos:  pos
			}
		} else if ch.is_digit() {
			lit := t.read_number()
			pos.end = t.current_loc()
			return Token{
				lit:  lit.replace('_', '')
				kind: .number
				pos:  pos
			}
		}
		match ch {
			`+` {
				if nextc == `=` {
					t.pos++
					pos.end = t.current_loc()
					return Token.no_lit(.plus_assign, pos)
				}
				return Token.no_lit(.plus, pos)
			}
			`-` {
				if nextc == `=` {
					t.pos++
					pos.end = t.current_loc()
					return Token.no_lit(.minus_assign, pos)
				}
				return Token.no_lit(.minus, pos)
			}
			`*` {
				if nextc == `=` {
					t.pos++
					pos.end = t.current_loc()
					return Token.no_lit(.mul_assign, pos)
				}
				return Token.no_lit(.mul, pos)
			}
			`/` {
				if nextc == `/` {
					t.ignore_line()
					continue
				} else if nextc == `*` {
					start_pos := t.pos
					mut nest_count := 1
					t.pos++
					for nest_count > 0 && t.pos < t.text.len - 1 {
						t.pos++
						if t.pos >= t.text.len - 1 {
							old_pos := t.pos
							t.pos = start_pos
							context.error('unterminated multiline comment', t.current_pos())
							t.pos = old_pos
						}
						if t.text[t.pos] == lf {
							t.inc_line_number()
							continue
						}
						if t.matches('/*', t.pos) && t.text[t.pos + 2] != `/` {
							nest_count++
							continue
						}
						if t.matches('*/', t.pos) {
							nest_count--
						}
					}
					t.pos++
					continue
				} else if nextc == `=` {
					t.pos++
					pos.end = t.current_loc()
					return Token.no_lit(.div_assign, pos)
				}
				return Token.no_lit(.div, pos)
			}
			`%` {
				if nextc == `=` {
					t.pos++
					pos.end = t.current_loc()
					return Token.no_lit(.mod_assign, pos)
				}
				return Token.no_lit(.mod, pos)
			}
			`@` {
				return Token.no_lit(.at, pos)
			}
			`$` {
				return Token.no_lit(.dollar, pos)
			}
			`=` {
				if nextc == `=` {
					t.pos++
					pos.end = t.current_loc()
					return Token.no_lit(.eq, pos)
				}
				return Token.no_lit(.assign, pos)
			}
			`<` {
				if nextc == `=` {
					t.pos++
					pos.end = t.current_loc()
					return Token.no_lit(.le, pos)
				}
				return Token.no_lit(.lt, pos)
			}
			`>` {
				if nextc == `=` {
					t.pos++
					pos.end = t.current_loc()
					return Token.no_lit(.ge, pos)
				}
				return Token.no_lit(.gt, pos)
			}
			`.` {
				if nextc == `.` && t.look_ahead(2) == `.` {
					t.pos += 2
					pos.end = t.current_loc()
					return Token.no_lit(.ellipsis, pos)
				} else if nextc == `.` {
					t.pos++
					pos.end = t.current_loc()
					return Token.no_lit(.dotdot, pos)
				}
				return Token.no_lit(.dot, pos)
			}
			`,` {
				return Token.no_lit(.comma, pos)
			}
			`:` {
				return Token.no_lit(.colon, pos)
			}
			`;` {
				return Token.no_lit(.semicolon, pos)
			}
			`?` {
				if nextc == `?` {
					t.pos++
					pos.end = t.current_loc()
					return Token.no_lit(.or_else, pos)
				}
				return Token.no_lit(.question, pos)
			}
			`#` {
				return Token.no_lit(.hash, pos)
			}
			`&` {
				if nextc == `&` {
					t.pos++
					pos.end = t.current_loc()
					return Token.no_lit(.log_and, pos)
				} else if nextc == `=` {
					t.pos++
					pos.end = t.current_loc()
					return Token.no_lit(.and_assign, pos)
				}
				return Token.no_lit(.amp, pos)
			}
			`|` {
				if nextc == `|` {
					t.pos++
					pos.end = t.current_loc()
					return Token.no_lit(.log_or, pos)
				} else if nextc == `=` {
					t.pos++
					pos.end = t.current_loc()
					return Token.no_lit(.or_assign, pos)
				}
				return Token.no_lit(.pipe, pos)
			}
			`!` {
				if t.matches('is ', t.pos + 1) {
					t.pos += 2
					pos.end = t.current_loc()
					return Token.no_lit(.not_is, pos)
				} else if t.matches('in ', t.pos + 1) {
					t.pos += 2
					pos.end = t.current_loc()
					return Token.no_lit(.not_in, pos)
				} else if nextc == `=` {
					t.pos++
					pos.end = t.current_loc()
					return Token.no_lit(.ne, pos)
				}
				return Token.no_lit(.bang, pos)
			}
			`~` {
				return Token.no_lit(.bit_not, pos)
			}
			`^` {
				if nextc == `=` {
					t.pos++
					pos.end = t.current_loc()
					return Token.no_lit(.xor_assign, pos)
				}
				return Token.no_lit(.xor, pos)
			}
			`{` {
				return Token.no_lit(.lbrace, pos)
			}
			`}` {
				return Token.no_lit(.rbrace, pos)
			}
			`[` {
				return Token.no_lit(.lbracket, pos)
			}
			`]` {
				return Token.no_lit(.rbracket, pos)
			}
			`(` {
				return Token.no_lit(.lparen, pos)
			}
			`)` {
				return Token.no_lit(.rparen, pos)
			}
			`'` {
				lit := t.read_char()
				pos.end = t.current_loc()
				return Token{
					lit:  lit
					kind: .char
					pos:  pos
				}
			}
			`"` {
				lit := t.read_string()
				pos.end = t.current_loc()
				return Token{
					lit:  lit
					kind: .string
					pos:  pos
				}
			}
			else {}
		}
		t.invalid_character()
		break
	}
	return t.end_of_file()
}

@[direct_array_access]
fn (mut t Tokenizer) invalid_character() {
	pos := t.current_pos()
	ch := t.text[t.pos]
	ch_len := rune(ch).length_in_bytes()
	s := if ch_len == 1 {
		ch.ascii_str()
	} else {
		t.text[t.pos..t.pos + ch_len]
	}
	context.error('invalid character `${s}`', pos)
}
