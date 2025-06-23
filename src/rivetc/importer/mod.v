// Copyright (C) 2024-present The Rivet programming language. Use of this source code
// is governed by an MIT license that can be found in the LICENSE file.

module importer

import os
import rivetc.ast
import rivetc.util
import rivetc.context

pub struct Importer {
pub mut:
	ctx           &context.Context
	imported_mods []ImportedMod
}

pub struct ImportedMod {
pub:
	name   string
	is_pkg bool
	files  []&ast.File
}

pub fn new(ctx &context.Context) &Importer {
	return &Importer{
		ctx: ctx
	}
}

pub fn (mut imp Importer) import_root_pkg() ImportedMod {
	return imp.import_module(imp.ctx.options.input, true)
}

// The input the compiler receives can be a file or a directory. If it's a file, the
// module name will be the same as the file, and if it's a directory, the name will
// be the same as the directory.
// Files are sorted alphabetically and by priority.
pub fn (mut imp Importer) import_module(dir_name string, is_pkg bool) ImportedMod {
	imp.ctx.log(@METHOD)
	mod_name := get_mod_name(dir_name)

	input_files := util.get_rivet_files(dir_name)
	if input_files == [] {
		context.ic_error('the directory does not contain any Rivet source code files')
	}

	mut files := []&ast.File{}
	for filename in input_files {
		mut f := ast.File.new(filename)
		f.mod_name = mod_name
		f.is_pkg = is_pkg
		f.priority = match os.base(filename) {
			'pkg.ri' { 2 }
			'mod.ri' { 1 }
			else { 0 }
		}
		files << f
	}
	files.sort(b.priority < a.priority)

	return ImportedMod{
		name:   mod_name
		is_pkg: is_pkg
		files:  files
	}
}

@[inline]
pub fn get_mod_name(dir_name string) string {
	if os.is_file(dir_name) {
		_, mod_name, _ := os.split_path(dir_name)
		return mod_name.all_before('.')
	}
	return os.base(if dir_name == '.' {
		os.abs_path(dir_name)
	} else {
		dir_name
	})
}
