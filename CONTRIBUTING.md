# CONTRIBUTING

This document specifies how to contribute to the project in different ways.

## Reporting issues/Request feature

To report an issue or request a feature simply open an issue and select the 
appropriate template, then fill in the necessary information and that's it.

## Bootstrap compiler/Self-hosted compiler/Modify the libraries

To make a modification, fix a bug or add a new feature to the compiler, prior 
knowledge of consoles/terminals, the use of `git` and github is required.

### Bootstrap compiler

The bootstrap compiler is written in Python 3, therefore `python3` is required to 
run it (preferably version 3.11).

The compiler code is located in `rivetc/src`, it contains several modules for each 
part of the compiler:

* `__init__.py`: This is where all the code of the `Compiler` class is contained, 
    which executes everything. This module contains useful functions and module 
    loading.
* `report.py`: This module contains everything related to reporting compiler 
    errors/warnings.
* `utils.py`: Useful features are here. Also the current version of the compiler.
* `token.py`: This module defines the Tokens, which are generated by the Lexer to 
    be used later by the Parser. It also defines the keywords used by the compiler.
* `ast.py`: This module defines the AST (Abstract Syntax Tree) generated by the 
    Parser, which is then used by the rest of the compiler modules.
* `sym.py`: This module defines the symbols that the compiler generates from the 
    information obtained from the AST, such as modules, functions, types, etc.
    It also defines primitive types, such as `int32`, `bool`, etc.
* `type.py`: Everything related to the types are here. Pointers, References, Arrays, 
    etc.
* `prefs.py`: The parsing of the options passed to the compiler is executed in this 
    module, to then generate an object of type `Prefs`, which is used throughout 
    the compiler.
* `lexer.py`: The Lexer analyzes the files obtained when loading a module and generates 
    the corresponding tokens to then pass on to the Parser.
* `parser.py`: It parses the generated tokens and makes sure they have the correct 
    syntax, to generate the AST later.
* `register.py`: Registers the symbols that the user defines in the AST, such as types, 
    functions, etc.
* `resolver.py`: Resolves the use of symbols throughout the code and checks for their 
    existence.
* `checker.py`: Performs semantic and type compatibility checking throughout the code.
* `codegen/`: After going through the previous modules, you go to the codegen, where 
    the RIR (Rivet Intermediate Representation) is generated from the AST.
    * `__init__.py`: Generates the RIR from the AST.
    * `ir.py`: Defines the RIR used by the compiler.
    * `c.py`: Use the generated RIR to create the C code that will be compiled.
    * `c_headers.py`: It contains a useful header inserted into every generated C file.

To run the compiler, just run: `python3 rivetc`. For example, to see what options can 
be used and how to compile modules you can run: `python3 rivetc -h`.

To check that the compiler works as it should, run the following commands:

* `python3 tests/run_all.py`: Check that valid code compiles and runs successfully, 
    and invalid code gives the corresponding errors.

### Self-hosted compiler

TODO.

### Modify the libraries

The compiler comes with a number of libraries that are located in `lib/`:

* `c/`: Contains wrappers to the standard C library for both Linux and Windows.
* `core/`: This is the heart of Rivet, it contains the code that gives life to 
        the strings, vectors, the backtrace, etc.
* `std/`: The standard Rivet library, this module contains several submodules 
        with functions and types useful for development.
* `rivet/`: The self-hosted compiler code.

There are modules that contain tests that are executable using the `python3 rivetc -t` 
command, for example: `python3 rivetc -t lib/std/tests`.