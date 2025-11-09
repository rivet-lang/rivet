// Copyright (C) 2024 The Weld programming language. Use of this source
// code is governed by an MIT license that can be found in the LICENSE file.

module ice

import term

const ice_txt = term.bold(term.red('internal compiler error:'))

@[noreturn]
pub fn ice(msg string) {
	eprintln('${ice_txt} ${term.bold(msg)}')
	eprintln("You've discovered a bug in the Weld compiler. Please report this issue to the GitHub repository.")
	eprintln(term.italic('\nStacktrace:'))
	print_backtrace()
	exit(102)
}
