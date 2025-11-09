# Copyright (C) 2024 The Rivet programming language. Use of this source
# code is governed by an MIT license that can be found in the LICENSE
# file.

build:
	v -o bin/rivetc src/rivetc/cmd

build-prod:
	v -prod -o bin/rivetc src/rivetc/cmd

test: build
	v test src/rivetc
	v src/tests/run_tests.vsh

fmt:
	v fmt -w .
