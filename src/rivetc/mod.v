// Copyright (C) 2024-present The Rivet programming language. Use of this source code
// is governed by an MIT license that can be found in the LICENSE file.

module rivetc

import rivetc.context
import rivetc.parser
import rivetc.sema

pub fn run(args []string) {
	mut ctx := &context.Context{}

	context.push(ctx)
	defer { context.pop() }

	ctx.options = context.parse_args(args)

	mut p := parser.new(ctx)
	p.parse()
	ctx.abort_if_errors()

	if !ctx.options.check_syntax {
		mut s := &sema.Sema{
			parser: p
		}
		s.analyze(ctx)
		ctx.abort_if_errors()
	}
}
