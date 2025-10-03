<div align="center">

<img src="https://github.com/rivet-lang/logo/blob/main/logo.png" alt="Rivet logo" width="200" height="200"/>

# The Rivet programming language

A general-purpose programming language, focused on simplicity, safety and stability.

[Website](https://rivet-lang.github.io)
•
[Documentation](https://rivet-lang.github.io/docs)
•
[Roadmap](ROADMAP.md)
•
[Contributing](CONTRIBUTING.md)

![issues](https://img.shields.io/github/issues/rivet-lang/rivet?style=flat-square)
![status](https://img.shields.io/badge/status-alpha-blue?style=flat-square)
![license](https://img.shields.io/github/license/rivet-lang/rivet?style=flat-square)

</div>

Rivet's goal is to be a very powerful programming language and at the same time easy to use, 
whose syntax is inspired by Go, Zig, C# and other programming languages.

Rivet uses C as the only backend and generates C99 code that is compiled using a C compiler 
(by default, GCC or Clang). The idea is that in the long term there will be other backends 
available for code generation, such as LLVM or WebAssembly, and also that there will be an 
interpreter available.

> [!NOTE]
> Currently the language is in alpha state, and therefore its syntax and the language
> API is not stable, and may change in the long term. Not all features are implemented.
> 
> Compiler version 0.1.0 will be released when the self-hosted compiler can compile itself
> successfully.
> 
> Only Linux is supported for now, Windows and macOS are not supported yet. Any help to 
> provide full support for both Windows and macOS is welcome.
> 
> Read [CONTRIBUTING](CONTRIBUTING.md) to get more information.

You can find information on how to build Rivet on your computer by going to the
[documentation](https://rivet-lang.github.io/docs).
