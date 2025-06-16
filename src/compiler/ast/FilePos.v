// Copyright (C) 2024-present The Rivet programming language. Use of this source code
// is governed by an MIT license that can be found in the LICENSE file.

module ast

@[minify]
pub struct FileLoc {
pub:
	pos  int
	line int
	col  int
}

@[minify]
pub struct FilePos {
pub mut:
	file  &File = unsafe { nil }
	begin FileLoc
	end   FileLoc
}

pub fn (fp FilePos) == (fp2 FilePos) bool {
	// fast route: if the start and end location are different, then
	// we return `false`.
	if !(fp.begin == fp2.begin && fp.end == fp2.end) {
		return false
	}
	// otherwise, everything will depend on whether it is the same file.
	return fp.file == fp2.file
}

@[inline]
pub fn (fp FilePos) + (fp2 FilePos) FilePos {
	return fp.extend(fp2)
}

@[inline]
pub fn (fp FilePos) extend(end FilePos) FilePos {
	return FilePos{
		...fp
		end: end.end
	}
}

pub fn (fp &FilePos) contains(loc &FileLoc) bool {
	return match true {
		loc.line > fp.begin.line && loc.line < fp.end.line {
			true
		}
		loc.line == fp.begin.line && loc.line == fp.end.line {
			loc.col >= fp.begin.col && loc.col <= fp.end.col
		}
		loc.line == fp.begin.line {
			loc.col >= fp.begin.col
		}
		loc.line == fp.end.line {
			loc.col <= fp.end.col
		}
		else {
			false
		}
	}
}

pub fn (fp &FilePos) str() string {
	filename := if isnil(fp.file) { '<unknown-file>' } else { fp.file.filename }
	if fp.begin.line == fp.end.line {
		return '${filename}:${fp.begin.line + 1}:${fp.begin.col}'
	}
	return '${filename}:${fp.begin.line + 1}:${fp.begin.col}-${fp.end.line + 1}:${fp.end.col}'
}
