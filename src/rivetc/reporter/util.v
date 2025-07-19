// Copyright (C) 2024 The Rivet programming language. Use of this source
// code is governed by an MIT license that can be found in the LICENSE file.

module reporter

import term

fn bold(s string) string {
	if reporter_.colorize_output {
		return term.bold(s)
	}
	return s
}

fn blue(s string) string {
	if reporter_.colorize_output {
		return term.blue(s)
	}
	return s
}

fn cyan(s string) string {
	if reporter_.colorize_output {
		return term.cyan(s)
	}
	return s
}

fn magenta(s string) string {
	if reporter_.colorize_output {
		return term.magenta(s)
	}
	return s
}

fn green(s string) string {
	if reporter_.colorize_output {
		return term.green(s)
	}
	return s
}

fn yellow(s string) string {
	if reporter_.colorize_output {
		return term.yellow(s)
	}
	return s
}

fn red(s string) string {
	if reporter_.colorize_output {
		return term.red(s)
	}
	return s
}
