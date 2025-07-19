// Copyright (C) 2024 The Rivet programming language. Use of this source
// code is governed by an MIT license that can be found in the LICENSE file.

module context

import os
import flag
import rivetc.reporter

@[footer: 'The compiler expects an input, either file or directory (if directory, it must contain a file entry `src/main.ri`).']
@[xdoc: 'The Rivet programming language compiler']
@[name: 'rivetc']
@[version: '0.1.0']
pub struct Options {
pub mut:
	input string @[ignore]

	show_help    bool @[long: help; short: h; xdoc: 'Print help information.']
	check_syntax bool @[xdoc: 'Only parse the files, but then stop.']

	is_verbose bool @[long: verbose; short: v; xdoc: 'Enable verbosity in the compiler while compiling.']
}

@[inline]
pub fn parse_args(args []string) Options {
	mut options, remaining := flag.to_struct[Options](args) or { reporter.ic_error(err.msg()) }

	if options.show_help {
		eprintln(flag.to_doc[Options]() or { reporter.ic_error(err.msg()) })
		exit(0)
	}

	if remaining.len == 1 {
		input := remaining[0]
		if os.is_file(input) || os.is_dir(input) {
			options.input = input
		} else {
			reporter.ic_error('`${input}` is not a valid input, expected directory or file')
		}
	} else if remaining.len == 0 {
		reporter.ic_error('at least one input was expected')
	} else {
		reporter.ic_error('only one input is expected')
	}

	return options
}
