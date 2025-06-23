// Copyright (C) 2024-present The Rivet programming language. Use of this source code
// is governed by an MIT license that can be found in the LICENSE file.

module ast

import os

@[heap]
pub struct File {
pub:
	filename string
	content  string
pub mut:
	mod_name string
	priority int
	is_pkg   bool
	stmts    []Stmt
	scope    &Scope = unsafe { nil }
	errors   int
mut:
	lines ?[]string
}

@[inline]
pub fn (f File) == (f2 File) bool {
	return f.filename == f2.filename && f.mod_name == f2.mod_name && f.content == f2.content
}

pub fn File.new(filename string) &File {
	content := read_file(filename)
	return &File{
		filename: filename
		content:  content
	}
}

pub fn File.from_memory(content string) &File {
	return &File{
		filename: '<memory>'
		content:  content
		mod_name: '<memory>'
	}
}

pub fn (file &File) get_lines() []string {
	if file.lines != none {
		return file.lines
	}
	lines := file.content.split_into_lines()
	unsafe {
		file.lines = lines
	}
	return lines
}

pub fn (file &File) get_line(line int) ?string {
	lines := file.get_lines()
	return lines[line] or { none }
}

pub fn read_file(path string) string {
	return skip_bom(os.read_file(path) or {
		// we use `panic` because this should not happen
		panic(err.msg())
	})
}

pub fn skip_bom(file_content string) string {
	mut raw_text := file_content
	// BOM check
	if raw_text.len >= 3 {
		unsafe {
			c_text := raw_text.str
			if c_text[0] == 0xEF && c_text[1] == 0xBB && c_text[2] == 0xBF {
				// skip three BOM bytes
				offset_from_begin := 3
				raw_text = tos(c_text[offset_from_begin], vstrlen(c_text) - offset_from_begin)
			}
		}
	}
	return raw_text
}
