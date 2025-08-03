// Copyright (C) 2024 The Rivet programming language. Use of this source
// code is governed by an MIT license that can be found in the LICENSE file.

module tokenizer

import rivetc.token
import rivetc.reporter

fn (mut t Tokenizer) read_ident() string {
	start := t.pos
	for t.pos < t.text.len {
		c := t.text[t.pos]
		if is_valid_name(c) || c.is_digit() {
			t.pos++
			continue
		}
		break
	}
	lit := t.text[start..t.pos]
	t.pos--
	return lit
}

enum NumberMode {
	bin
	oct
	hex
	dec
}

@[inline]
fn (nm NumberMode) is_valid(c u8) bool {
	return match nm {
		.bin { c.is_bin_digit() }
		.oct { c.is_oct_digit() }
		.hex { c.is_hex_digit() }
		.dec { c.is_digit() }
	}
}

@[inline]
fn (nm NumberMode) str() string {
	return match nm {
		.bin { 'binary' }
		.oct { 'octal' }
		.hex { 'hexadecimal' }
		.dec { 'decimal' }
	}
}

@[direct_array_access]
fn (mut t Tokenizer) read_number_mode(mode NumberMode) (string, token.Kind) {
	mut kind := token.Kind.int
	start := t.pos
	if mode != .dec {
		t.pos += 2 // skip '0x', '0b', '0o'
	}
	if t.pos < t.text.len && t.text[t.pos] == num_sep {
		reporter.err('separator `_` is only valid between digits in a numeric literal',
			t.current_pos()).report()
	}
	for t.pos < t.text.len {
		ch := t.text[t.pos]
		if ch == num_sep && t.text[t.pos - 1] == num_sep {
			reporter.err('cannot use `_` consecutively in a numeric literal', t.current_pos()).report()
		}
		if !mode.is_valid(ch) && ch != num_sep {
			if mode == .dec && (!ch.is_letter() || ch in [`e`, `E`]) {
				break
			} else if mode != .dec && (!ch.is_digit() && !ch.is_letter()) {
				break
			}

			reporter.err('${mode} number has unsuitable digit `${t.text[t.pos].ascii_str()}`',
				t.current_pos()).report()
		}
		t.pos++
	}
	if t.text[t.pos - 1] == num_sep {
		t.pos--
		reporter.err('cannot use `_` at the end of a numeric literal', t.current_pos()).report()
	}
	if mode != .dec && start + 2 == t.pos {
		t.pos--

		reporter.err('number part of this ${mode} number is not provided', t.current_pos()).report()
		t.pos++
	}
	if mode == .dec {
		mut call_method := false // `true` for, e.g., 5.method(), 5.5.method(), 5e5.method()
		mut is_range := false // `true` for, e.g., 5..10
		// fractional part
		if t.pos < t.text.len && t.text[t.pos] == `.` {
			kind = .float
			t.pos++
			if t.pos < t.text.len {
				// 16.6, 16.6.str()
				if t.text[t.pos].is_digit() {
					for t.pos < t.text.len {
						c := t.text[t.pos]
						if !c.is_digit() {
							if !c.is_letter() || c in [`e`, `E`] {
								// 16.6.str()
								if c == `.` && t.pos + 1 < t.text.len
									&& t.text[t.pos + 1].is_letter() {
									call_method = true
								}
								break
							} else {
								reporter.err('number has unsuitable digit `${c.ascii_str()}`',
									t.current_pos()).report()
							}
						}
						t.pos++
					}
				} else if t.text[t.pos] == `.` {
					// 4.. a range
					is_range = true
					t.pos--
				} else if t.text[t.pos] in [`e`, `E`] {
					// 6.e6
				} else if t.text[t.pos].is_letter() {
					// 16.str()
					call_method = true
					t.pos--
				} else {
					// 5.
					t.pos--
					fl := t.text[start..t.pos]
					mut d := reporter.err('float literals should have a digit after the decimal point',
						t.current_pos())
					d.add_help('use `${fl}.0` instead of `${fl}`')
					d.report()
					t.pos++
				}
			}
		}
		// exponential part
		mut has_exp := false
		if t.pos < t.text.len && t.text[t.pos] in [`e`, `E`] {
			kind = .float
			has_exp = true
			t.pos++
			if t.pos < t.text.len && t.text[t.pos] in [`-`, `+`] {
				t.pos++
			}
			for t.pos < t.text.len {
				c := t.text[t.pos]
				if !c.is_digit() {
					if !c.is_letter() {
						// 6e6.str()
						if c == `.` && t.pos + 1 < t.text.len && t.text[t.pos + 1].is_letter() {
							call_method = true
						}
						break
					} else {
						reporter.err('this number has unsuitable digit `${c.ascii_str()}`',
							t.current_pos()).report()
					}
				}
				t.pos++
			}
		}
		if t.text[t.pos - 1] in [`e`, `E`] {
			t.pos--
			reporter.err('exponent has no digits', t.current_pos()).report()
			t.pos++
		} else if t.pos < t.text.len && t.text[t.pos] == `.` && !is_range && !call_method {
			t.pos--
			if has_exp {
				reporter.err('exponential part should be integer', t.current_pos()).report()
			} else {
				reporter.err('too many decimal points in number', t.current_pos()).report()
			}
			t.pos++
		}
	}
	lit := t.text[start..t.pos]
	// decimal literals starting with 0 are invalid, an octal literal should be used instead
	if mode == .dec && lit.len > 1 && lit[0] == `0` {
		old_pos := t.pos
		t.pos = start
		mut d := reporter.err('zeros are not allowed at the beginning of a decimal literal',
			t.current_pos())
		d.add_note('use the prefix `0o` to denote an octal number')
		d.report()
		t.pos = old_pos
	}
	t.pos-- // fix pos
	return lit, kind
}

