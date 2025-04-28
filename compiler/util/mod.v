// Copyright (C) 2024-present The Rivet programming language. Use of this source code
// is governed by an MIT license that can be found in the LICENSE file.

module util

import os

@[inline]
pub fn get_rivet_files(from string) []string {
	return os.walk_ext(from, '.ri')
}

@[inline]
pub fn is_valid_name(c u8) bool {
	return c == `_` || c.is_letter()
}

@[inline]
pub fn numeric_value_has_prefix(value string) bool {
	return value.len > 2 && value[..2] !in ['0x', '0o', '0b']
}
