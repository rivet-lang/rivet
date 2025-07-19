// Copyright (C) 2024 The Rivet programming language. Use of this source
// code is governed by an MIT license that can be found in the LICENSE file.

module rivetc

import rivetc.context
import rivetc.parser
import rivetc.importer
import rivetc.sema

pub fn run(args []string) {
	mut ctx := &context.Context{}

	ctx.options = context.parse_args(args)

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
