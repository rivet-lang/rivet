// Copyright (C) 2024-present The Rivet programming language. Use of this source code
// is governed by an MIT license that can be found in the LICENSE file.

module context

import os
import flag
import compiler.util

@[footer: 'The compiler expects an input, either file or directory (if directory, it must contain a file entry `src/main.ri`).']
@[xdoc: 'The Rivet programming language compiler']
@[name: 'rivetc']
@[version: '0.1.0']
pub struct Options {
pub mut:
	input_dir   string   @[ignore]
	input_files []string @[ignore]

	show_help    bool @[long: help; short: h; xdoc: 'Print help information.']
	check_syntax bool @[xdoc: 'Only parse the files, but then stop.']
}

@[inline]
pub fn parse_args(args []string) Options {
	mut options, remaining := flag.to_struct[Options](args) or { ic_error(err.msg()) }

	if options.show_help {
		eprintln(flag.to_doc[Options]() or { ic_error(err.msg()) })
		exit(0)
	}

	if remaining.len == 1 {
		input := remaining[0]
		match true {
			os.is_file(input) {
				options.input_dir = os.dir(input)
				options.input_files = [input]
			}
			os.is_dir(input) {
				files := util.get_rivet_files(input)
				if files == [] {
					ic_error('the directory does not contain any Rivet source code files')
				}
				options.input_dir = input
				options.input_files = files
			}
			else {
				ic_error('`${input}` is not a valid input, expected directory')
			}
		}
	} else if remaining.len == 0 {
		ic_error('at least one input was expected')
	} else {
		ic_error('only one input is expected')
	}

	return options
}
