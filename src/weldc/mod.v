// Copyright (C) 2024 The Weld programming language. Use of this source
// code is governed by an MIT license that can be found in the LICENSE file.

module weldc

import weldc.context
import weldc.parser
import weldc.importer
import weldc.sema

pub fn run(args []string) {
	mut ctx := context.new(context.parse_args(args))

	mut imp := importer.new(ctx)
	mut root_pkg := imp.import_root_pkg()
	ctx.root_name = root_pkg.name

	mut p := parser.new(ctx)
	p.parse(mut root_pkg)
	ctx.abort_if_errors()

	if !ctx.options.check_syntax {
		mut s := sema.new(ctx)
		s.analyze(p, imp)
		ctx.abort_if_errors()
	}
}
