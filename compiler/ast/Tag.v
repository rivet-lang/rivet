// Copyright (C) 2024-present The Rivet programming language. Use of this source code
// is governed by an MIT license that can be found in the LICENSE file.

module ast

pub struct TagArg {
pub:
	name  ?string
	value Expr
}

pub struct Tag {
pub:
	name string
	args []TagArg
}

pub struct Tags {
mut:
	tags []Tag
}

pub fn (mut tags Tags) add(name string, args []TagArg) ! {
	if _ := tags.find(name) {
		return error('duplicate tag `${name}`')
	}
	for arg in args {
		if arg.name != none {
			if args.count(it.name or { '' } == arg.name) != 1 {
				return error('`${name}` tag has duplicate `${arg.name}` argument')
			}
		}
	}
	tags.tags << Tag{name, args}
}

pub fn (tags &Tags) find(name string) ?Tag {
	for tag in tags.tags {
		if tag.name == name {
			return tag
		}
	}
	return none
}
