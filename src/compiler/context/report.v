// Copyright (C) 2024-present The Rivet programming language. Use of this source code
// is governed by an MIT license that can be found in the LICENSE file.

module context

import term
import strings
import compiler.ast

pub struct Report {
mut:
	errors          int
	warnings        int
	colorize_output bool = term.can_show_color_on_stderr()
}

fn bold(s string) string {
	if get().report.colorize_output {
		return term.bold(s)
	}
	return s
}

fn blue(s string) string {
	if get().report.colorize_output {
		return term.blue(s)
	}
	return s
}

fn cyan(s string) string {
	if get().report.colorize_output {
		return term.cyan(s)
	}
	return s
}

fn green(s string) string {
	if get().report.colorize_output {
		return term.green(s)
	}
	return s
}

fn yellow(s string) string {
	if get().report.colorize_output {
		return term.yellow(s)
	}
	return s
}

fn red(s string) string {
	if get().report.colorize_output {
		return term.red(s)
	}
	return s
}

enum ReportType {
	fatal
	error
	warn
	note
}

fn (rt ReportType) colorize() string {
	return match rt {
		.fatal { red('fatal:') }
		.error { red('error:') }
		.warn { yellow('warning:') }
		.note { cyan('note:') }
	}
}

pub enum HintKind {
	note
	help
}

fn (hk HintKind) colorize() string {
	return bold(match hk {
		.note { cyan('note:') }
		.help { green('help:') }
	})
}

pub struct Hint {
pub:
	kind HintKind
	msg  string
	pos  ?ast.FilePos
}

@[inline]
pub fn note(msg string) Hint {
	return Hint{.note, msg, none}
}

@[inline]
pub fn help(msg string) Hint {
	return Hint{.help, msg, none}
}

@[params]
struct ReportParams {
	pos   ?ast.FilePos
	msg   string
	type  ReportType
	hints []Hint
}

const backtick = `\``

fn report_source(pos ast.FilePos, prefix string, mut sb strings.Builder) {
	border := bold(blue('      | '))
	for idx := pos.begin.line; idx <= pos.end.line; idx++ {
		if offending_line := pos.file.get_line(idx) {
			sb.writeln(border)
			sb.write_string(bold(blue('${pos.begin.line + 1:5d} | ')))
			sb.writeln(offending_line)
			sb.write_string(border)
			for jdx in 0 .. offending_line.len {
				if offending_line[jdx] == `\t` {
					sb.write_u8(`\t`)
					continue
				}

				mut caret := false
				if pos.begin.line == idx && pos.end.line == idx {
					if pos.begin.col <= jdx + 1 && jdx + 1 <= pos.end.col {
						caret = true
					}
				} else if pos.begin.line == idx && pos.begin.col <= jdx + 1 {
					caret = true
				} else if pos.begin.line < idx && idx < pos.end.line {
					caret = true
				} else if pos.end.line == idx && pos.end.col >= jdx + 1 {
					caret = true
				}

				if caret {
					if idx == pos.end.line && jdx == pos.end.col {
						break
					}
					if pos.begin.line == idx && pos.begin.col == jdx + 1 {
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
fn print_highlighted_message(msg string, mut sb strings.Builder) {
	mut start := 0
	mut cur := 0

	for cur < msg.len {
		if msg[cur] == backtick {
			sb.write_string(msg[start..cur])
			start = cur
			cur++

			for cur < msg.len && msg[cur] != backtick {
				cur++
			}

			if cur == msg.len {
				sb.write_string(msg[start..cur])
				start = cur
			} else {
				cur++
				sb.write_string(bold(blue(msg[start..cur])))
				start = cur
			}
		} else {
			cur++
		}
	}

	sb.write_string(msg[start..])
}

fn print_message(params ReportParams) {
	mut sb := strings.new_builder(params.msg.len)

	// file:line:column
	if params.pos != none {
		sb.write_string(bold(params.pos.str() + ':'))
		sb.write_u8(` `)
	}

	// error:|warn:|note:|help:
	sb.write_string(bold(params.type.colorize()))
	sb.write_u8(` `)

	// invalid character `\`
	print_highlighted_message(params.msg, mut sb)

	// 8 | '\'
	if params.pos != none {
		sb.write_u8(`\n`)
		report_source(params.pos, '', mut sb)
	}

	// help: remove invalid character
	for hint in params.hints {
		sb.write_u8(`\n`)
		eq := bold(blue('='))
		sb.write_string('${' ':6}${eq} ${hint.kind.colorize()} ')
		print_highlighted_message(hint.msg, mut sb)
		if hint.pos != none {
			// report_source()
		}
	}

	s := sb.str()
	if params.type == .fatal {
		panic(s)
	} else {
		eprintln(s)
	}
}

@[inline]
fn (r &Report) ic_note(msg string) {
	print_message(msg: msg, type: .note)
}

@[inline]
fn (r &Report) ic_warn(msg string) {
	print_message(msg: msg, type: .warn)
}

@[noreturn]
fn (r &Report) ic_error(msg string) {
	print_message(msg: msg, type: .error)
	exit(101)
}

@[noreturn]
fn (r &Report) ic_fatal(msg string) {
	print_message(msg: msg, type: .fatal)
	for {}
}

fn (mut r Report) warn(msg string, pos ast.FilePos, hints ...Hint) {
	r.warnings++
	print_message(pos: pos, msg: msg, type: .warn, hints: hints)
}

fn (mut r Report) error(msg string, pos ast.FilePos, hints ...Hint) {
	r.errors++
	unsafe {
		pos.file.errors++
	}
	print_message(pos: pos, msg: msg, type: .error, hints: hints)
}

// convenience methods calling on correct instance:

@[inline]
pub fn ic_note(msg string) {
	get().report.ic_note(msg)
}

@[inline]
pub fn ic_warn(msg string) {
	get().report.ic_warn(msg)
}

@[noreturn]
pub fn ic_error(msg string) {
	get().report.ic_error(msg)
}

@[noreturn]
pub fn ic_fatal(msg string) {
	get().report.ic_fatal(msg)
}

@[inline]
pub fn error(msg string, pos ast.FilePos, hints ...Hint) {
	mut r := &get().report
	r.error(msg, pos, ...hints)
}

@[inline]
pub fn warn(msg string, pos ast.FilePos, hints ...Hint) {
	mut r := &get().report
	r.warn(msg, pos, ...hints)
}