fn (mut t Tokenizer) read_number() (string, token.Kind) {
	return t.read_number_mode(match true {
		t.matches('0b', t.pos) { .bin }
		t.matches('0o', t.pos) { .oct }
		t.matches('0x', t.pos) { .hex }
		else { .dec }
	})
}

@[direct_array_access]
fn (mut t Tokenizer) read_char() string {
	start := t.pos
	// is_bytelit := t.pos > 0 && t.text[t.pos - 1] == `b`

	mut len := 0
	for {
		t.pos++
		if t.pos >= t.text.len {
			break
		}
		if t.text[t.pos] != backslash {
			len++
		}
		double_slash := t.matches('\\\\', t.pos - 2)
		if t.text[t.pos] == `'` && (t.text[t.pos - 1] != backslash || double_slash) {
			if double_slash {
				len++
			}
			break
		}
	}
	len--

	ch := t.text[start + 1..t.pos]
	if len == 0 {
		reporter.err('empty character literal', t.current_pos()).report()
	} else if len != 1 {
		mut d := reporter.err('character literal may only contain one codepoint', t.current_pos())
		d.add_help('if you meant to write a string literal, use double quotes')
		d.report()
	}
	return ch
}

@[direct_array_access]
fn (mut t Tokenizer) read_string() string {
	start_pos := t.current_pos()
	start := t.pos
	start_char := t.text[t.pos]
	is_raw := t.pos > 0 && t.text[t.pos - 1] == `r`
	// is_cstr := t.pos > 0 && t.text[t.pos - 1] == `c`
	mut backslash_count := if start_char == backslash { 1 } else { 0 }
	mut n_cr_chars := 0
	for {
		t.pos++
		if t.pos >= t.text.len {
			t.pos = start
			reporter.err('unfinished string literal', start_pos).report()
			return ''
		}
		c := t.text[t.pos]
		if c == backslash {
			backslash_count++
		}
		// end of string
		if c == `"` && (is_raw || backslash_count & 1 == 0) {
			break // handle `\\` at the end
		}
		if c == cr {
			n_cr_chars++
		}
		if c == lf {
			t.inc_line_number()
		}
		if c != backslash_count {
			backslash_count = 0
		}
	}
	mut lit := ''
	if start <= t.pos {
		lit = t.text[start + 1..t.pos]
		if n_cr_chars > 0 {
			lit = lit.replace('\r', '')
		}
	}
	return lit
}
