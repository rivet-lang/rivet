# Copyright (C) 2024-present The Rivet programming language. Use of this source code
# is governed by an MIT license that can be found in the LICENSE file.

build:
	v -o bin/rivetc src/cmd

test: build
	v test src/cmd
	v tests/run_tests.vsh

fmt:
	v fmt -w .
