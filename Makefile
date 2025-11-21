# Copyright (C) 2024 The Weld programming language. Use of this source
# code is governed by an MIT license that can be found in the LICENSE
# file.

build:
	v -o bin/weldc src/weldc/cmd

build-prod:
	v -prod -o bin/weldc src/weldc/cmd

test: build
	v test src/weldc
	v run test/run_tests.vsh

gen-out-files:
	v run test/gen_out_files.vsh

fmt:
	v fmt -w .
