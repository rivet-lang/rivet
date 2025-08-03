// Copyright (C) 2024 The Rivet programming language. Use of this source
// code is governed by an MIT license that can be found in the LICENSE file.

module token

import rivetc.ast
import rivetc.reporter

@[minify]
pub struct Token {
pub:
	kind Kind   // the token number/enum; for quick comparisons
	lit  string // literal representation of the token
	pos  ast.FilePos
}

@[inline]
pub fn Token.no_lit(kind Kind, pos ast.FilePos) Token {
	return Token{
		kind: kind
		pos:  pos
	}
}

pub enum Kind {
	unknown
	eof

	ident  // foo
	int    // 123
	float  // 123.0
	string // "foo"
	char   // 'A'

	plus           // +
	minus          // -
	mul            // *
	div            // /
	mod            // %
	xor            // ^
	pipe           // |
	log_and        // &&
	log_or         // ||
	bang           // !
	bit_not        // ~
	question       // ?
	or_else        // ??
	comma          // ,
	semicolon      // ;
	colon          // :
	amp            // &
	hash           // #
	dollar         // $
	at             // @
	lshift         // <<
	rshift         // >>
	not_in         // !in
	not_is         // !is
	assign         // =
	plus_assign    // +=
	minus_assign   // -=
	div_assign     // /=
	mul_assign     // *=
	xor_assign     // ^=
	mod_assign     // %=
	or_assign      // |=
	and_assign     // &=
	rshift_assign  // <<=
	lshift_assign  // >>=
	log_and_assign // &&=
	log_or_assign  // ||=
	lbrace         // {
	rbrace         // }
	lparen         // (
	rparen         // )
	lbracket       // [
	rbracket       // ]
	eq             // ==
	ne             // !=
	gt             // >
	lt             // <
	ge             // >=
	le             // <=
	dot            // .
	dotdot         // ..
	ellipsis       // ...

	keyword_beg
	kw_break
	kw_continue
	kw_defer
	kw_else
	kw_enum
	kw_for
	kw_fn
	kw_if
	kw_in
	kw_is
	kw_let
	kw_match
	kw_mod
	kw_mut
	kw_pub
	kw_return
	kw_struct
	kw_trait
	kw_use
	kw_while
	keyword_end

	_end_
}

pub const token_str = build_token_str()
pub const keywords = build_keys()

pub const assign_tokens = [Kind.assign, .plus_assign, .minus_assign, .mul_assign, .div_assign,
	.xor_assign, .mod_assign, .or_assign, .and_assign, .rshift_assign, .lshift_assign,
	.log_and_assign, .log_or_assign]!

fn build_keys() map[string]Kind {
	mut res := map[string]Kind{}
	for t in int(Kind.keyword_beg) + 1 .. int(Kind.keyword_end) {
		res[token_str[t]] = unsafe { Kind(t) }
	}
	return res
}

fn build_token_str() []string {
	mut s := []string{len: int(Kind._end_)}
	s[Kind.unknown] = 'unknown'
	s[Kind.eof] = 'end of file'

	s[Kind.ident] = 'identifier'
	s[Kind.int] = 'integer literal'
	s[Kind.float] = 'floating-point literal'
	s[Kind.string] = 'string literal'
	s[Kind.char] = 'character literal'

	s[Kind.plus] = '+'
	s[Kind.minus] = '-'
	s[Kind.mul] = '*'
	s[Kind.div] = '/'
	s[Kind.mod] = '%'
	s[Kind.xor] = '^'
	s[Kind.bit_not] = '~'
	s[Kind.pipe] = '|'
	s[Kind.hash] = '#'
	s[Kind.amp] = '&'
	s[Kind.log_and] = '&&'
	s[Kind.log_or] = '||'
	s[Kind.bang] = '!'
	s[Kind.dot] = '.'
	s[Kind.dotdot] = '..'
	s[Kind.ellipsis] = '...'
	s[Kind.comma] = ','
	s[Kind.not_in] = '!in'
	s[Kind.not_is] = '!is'
	s[Kind.semicolon] = ';'
	s[Kind.colon] = ':'
	s[Kind.assign] = '='
	s[Kind.plus_assign] = '+='
	s[Kind.minus_assign] = '-='
	s[Kind.mul_assign] = '*='
	s[Kind.div_assign] = '/='
	s[Kind.xor_assign] = '^='
	s[Kind.mod_assign] = '%='
	s[Kind.or_assign] = '|='
	s[Kind.and_assign] = '&='
	s[Kind.rshift_assign] = '>>='
	s[Kind.lshift_assign] = '<<='
	s[Kind.log_or_assign] = '||='
	s[Kind.log_and_assign] = '&&='
	s[Kind.lbrace] = '{'
	s[Kind.rbrace] = '}'
	s[Kind.lparen] = '('
	s[Kind.rparen] = ')'
	s[Kind.lbracket] = '['
	s[Kind.rbracket] = ']'
	s[Kind.eq] = '=='
	s[Kind.ne] = '!='
	s[Kind.gt] = '>'
	s[Kind.lt] = '<'
	s[Kind.ge] = '>='
	s[Kind.le] = '<='
	s[Kind.question] = '?'
	s[Kind.or_else] = '??'
	s[Kind.lshift] = '<<'
	s[Kind.rshift] = '>>'
	s[Kind.dollar] = '$'
	s[Kind.at] = '@'

	s[Kind.kw_break] = 'break'
	s[Kind.kw_continue] = 'continue'
	s[Kind.kw_defer] = 'defer'
	s[Kind.kw_else] = 'else'
	s[Kind.kw_enum] = 'enum'
	s[Kind.kw_fn] = 'fn'
	s[Kind.kw_for] = 'for'
	s[Kind.kw_if] = 'if'
	s[Kind.kw_in] = 'in'
	s[Kind.kw_is] = 'is'
	s[Kind.kw_let] = 'let'
	s[Kind.kw_match] = 'match'
	s[Kind.kw_mod] = 'mod'
	s[Kind.kw_mut] = 'mut'
	s[Kind.kw_pub] = 'pub'
	s[Kind.kw_return] = 'return'
	s[Kind.kw_struct] = 'struct'
	s[Kind.kw_trait] = 'trait'
	s[Kind.kw_use] = 'use'
	s[Kind.kw_while] = 'while'

	return s
}

@[inline]
pub fn lookup(key string) Kind {
	return if kind := keywords[key] {
		kind
	} else {
		.ident
	}
}

@[inline]
pub fn is_key(key string) bool {
	return int(keywords[key]) > 0
}

@[inline]
pub fn (t Kind) is_keyword() bool {
	return int(t) > int(Kind.keyword_beg) && int(t) < int(Kind.keyword_end)
}

@[inline]
pub fn (t Kind) is_assign() bool {
	return t in assign_tokens
}

@[inline]
pub fn (t Kind) str() string {
	idx := int(t)
	if idx < 0 || token_str.len <= idx {
		return 'unknown'
	}
	return token_str[idx]
}

pub fn (t Token) str() string {
	mut s := t.kind.str()
	if s.len == 0 {
		reporter.ic_fatal('Token.str(): missing token kind string - at ${t.pos}')
	} else if !s[0].is_letter() {
		// punctuation, operators
		return 'token `${s}`'
	}
	if is_key(t.lit) {
		s = 'keyword'
	}
	if t.lit != '' {
		match t.kind {
			.char { s += ' `\'${t.lit}\'`' }
			.string { s += ' `"${t.lit}"`' }
			else { s += ' `${t.lit}`' }
		}
	}
	return s
}
