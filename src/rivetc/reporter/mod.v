// Copyright (C) 2024 The Rivet programming language. Use of this source
// code is governed by an MIT license that can be found in the LICENSE file.

@[has_globals]
module reporter

import term
import strings
import rivetc.ast

__global reporter_ = Reporter{}

const margin = '   '

struct Reporter {
pub mut:
	errors int
mut:
	warnings        int
	diagnostics     []Diagnostic
	colorize_output bool = term.can_show_color_on_stderr()
}

pub fn report(d Diagnostic) {
	if d.severity == .err {
		reporter_.errors++
	} else {
		reporter_.warnings++
	}
	reporter_.diagnostics << d
}

pub fn print() {
	for d in reporter_.diagnostics {
		eprintln(d.renderize())
	}
}

pub enum Severity {
	err
	warn
}

@[inline]
pub fn (s Severity) label() string {
	return match s {
		.err { 'error' }
		.warn { 'warning' }
	}
}

@[inline]
pub fn (s Severity) colorize(str string) string {
	return match s {
		.err { red(str) }
		.warn { yellow(str) }
	}
}

struct Hint {
	msg     string
	pos     ?ast.FilePos
	is_help bool
}

@[inline]
pub fn (h Hint) label() string {
	return if h.is_help { 'help' } else { 'note' }
}

@[inline]
pub fn (h Hint) colorize(str string) string {
	return if h.is_help { cyan(str) } else { magenta(str) }
}

struct Diagnostic {
	severity Severity
	msg      string
	pos      ?ast.FilePos
mut:
	hints []Hint
}

@[inline]
pub fn diagnostic(severity Severity, msg string, pos ast.FilePos) Diagnostic {
	return Diagnostic{
		severity: severity
		msg:      msg
		pos:      pos
	}
}

@[inline]
pub fn err(msg string, pos ast.FilePos) Diagnostic {
	return Diagnostic{
		severity: .err
		msg:      msg
		pos:      pos
	}
}

@[inline]
pub fn warn(msg string, pos ast.FilePos) Diagnostic {
	return Diagnostic{
		severity: .warn
		msg:      msg
		pos:      pos
	}
}

@[inline]
pub fn (d Diagnostic) report() {
	unsafe {
		if d.pos != none {
			mut pos := &d.pos
			if d.severity == .err {
				pos.file.errors++
			}
		}
	}
	report(d)
}

@[params]
pub struct OptionalPos {
pub:
	pos ?ast.FilePos
}

pub fn (mut d Diagnostic) add_note(msg string, params OptionalPos) {
	d.hints << Hint{
		msg: msg
		pos: params.pos
	}
}

pub fn (mut d Diagnostic) add_help(msg string, params OptionalPos) {
	d.hints << Hint{
		msg:     msg
		pos:     params.pos
		is_help: true
	}
}

pub fn (d Diagnostic) renderize() string {
	mut sb := strings.new_builder(200)
	sb.write_string(bold(d.severity.colorize(d.severity.label() + ': ')))
	highlighted_message(d.msg, mut sb, true)
	sb.writeln('')
	if d.pos != none {
		renderize_position(d.pos, mut sb, false)
		sb.writeln('')
	}
	if d.hints != [] {
		eq := bold(blue('= '))
		for hint in d.hints {
			sb.write_string('${margin}${eq}${bold(hint.colorize(hint.label() + ':'))} ')
			highlighted_message(hint.msg, mut sb, false)
			sb.writeln('')
			if hint.pos != none {
				renderize_position(hint.pos, mut sb, true)
				sb.writeln('')
			}
		}
	}
	return sb.str().trim_space()
}

const backtick = `\``

fn renderize_position(pos ast.FilePos, mut sb strings.Builder, is_embed bool) {
	if is_embed {
		sb.write_string(margin)
	}
	sb.write_string(margin)
	sb.write_string(blue(bold('in ')))
	sb.writeln(pos.str())

	mut border := bold(blue('         |'))
	if is_embed {
		border = margin + border
	}
	for idx := pos.begin.line; idx <= pos.end.line; idx++ {
		if offending_line := pos.file.get_line(idx) {
			sb.writeln(border)
			if is_embed {
				sb.write_string(margin)
			}

			sb.write_string(bold(blue('  ${pos.begin.line + 1:6d} | ')))
			sb.writeln(offending_line)

			sb.write_string(border + ' ')
			start_column := int_max(0, int_min(pos.begin.col - 1, offending_line.len))
			end_column := int_max(0, int_min(pos.end.col, offending_line.len))
			for jdx in 0 .. offending_line.len {
				if offending_line[jdx] == `\t` {
					sb.write_u8(`\t`)
					continue
				}

				mut caret := false
				if pos.begin.line == idx && pos.end.line == idx {
					if start_column <= jdx && jdx <= end_column {
						caret = true
					}
				} else if pos.begin.line == idx && start_column <= jdx {
					caret = true
				} else if pos.begin.line < idx && idx < pos.end.line {
					caret = true
				} else if pos.end.line == idx && end_column >= jdx {
					caret = true
				}

				if caret {
					if idx == pos.end.line && jdx == end_column {
						break
					}
					if pos.begin.line == idx && start_column == jdx {
						sb.write_string(green(bold('^')))
					} else {
						sb.write_string(green(bold('~')))
					}
				} else {
					sb.write_u8(` `)
				}
			}
		}
	}
}

@[direct_array_access]
fn highlighted_message(msg string, mut sb strings.Builder, bold_s bool) {
	mut start := 0
	mut cur := 0
	mut sb2 := strings.new_builder(100)

	for cur < msg.len {
		if msg[cur] == backtick {
			sb2.write_string(msg[start..cur])
			start = cur
			cur++

			for cur < msg.len && msg[cur] != backtick {
				cur++
			}

			if cur == msg.len {
				sb2.write_string(msg[start..cur])
				start = cur
			} else {
				cur++
				s := blue(msg[start..cur])
				sb2.write_string(if bold_s { s } else { bold(s) })
				start = cur
			}
		} else {
			cur++
		}
	}

	sb2.write_string(msg[start..])
	sb.write_string(if bold_s {
		bold(sb2.str())
	} else {
		sb2.str()
	})
}

@[inline]
pub fn ic_warn(msg string) {
	eprint(Diagnostic{
		severity: .warn
		msg:      msg
	}.renderize())
}

@[noreturn]
pub fn ic_error(msg string) {
	eprint(Diagnostic{
		severity: .err
		msg:      msg
	}.renderize())
	exit(101)
}

@[noreturn]
pub fn ic_fatal(msg string) {
	eprint(Diagnostic{
		severity: .err
		msg:      msg
	}.renderize())
	exit(102)
}
