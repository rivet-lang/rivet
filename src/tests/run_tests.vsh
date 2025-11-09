// Copyright (C) 2024 The Weld programming language. Use of this source
// code is governed by an MIT license that can be found in the LICENSE file.
import os
import term

// test.err.wd -> test.err.out
// test.ok.wd -> test.ok.out

const weldc = './bin/weldc'

if !os.exists(weldc) {
	panic('`${weldc}` executable not found')
}

mut passed := 0
mut failed := 0

files := os.walk_ext('src/tests/', '.wd')
if files.len == 0 {
	return
}
for i, file in files {
	print(term.bold(term.cyan('  [${i + 1}/${files.len}] ')))
	print(file)
	mut test_passed := true
	is_err_out := file.ends_with('.err.wd')
	out_content := if is_err_out { os.read_file(file#[..-3] + '.out')! } else { '' }
	res := os.execute('${weldc} ${file}')
	res_out := res.output.trim_space()
	out_is_diff := res.exit_code != 0 && res_out != out_content
	if is_err_out {
		if res.exit_code == 0 {
			test_passed = false
		} else if out_is_diff {
			test_passed = false
		}
	} else {
		if res.exit_code == 0 || res_out.len == 0 {
			test_passed = true
		} else {
			test_passed = false
		}
	}
	if test_passed {
		println(term.bold(term.green(' .. PASSED')))
		passed++
	} else {
		println(term.bold(term.red(' .. FAILED')))
		failed++
		if is_err_out {
			println('Expected:\n${out_content}\n')
			if out_is_diff {
				println('Got:\n${res_out}')
			} else if res_out == '' {
				println('Got empty result')
			}
		} else {
			println('Expected clean compilation, got:\n${res_out}')
		}
	}
}

passed_str := term.green('${passed} passed')
failed_str := term.red('${failed} failed')
println(term.bold('Summary for all tests files: ${passed_str}, ${failed_str}, ${files.len} total.'))

if failed != 0 {
	exit(failed)
}
