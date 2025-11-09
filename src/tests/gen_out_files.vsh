// Copyright (C) 2024 The Weld programming language. Use of this source
// code is governed by an MIT license that can be found in the LICENSE file.
import os
import term

const weldc = './bin/weldc'

if !os.exists(weldc) {
	panic('`${weldc}` executable not found')
}

files := os.walk_ext('src/tests/', '.wd')
if files.len == 0 {
	return
}

for file in files {
	out_file := file#[..-3] + '.out'
	if !file.ends_with('.err.wd') || os.is_file(out_file) {
		continue
	}
	println(term.bold('>> generating .out file for `${file}`'))
	res := os.execute('${weldc} ${file}')
	if res.exit_code != 0 {
		os.write_file(out_file, res.output.trim_space())!
	} else {
		println('   >> unexpected .exit_code == 0 for `${file}`')
	}
}
