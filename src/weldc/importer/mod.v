// Copyright (C) 2024 The Weld programming language. Use of this source
// code is governed by an MIT license that can be found in the LICENSE file.

module importer

import os
import weldc.ast
import weldc.context
import weldc.reporter

pub struct Importer {
pub mut:
	ctx &context.Context
}

pub struct ImportedMod {
pub:
	name     string
	is_pkg   bool
	pkg_name string
	files    []&ast.File
}

pub fn new(ctx &context.Context) &Importer {
	return &Importer{
		ctx: ctx
	}
}

@[inline]
pub fn (mut imp Importer) import_root_pkg() ImportedMod {
	return imp.import_module(imp.ctx.options.input, true, imp.ctx.options.input)
}

// The input the compiler receives can be a file or a directory. If it's a file, the
// module name will be the same as the file, and if it's a directory, the name will
// be the same as the directory.
// Files are sorted alphabetically and by priority.
pub fn (mut imp Importer) import_module(dir_name string, is_pkg bool, pkg_name string) ImportedMod {
	mod_name := get_mod_name(dir_name)
	pkg_name_ := get_mod_name(pkg_name)

	imp.ctx.log('${@METHOD}("${mod_name}", ${is_pkg}, "${pkg_name_}")')

	if !mod_name.is_identifier() {
		kind := if is_pkg { 'package' } else { 'module' }
		reporter.ic_error('`${mod_name}` is not a valid ${kind} name')
	}

	input_files := get_weld_files(dir_name)
	if input_files == [] {
		reporter.ic_error("directory `${dir_name}` doesn't contains Weld source files")
	}

	mut files := []&ast.File{}
	for filename in input_files {
		mut f := ast.File.new(filename)
		f.mod_name = mod_name
		f.is_pkg = is_pkg
		f.priority = match os.base(filename) {
			'pkg.wd' { 2 }
			'mod.wd' { 1 }
			else { 0 }
		}
		files << f
	}
	files.sort(a.priority > b.priority)

	return ImportedMod{
		name:     mod_name
		is_pkg:   is_pkg
		pkg_name: pkg_name_
		files:    files
	}
}

@[inline]
pub fn get_mod_name(dir_name string) string {
	if os.is_file(dir_name) || os.is_dir(dir_name) {
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
	return dir_name
}

@[inline]
pub fn get_weld_files(from string) []string {
	if os.is_file(from) {
		return [from]
	}
	return os.ls(from) or { [] }.filter(it.ends_with('.wd'))
}
