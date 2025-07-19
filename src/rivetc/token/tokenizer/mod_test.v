// Copyright (C) 2024 The Rivet programming language. Use of this source
// code is governed by an MIT license that can be found in the LICENSE file.
import rivetc.context
import rivetc.token
import rivetc.token.tokenizer

struct ExpectedToken {
	kind token.Kind
	lit  string
}

const source = '
fn main 123 123.0 0b0101 0o1234567 0x123456ABCDEF
// inline comment

fn other

/*
	multiline comment
*/

fn other2() {}

"my string :)\nhello!"[0]
\'a\' \'b\'
'

const expected_tokens = [
	ExpectedToken{.kw_fn, 'fn'},
	ExpectedToken{.ident, 'main'},
	ExpectedToken{.int, '123'},
	ExpectedToken{.float, '123.0'},
	ExpectedToken{.int, '0b0101'},
	ExpectedToken{.int, '0o1234567'},
	ExpectedToken{.int, '0x123456ABCDEF'},
	ExpectedToken{.kw_fn, 'fn'},
	ExpectedToken{.ident, 'other'},
	ExpectedToken{.kw_fn, 'fn'},
	ExpectedToken{.ident, 'other2'},
	ExpectedToken{.lparen, ''},
	ExpectedToken{.rparen, ''},
	ExpectedToken{.lbrace, ''},
	ExpectedToken{.rbrace, ''},
	ExpectedToken{.string, 'my string :)\nhello!'},
	ExpectedToken{.lbracket, ''},
	ExpectedToken{.int, '0'},
	ExpectedToken{.rbracket, ''},
	ExpectedToken{.char, 'a'},
	ExpectedToken{.char, 'b'},
	ExpectedToken{.eof, ''},
]

fn test_tokenizer_next() {
	mut ctx := &context.Context{}

	mut t := tokenizer.from_memory(ctx, source)
	tokens := t.get_all_tokens()

	assert tokens.len == expected_tokens.len, tokens.str()

	for i, tok in tokens {
		expected_tok := expected_tokens[i]
		assert expected_tok.kind == tok.kind
		assert expected_tok.lit == tok.lit
	}
}
