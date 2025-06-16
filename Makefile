# Copyright (C) 2024-present The Rivet programming language. Use of this source code
# is governed by an MIT license that can be found in the LICENSE file.

build:
	v -o bin/rivetc src/rivetc

test: build
	v test src/compiler
	v tests/run_tests.vsh

fmt:
	v fmt -w .
