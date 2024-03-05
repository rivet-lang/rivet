# Copyright (C) 2023 Jose Mendoza. All rights reserved.
# Use of this source code is governed by an MIT license that can
# be found in the LICENSE file.

import os

from .. import prefs, utils

from .ir import InstKind
from . import ir, c_headers

MIN_INT64 = -9223372036854775808

# NOTE: some of the words in `C_RESERVED` are not reserved in C, but are
# in C++, thus need escaping too. `small` should not be needed, but see
# https://stackoverflow.com/questions/5874215/what-is-rpcndr-h
C_RESERVED = [
    'auto', 'bool', 'case', 'char', 'complex', 'default', 'delete', 'do',
    'double', 'export', 'float', 'goto', 'inline', 'int', 'long', 'namespace',
    'new', 'register', 'restrict', 'short', 'signed', 'sizeof', 'small',
    'static', 'typedef', 'typename', 'union', 'unsigned', 'void', 'volatile',
    'template', 'far', 'near', 'huge', 'linux', 'unix'
]

def c_escape(kw):
    return f"_{kw}_" if kw in C_RESERVED else kw

class CGen:
    def __init__(self, comp):
        self.comp = comp
        self.typedefs = utils.Builder()
        self.types = utils.Builder()
        self.protos = utils.Builder()
        self.globals = utils.Builder()
        self.out = utils.Builder()

    def gen(self, out_rir):
        self.comp.vlog("cgen: generating types...")
        self.gen_types(out_rir.types)
        self.comp.vlog("cgen: generating externs...")
        self.gen_externs(out_rir.externs)
        self.comp.vlog("cgen: generating globals...")
        self.gen_globals(out_rir.globals)
        self.comp.vlog("cgen: generating decls...")
        self.gen_decls(out_rir.decls)

        self.comp.vlog("cgen: generating C file...")
        c_file = f"module.{self.comp.prefs.mod_name}.c"
        with open(c_file, "w+") as out:
            out.write(c_headers.HEADER)
            if self.comp.prefs.build_mode != prefs.BuildMode.Release:
                out.write(c_headers.RIVET_BREAKPOINT)
            out.write(str(self.typedefs).strip() + "\n\n")
            out.write(str(self.types).strip() + "\n\n")
            out.write(str(self.protos).strip() + "\n\n")
            out.write(str(self.globals).strip() + "\n\n")
            out.write(str(self.out).strip())

        self.comp.vlog("cgen: generating C compiler arguments...")
        args = [
            self.comp.prefs.target_backend_compiler, "-o",
            self.comp.prefs.mod_output, "-Werror", "-fno-builtin", "-fwrapv",
            "-m64" if self.comp.prefs.target_bits == prefs.Bits.X64 else "-m32",
        ]
        if self.comp.prefs.build_mode == prefs.BuildMode.Release:
            args.append("-flto")
            args.append("-O3")
        else:
            args.append("-g")
        if self.comp.prefs.target_os == prefs.OS.Windows:
            args.append(f"-municode")
        for l in self.comp.prefs.library_path:
            args.append(f"-L{l}")
        for f in self.comp.prefs.flags:
            args.append(f"-D{f}")
        args.append(c_file)
        for obj in self.comp.prefs.objects_to_link:
            args.append(obj)
        for l in self.comp.prefs.libraries_to_link:
            args.append(f"-l{l}")
        self.comp.vlog(f"C compiler arguments: {' '.join(args)}")

        self.comp.vlog("cgen: compiling C file...")
        res = utils.execute(*args)
        if res.exit_code == 0:
            if not self.comp.prefs.keep_c:
                os.remove(c_file)
        else:
            utils.error(
                f"error while compiling the output C file `{c_file}`:\n{res.err}"
            )

    def write(self, txt):
        self.out.write(txt)

    def writeln(self, txt = ""):
        self.out.writeln(txt)

    def gen_types(self, types):
        for s in types:
            if isinstance(s, ir.Struct):
                self.typedefs.writeln(f"typedef struct {s.name} {s.name};")
                if not s.is_opaque:
                    self.types.writeln(f"struct {s.name} {{")
                    for i, f in enumerate(s.fields):
                        f_name = c_escape(f.name)
                        self.types.write("  ")
                        self.types.write(self.gen_type(f.typ, f_name))
                        if not isinstance(f.typ, (ir.Array, ir.Function)):
                            self.types.write(f" {f_name}")
                        self.types.writeln(";")
                    self.types.writeln("};")
                self.types.writeln()
            else:
                self.typedefs.writeln(f"typedef union {s.name} {s.name};")
                self.types.writeln(f"union {s.name} {{")
                for i, f in enumerate(s.fields):
                    f_name = c_escape(f.name)
                    self.types.write("  ")
                    self.types.write(self.gen_type(f.typ, f_name))
                    if not isinstance(f.typ, (ir.Array, ir.Function)):
                        self.types.write(f" {f_name}")
                    self.types.writeln(";")
                self.types.writeln("};\n")

    def gen_externs(self, externs):
        for extern_fn in externs:
            self.gen_fn_decl(extern_fn)

    def gen_globals(self, globals):
        for g in globals:
            if not g.is_public:
                self.globals.write("RIVET_LOCAL ")
            if g.is_extern:
                self.globals.write("extern ")
            if isinstance(g.typ, ir.Array):
                self.globals.write(self.gen_type(g.typ, g.name))
            else:
                self.globals.write(self.gen_type(g.typ))
                self.globals.write(" ")
                self.globals.write(g.name)
            self.globals.writeln(";")

    def gen_decls(self, decls):
        for decl in decls:
            if isinstance(decl, ir.FuncDecl):
                self.gen_fn_decl(decl)
            else:
                self.gen_vtable(decl)
            self.writeln()

    def gen_vtable(self, decl):
        self.globals.writeln(
            f"static {decl.structure} {decl.name}[{decl.implement_nr}] = {{"
        )
        for i, ft in enumerate(decl.funcs):
            self.globals.writeln('  {')
            items = ft.items()
            for i2, (f, impl) in enumerate(items):
                self.globals.write(f'    .{f} = (void*){impl}')
                if i2 < len(items) - 1:
                    self.globals.writeln(", ")
                else:
                    self.globals.writeln()
            self.globals.write("  }")
            if i < len(decl.funcs) - 1:
                self.globals.writeln(",")
            else:
                self.globals.writeln()
        self.globals.writeln("};")

    def gen_fn_decl(self, decl):
        if decl.is_never:
            if not decl.is_extern:
                self.write("RIVET_NEVER ")
            self.protos.write("RIVET_NEVER ")
        if not decl.is_extern:
            if decl.is_public:
                self.write("RIVET_EXPORT ")
                self.protos.write("RIVET_EXPORT ")
            else:
                self.write("RIVET_LOCAL ")
                self.protos.write("RIVET_LOCAL ")
        if decl.attrs.has("inline") and not decl.is_extern:
            self.write("inline ")
        if isinstance(decl.ret_typ, ir.Function):
            ret_typ = self.gen_type(decl.ret_typ.ret_typ) + " (*"
        else:
            ret_typ = self.gen_type(decl.ret_typ)
        self.protos.write(f"{ret_typ} {decl.name}(")
        if not decl.is_extern:
            self.write(f"{ret_typ} {decl.name}(")
        if len(decl.args) == 0:
            if not decl.is_extern:
                self.write("void")
            self.protos.write("void")
        else:
            for i, arg in enumerate(decl.args):
                arg_typ = self.gen_type(arg.typ, arg.name)
                self.protos.write(arg_typ)
                if not decl.is_extern:
                    self.write(arg_typ)
                if not isinstance(arg.typ, (ir.Array, ir.Function)):
                    self.protos.write(f" {c_escape(arg.name)}")
                    if not decl.is_extern:
                        self.write(f" {c_escape(arg.name)}")
                if i < len(decl.args) - 1:
                    self.protos.write(", ")
                    if not decl.is_extern:
                        self.write(", ")
            if decl.is_variadic:
                if len(decl.args) > 0:
                    if not decl.is_extern:
                        self.write(", ")
                    self.protos.write(", ")
                if not decl.is_extern:
                    self.write("...")
                self.protos.write("...")
        if isinstance(decl.ret_typ, ir.Function):
            self.protos.write(")) (")
            for i, arg in enumerate(decl.ret_typ.args):
                self.protos.write(self.gen_type(arg))
                if i < len(decl.ret_typ.args) - 1:
                    self.protos.write(", ")
        self.protos.writeln(");")
        if not decl.is_extern:
            if isinstance(decl.ret_typ, ir.Function):
                self.write(") (")
                for i, arg in enumerate(decl.ret_typ.args):
                    self.write(self.gen_type(arg))
                    if i < len(decl.ret_typ.args) - 1:
                        self.write(", ")
            self.writeln(") {")
            self.gen_instrs(decl.instrs)
            if decl.is_never:
                self.writeln("  while (1);")
            self.writeln("}")

    def gen_instrs(self, insts):
        for inst in insts:
            if isinstance(inst, ir.Label):
                self.writeln()
            else:
                self.write("  ")
            if isinstance(inst, ir.Skip):
                continue # skip
            elif isinstance(inst, ir.Comment):
                self.writeln(f"/* {inst.text} */")
            elif isinstance(inst, ir.Label):
                self.writeln(f"{inst.label}: ;")
            elif isinstance(inst, ir.Inst):
                self.gen_inst(inst)
                if inst.kind == InstKind.DbgStmtLine:
                    self.writeln()
                elif inst.kind != InstKind.Nop:
                    self.writeln(";")

    def gen_inst(self, inst):
        if inst.kind == InstKind.Nop:
            self.write("/* NOP */")
        elif inst.kind == InstKind.Alloca:
            name = inst.args[0].name
            typ = inst.args[0].typ
            self.write_type(typ, name)
            if not isinstance(typ, (ir.Function, ir.Array)):
                self.write(" ")
                self.gen_expr(inst.args[0])
            if len(inst.args) == 2:
                self.write(" = ")
                self.gen_expr(inst.args[1])
        elif inst.kind in (InstKind.Store, InstKind.StorePtr):
            arg0 = inst.args[0]
            arg1 = inst.args[1]
            if inst.kind == InstKind.StorePtr:
                self.write("(*(")
            self.gen_expr(arg0)
            if inst.kind == InstKind.StorePtr:
                self.write("))")
            self.write(" = ")
            self.gen_expr(arg1)
        elif inst.kind == InstKind.LoadPtr:
            self.write("(*(")
            self.gen_expr(inst.args[0])
            self.write("))")
        elif inst.kind == InstKind.GetElementPtr:
            self.write("(")
            self.gen_expr(inst.args[0])
            self.write(" + ")
            self.gen_expr(inst.args[1])
            self.write(")")
        elif inst.kind == InstKind.GetPtr:
            arg0 = inst.args[0]
            if isinstance(arg0, (ir.Ident, ir.Selector, ir.ArrayLit)):
                if isinstance(arg0, ir.ArrayLit):
                    self.gen_expr(arg0)
                else:
                    self.write("(&(")
                    self.gen_expr(arg0)
                    self.write("))")
            else:
                self.write(f"({self.gen_type(arg0.typ)}[]){{ ")
                self.gen_expr(arg0)
                self.write(" }")
        elif inst.kind == InstKind.Cast:
            self.write("((")
            self.gen_expr(inst.args[1])
            self.write(")(")
            self.gen_expr(inst.args[0])
            self.write("))")
        elif inst.kind == InstKind.Cmp:
            self.gen_expr(inst.args[1])
            self.write(" ")
            self.gen_expr(inst.args[0])
            self.write(" ")
            self.gen_expr(inst.args[2])
        elif inst.kind == InstKind.DbgStmtLine:
            self.write(f'#line {inst.args[1].name} "{inst.args[0].name}"')
        elif inst.kind == InstKind.Breakpoint:
            self.write("RIVET_BREAKPOINT")
        elif inst.kind in (
            InstKind.Add, InstKind.Sub, InstKind.Mult, InstKind.Div,
            InstKind.Mod, InstKind.BitAnd, InstKind.BitOr, InstKind.BitXor,
            InstKind.Lshift, InstKind.Rshift
        ):
            self.gen_expr(inst.args[0])
            if inst.kind == InstKind.Add: self.write(" + ")
            elif inst.kind == InstKind.Sub: self.write(" - ")
            elif inst.kind == InstKind.Mult: self.write(" * ")
            elif inst.kind == InstKind.Div: self.write(" / ")
            elif inst.kind == InstKind.Mod: self.write(" % ")
            elif inst.kind == InstKind.BitAnd: self.write(" & ")
            elif inst.kind == InstKind.BitOr: self.write(" | ")
            elif inst.kind == InstKind.BitXor: self.write(" ^ ")
            elif inst.kind == InstKind.Lshift: self.write(" << ")
            elif inst.kind == InstKind.Rshift: self.write(" >> ")
            self.gen_expr(inst.args[1])
        elif inst.kind in (InstKind.Inc, InstKind.Dec):
            self.gen_expr(inst.args[0])
            if inst.kind == InstKind.Inc:
                self.write("++")
            else:
                self.write("--")
        elif inst.kind in (InstKind.BitNot, InstKind.BooleanNot, InstKind.Neg):
            if inst.kind == InstKind.BooleanNot:
                self.write("!")
            elif inst.kind == InstKind.Neg:
                self.write("-")
            else:
                self.write("~")
            self.write("(")
            self.gen_expr(inst.args[0])
            self.write(")")
        elif inst.kind == InstKind.Br:
            if len(inst.args) == 1:
                self.write(f"goto {inst.args[0].name}")
            else:
                self.write("if (")
                self.gen_expr(inst.args[0])
                self.write(f") goto {inst.args[1].name}")
                if len(inst.args) == 3:
                    self.write(f"; else goto {inst.args[2].name}")
        elif inst.kind == InstKind.Call:
            self.gen_expr(inst.args[0])
            self.write("(")
            args = inst.args[1:]
            for i, arg in enumerate(args):
                self.gen_expr(arg)
                if i < len(args) - 1:
                    self.write(", ")
            self.write(")")
        elif inst.kind == InstKind.Ret:
            self.write("return")
            if len(inst.args) == 1:
                self.write(" ")
                self.gen_expr(inst.args[0])
        else:
            raise Exception(inst) # unreachable

    def gen_expr(self, expr):
        if isinstance(expr, ir.Skip):
            self.write("/* <skip> */")
        elif isinstance(expr, ir.Inst):
            self.gen_inst(expr)
        elif isinstance(expr, ir.NoneLit):
            self.write("((void*)0)")
        elif isinstance(expr, ir.IntLit):
            if expr.value() == MIN_INT64:
                # NOTE: `-9223372036854775808` is wrong because C compilers
                # parse literal values without sign first, and `9223372036854775808`
                # overflows `int64`, hence the consecutive subtraction by `1`.
                self.write("(-9223372036854775807L - 1)")
            else:
                self.write("((")
                self.write_type(expr.typ)
                self.write(")")
                self.write("(")
                self.write(expr.lit)
                if expr.typ.name.endswith("64"
                                          ) or expr.typ.name.endswith("size"):
                    if expr.typ.name.startswith("u"):
                        self.write("U")
                    self.write("L")
                self.write("))")
        elif isinstance(expr, ir.FloatLit):
            self.write(expr.lit)
            if str(expr.typ) == "float32":
                self.write("f")
        elif isinstance(expr, ir.RuneLit):
            self.write(f"L'{expr.lit}'")
        elif isinstance(expr, ir.StringLit):
            self.write(f'(uint8*)"{expr.lit}"')
        elif isinstance(expr, ir.ArrayLit):
            self.write("(")
            self.write_type(expr.typ)
            if not isinstance(expr.typ, ir.Array):
                self.write("[]")
            self.write("){ ")
            for i, e in enumerate(expr.elems):
                self.gen_expr(e)
                if i < len(expr.elems) - 1:
                    self.write(", ")
            self.write(" }")
        elif isinstance(expr, ir.Ident):
            self.write(c_escape(expr.name))
        elif isinstance(expr, ir.Name):
            self.write(c_escape(expr.name))
        elif isinstance(expr, ir.Selector):
            self.gen_expr(expr.left)
            if isinstance(expr.left.typ, ir.Ptr):
                self.write("->")
            else:
                self.write(".")
            self.write(c_escape(expr.name.name))
        else:
            self.write(self.gen_type(expr))

    def write_type(self, typ, wrap = ""):
        self.write(self.gen_type(typ, wrap))

    def gen_type(self, typ, wrap = ""):
        if isinstance(typ, ir.Ptr):
            return f"{self.gen_type(typ.typ, wrap)}*"
        elif isinstance(typ, ir.Array):
            sizes = []
            p_typ = typ
            is_arr_of_fns = False
            while isinstance(p_typ, ir.Array):
                sizes.append(p_typ.size)
                if isinstance(p_typ.typ, ir.Function):
                    is_arr_of_fns = True
                    p_typ = p_typ.typ
                    break
                p_typ = p_typ.typ
            if is_arr_of_fns and len(sizes) > 0:
                sizes.reverse()
                return self.gen_type(
                    p_typ, f"{wrap}{''.join([f'[{s}]' for s in sizes])}"
                )
            sb = utils.Builder()
            sb.write(self.gen_type(typ.typ, wrap))
            if not isinstance(typ.typ, ir.Array):
                sb.write(f" {wrap}")
            sb.write(f"[{typ.size}]")
            return str(sb)
        elif isinstance(typ, ir.Function):
            sb = utils.Builder()
            sb.write(self.gen_type(typ.ret_typ))
            sb.write(" (*")
            if len(wrap) > 0:
                sb.write(wrap)
            sb.write(")(")
            if len(typ.args) == 0:
                sb.write("void")
            else:
                for i, arg in enumerate(typ.args):
                    sb.write(self.gen_type(arg))
                    if i < len(typ.args) - 1:
                        sb.write(", ")
            sb.write(")")
            return str(sb)
        return str(typ)
