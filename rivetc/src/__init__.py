# Copyright (C) 2023 Jose Mendoza. All rights reserved.
# Use of this source code is governed by an MIT license that can
# be found in the LICENSE file.

from os import path
import os, copy, glob

from . import (
    ast, sym, type, token, prefs, report, utils,

    # stages
    parser, register, resolver, checker, codegen
)

class Compiler:
    def __init__(self, args):
        #  `universe` is the mega-module where all the modules being
        #  compiled reside.
        self.universe = sym.universe()

        self.prefs = prefs.Prefs(args)
        self.pointer_size = 8 if self.prefs.target_bits == prefs.Bits.X64 else 4

        self.core_mod = None
        self.dyn_array_sym = None # from `core` module
        self.throwable_sym = None # from `core` module

        #  Primitive types.
        self.void_t = type.Type(self.universe[0])
        self.never_t = type.Type(self.universe[1])
        self.none_t = type.Type(self.universe[2])
        self.bool_t = type.Type(self.universe[3])
        self.rune_t = type.Type(self.universe[4])
        self.int8_t = type.Type(self.universe[5])
        self.int16_t = type.Type(self.universe[6])
        self.int32_t = type.Type(self.universe[7])
        self.int64_t = type.Type(self.universe[8])
        self.int_t = type.Type(self.universe[9])
        self.uint8_t = type.Type(self.universe[10])
        self.uint16_t = type.Type(self.universe[11])
        self.uint32_t = type.Type(self.universe[12])
        self.uint64_t = type.Type(self.universe[13])
        self.uint_t = type.Type(self.universe[14])
        self.comptime_int_t = type.Type(self.universe[15])
        self.comptime_float_t = type.Type(self.universe[16])
        self.float32_t = type.Type(self.universe[17])
        self.float64_t = type.Type(self.universe[18])
        self.string_t = type.Type(self.universe[19])
        self.rawptr_t = type.Ptr(self.void_t, True)
        self.boxedptr_t = type.Boxedptr()
        self.throwable_t = None # updated in register

        self.parsed_files = []
        self.source_files = []

        self.register = register.Register(self)
        self.resolver = resolver.Resolver(self)
        self.checker = checker.Checker(self)
        self.codegen = codegen.Codegen(self)

    def run(self):
        # if we are compiling the `core` module, avoid autoloading it
        if self.prefs.mod_name != "core":
            self.parsed_files += self.load_module(
                "core", "core", "", token.NO_POS
            )

        self.load_root_module()
        self.import_modules()

        if not self.prefs.check_syntax:
            self.vlog("registering symbols...")
            self.register.walk_files(self.source_files)
            if report.ERRORS > 0:
                self.abort()
            self.vlog("resolving symbols...")
            self.resolver.resolve_files(self.source_files)
            if report.ERRORS > 0:
                self.abort()
            self.vlog("checking files...")
            self.checker.check_files(self.source_files)
            if report.ERRORS > 0:
                self.abort()
            if not self.prefs.check:
                self.vlog("generating RIR...")
                self.codegen.gen_source_files(self.source_files)
                if report.ERRORS > 0:
                    self.abort()

    def import_modules(self):
        for sf in self.parsed_files:
            self.import_modules_from_decls(sf, sf.decls)
        self.resolve_deps()
        if report.ERRORS > 0:
            self.abort()

    def import_modules_from_decls(self, sf, decls):
        for decl in decls:
            if isinstance(decl, ast.ImportDecl):
                self.import_module(sf, decl)
            elif isinstance(decl, ast.ComptimeIf):
                ct_decls = self.evalue_comptime_if(decl)
                self.import_modules_from_decls(sf, ct_decls)

    def import_module(self, sf, decl):
        if len(decl.subimports) > 0:
            for subimport in decl.subimports:
                self.import_module(sf, subimport)
                subimport.id = id(subimport.mod_sym)
            return
        mod = self.load_module_files(decl.path, decl.alias, sf.file, decl.pos)
        if mod.found:
            if mod_sym_ := self.universe.find(mod.full_name):
                mod_sym = mod_sym_ # module already imported
            else:
                mod_sym = sym.Mod(False, mod.full_name)
                self.universe.add(mod_sym)
                self.parsed_files += parser.Parser(self).parse_mod(
                    mod_sym, mod.files
                )
            decl.alias = mod.alias
            decl.mod_sym = mod_sym

    def resolve_deps(self):
        g = self.import_graph()
        g_resolved = g.resolve()
        if self.prefs.is_verbose:
            utils.eprint("-----= resolved dependencies graph =-----")
            utils.eprint(g_resolved.display())
            utils.eprint("-----------------------------------------")
        cycles = g_resolved.display_cycles()
        if len(cycles) > 1:
            utils.error(
                f"import cycle detected between the following modules:\n{cycles}"
            )
        if self.prefs.is_verbose:
            utils.eprint("----------= imported modules =-----------")
            for node in g_resolved.nodes:
                utils.eprint(f" > {node.name}")
            utils.eprint("-----------------------------------------")
        for node in g_resolved.nodes:
            for fp in self.parsed_files:
                if not fp.sym:
                    continue
                if fp.sym.name == node.name:
                    self.source_files.append(fp)
        self.parsed_files.clear()

    def import_graph(self):
        g = utils.DepGraph()
        for fp in self.parsed_files:
            if not fp.sym:
                continue
            deps = []
            if fp.sym.name not in [
                "c.libc", "c", "c.ctypes", "core", "core.mem"
            ]:
                deps.append("core")
            self.import_graph_decls(fp, deps, fp.decls)
            g.add(fp.sym.name, deps)
        return g

    def import_graph_decls(self, fp, deps, decls):
        for d in decls:
            if isinstance(d, ast.ImportDecl):
                if len(d.subimports) > 0:
                    for subimport in d.subimports:
                        self.import_graph_mod(subimport, deps, fp)
                else:
                    self.import_graph_mod(d, deps, fp)
            elif isinstance(d, ast.ComptimeIf):
                self.import_graph_decls(fp, deps, self.evalue_comptime_if(d))

    def import_graph_mod(self, d, deps, fp):
        if not d.mod_sym:
            return # module not found
        if d.mod_sym.name == fp.sym.name:
            report.error("import cycle detected", d.pos)
            return
        deps.append(d.mod_sym.name)

    def load_root_module(self):
        if path.isdir(self.prefs.input):
            files = self.filter_files(
                glob.glob(path.join(self.prefs.input, "*.ri"))
            )
            src_dir = path.join(self.prefs.input, "src")
            if path.isdir(src_dir): # support `src/` directory
                files += self.filter_files(
                    glob.glob(path.join(src_dir, "*.ri"))
                )
            # if the `--test` option is used and a `tests` directory exists, try to
            # load files from that directory as well
            if self.prefs.build_mode == prefs.BuildMode.Test:
                tests_dir = path.join(self.prefs.input, "tests")
                if path.isdir(tests_dir):
                    files += self.filter_files(
                        glob.glob(path.join(tests_dir, "*.ri"))
                    )
        else:
            files = [self.prefs.input]
        if len(files) == 0:
            utils.error("no input received")
        root_sym = sym.Mod(False, self.prefs.mod_name)
        root_sym.is_root = True
        self.universe.add(root_sym)
        self.vlog("parsing root module files...")
        self.parsed_files += parser.Parser(self).parse_mod(root_sym, files)

    def load_module(self, pathx, alias, file_path, pos):
        mod = self.load_module_files(pathx, alias, file_path, pos)
        if mod.found:
            mod_sym = sym.Mod(False, mod.full_name)
            self.universe.add(mod_sym)
            self.vlog(f"parsing `{pathx}` module files...")
            return parser.Parser(self).parse_mod(mod_sym, mod.files)
        return []

    def load_module_files(self, pathx, alias, file_path, pos):
        found = False
        name = ""
        full_name = ""
        abspath = ""
        files = []
        is_super = pathx.startswith("..")
        if is_super or pathx.startswith("."):
            pathx2 = pathx[3 if is_super else 2:]
            name = pathx2[pathx2.rfind("/") + 1:]
            dirname = path.abspath(path.dirname(file_path))
            old_wd = os.getcwd()
            os.chdir(dirname)
            if path.isdir(pathx):
                found = True
                if len(name) == 0: # pathx == "." || pathx == ".."
                    name = path.basename(path.dirname(path.abspath(name)))
                abspath = path.abspath(pathx)
                mod_basedir = path.dirname(abspath)
                if mod_basedir.endswith("/src"):
                    mod_basedir = mod_basedir[:-4] # skip `src/`
                if "/src" in mod_basedir and not mod_basedir.endswith("/src"):
                    first_part = mod_basedir[:mod_basedir.rfind("/")]
                    mod_basedir = mod_basedir[:first_part.rfind("/")]
                names = abspath[mod_basedir.rfind("/") + 1:].split("/")
                if "src" in names:
                    src_idx = names.index("src")
                    full_name = ".".join([
                        *names[:src_idx], *names[src_idx + 1:]
                    ])
                else:
                    full_name = ".".join(names)
            os.chdir(old_wd)
            if found:
                files = self.filter_files(
                    glob.glob(path.join(path.relpath(abspath), "*.ri"))
                )
        else:
            name = pathx[pathx.rfind("/") + 1:]
            full_name = pathx.replace("/", ".")
            for l in self.prefs.library_path:
                mod_path = path.relpath(path.join(l, pathx))
                if path.isdir(mod_path):
                    found = True
                    files = self.filter_files(
                        glob.glob(path.join(mod_path, "*.ri"))
                    )
                # support `src/` directory
                if pathx.count("/") > 0:
                    slash_idx = pathx.find("/") + 1
                    src_dir = path.join(
                        l, pathx[:slash_idx], "src", pathx[slash_idx:]
                    )
                else:
                    src_dir = path.join(mod_path, "src")
                if path.isdir(src_dir):
                    if not found: found = True
                    files = self.filter_files(
                        glob.glob(path.join(src_dir, "*.ri"))
                    )
                if found:
                    break
        if not found:
            report.error(f"module `{pathx}` not found", pos)
        elif len(files) == 0:
            report.error(f"module `{pathx}` contains no rivet files", pos)
        return ast.ImportedMod(
            found, name, name if len(alias) == 0 else alias, full_name, files
        )

    def filter_files(self, inputs):
        new_inputs = []
        for input in inputs:
            basename_input = path.basename(input)
            if basename_input.count('.') == 1:
                new_inputs.append(input)
                continue
            exts = basename_input[:-3].split('.')[1:]
            should_compile = False
            already_exts = []
            for ext in exts:
                if ext in already_exts:
                    error(f"{input}: duplicate special extension `{ext}`")
                    continue
                already_exts.append(ext)
                if ext.startswith("d_") or ext.startswith("notd_"):
                    if ext.startswith("d_"):
                        should_compile = ext[2:] in self.prefs.flags
                    else:
                        should_compile = ext[5:] not in self.prefs.flags
                elif osf := prefs.OS.from_string(ext):
                    should_compile = self.prefs.target_os == osf
                elif arch := prefs.Arch.from_string(ext):
                    should_compile = self.prefs.target_arch == arch
                elif ext in ("x32", "x64"):
                    if ext == "x32":
                        should_compile = self.prefs.target_bits == Bits.X32
                    else:
                        should_compile = self.prefs.target_bits == Bits.X64
                elif ext in ("little_endian", "big_endian"):
                    if ext == "little_endian":
                        should_compile = self.prefs.target_endian == Endian.Little
                    else:
                        should_compile = self.prefs.target_endian == Endian.Big
                elif b := prefs.Backend.from_string(ext): # backends
                    should_compile = self.prefs.target_backend == b
                else:
                    error(f"{input}: unknown special extension `{ext}`")
                    break
                if not should_compile:
                    break
            if should_compile:
                new_inputs.append(input)
        return new_inputs

    # ========================================================

    def is_number(self, typ):
        return self.is_int(typ) or self.is_float(typ)

    def is_int(self, typ):
        return self.is_signed_int(typ) or self.is_unsigned_int(typ)

    def is_signed_int(self, typ):
        return typ in (
            self.int8_t, self.int16_t, self.int32_t, self.int64_t, self.int_t,
            self.comptime_int_t
        )

    def is_unsigned_int(self, typ):
        return typ in (
            self.uint8_t, self.uint16_t, self.uint32_t, self.uint64_t,
            self.uint_t
        )

    def is_float(self, typ):
        return typ in (self.float32_t, self.float64_t, self.comptime_float_t)

    def is_comptime_number(self, typ):
        return typ == self.comptime_int_t or typ == self.comptime_float_t

    def comptime_number_to_type(self, typ):
        if typ == self.comptime_int_t:
            return self.int_t
        elif typ == self.comptime_float_t:
            return self.float64_t
        return typ

    def num_bits(self, typ):
        if self.is_int(typ):
            return self.int_bits(typ)
        return self.float_bits(typ)

    def int_bits(self, typ):
        typ_sym = typ.symbol()
        if typ_sym.kind == sym.TypeKind.ComptimeInt:
            return 75 # only for checker
        elif typ_sym.kind in (sym.TypeKind.Int8, sym.TypeKind.Uint8):
            return 8
        elif typ_sym.kind in (sym.TypeKind.Int16, sym.TypeKind.Uint16):
            return 16
        elif typ_sym.kind in (sym.TypeKind.Int32, sym.TypeKind.Uint32):
            return 32
        elif typ_sym.kind in (sym.TypeKind.Int64, sym.TypeKind.Uint64):
            return 64
        elif typ_sym.kind in (sym.TypeKind.Int, sym.TypeKind.Uint):
            return 32 if self.prefs.target_bits == prefs.Bits.X32 else 64
        else:
            return -1

    def float_bits(self, typ):
        typ_sym = typ.symbol()
        if typ_sym.kind == sym.TypeKind.Float32:
            return 32
        elif typ_sym.kind in (sym.TypeKind.Float64, sym.TypeKind.ComptimeFloat):
            return 64
        else:
            return -1

    # Returns the size and alignment (in bytes) of `typ`, similarly to
    # C's `sizeof(T)` and `_Alignof(T)`.
    def type_size(self, typ, raw_size = False):
        if isinstance(typ, (type.Result, type.Option)):
            return self.type_size(typ.typ, raw_size)
        elif isinstance(typ, type.Type) and typ.is_boxed and not raw_size:
            return self.pointer_size, self.pointer_size
        elif isinstance(typ, (type.Ptr, type.Func, type.Boxedptr)):
            return self.pointer_size, self.pointer_size
        elif isinstance(typ, type.DynArray):
            return self.type_symbol_size(self.dyn_array_sym)
        return self.type_symbol_size(typ.symbol(), raw_size)

    def type_symbol_size(self, sy, raw_size = False):
        if raw_size and sy.raw_size != -1:
            return sy.raw_size, sy.raw_align
        if sy.size != -1 and not raw_size:
            return sy.size, sy.align
        size, align = 0, 0
        if sy.kind in (
            sym.TypeKind.Placeholder, sym.TypeKind.Void, sym.TypeKind.None_,
            sym.TypeKind.Never
        ):
            pass
        elif sy.kind == sym.TypeKind.Trait:
            size, align = self.pointer_size * 3, self.pointer_size
            size += len(sy.fields) * self.pointer_size
        elif sy.kind == sym.TypeKind.Alias:
            size, align = self.type_size(sy.info.parent)
        elif sy.kind in (sym.TypeKind.Uint, sym.TypeKind.Int):
            size, align = self.pointer_size, self.pointer_size
        elif sy.kind in (
            sym.TypeKind.Int8, sym.TypeKind.Uint8, sym.TypeKind.Bool
        ):
            size, align = 1, 1
        elif sy.kind in (sym.TypeKind.Int16, sym.TypeKind.Uint16):
            size, align = 2, 2
        elif sy.kind in (
            sym.TypeKind.Int32, sym.TypeKind.Uint32, sym.TypeKind.Rune,
            sym.TypeKind.Float32
        ):
            size, align = 4, 4
        elif sy.kind in (
            sym.TypeKind.Int64, sym.TypeKind.Uint64, sym.TypeKind.Float64,
            sym.TypeKind.ComptimeFloat, sym.TypeKind.ComptimeInt
        ):
            size, align = 8, 8
        elif sy.kind == sym.TypeKind.Enum:
            if sy.info.is_tagged:
                total_size = self.pointer_size
                max_alignment = self.pointer_size
                for variant in sy.info.variants:
                    if variant.has_typ:
                        variant_size, alignment = self.type_size(variant.typ)
                        if alignment > max_alignment:
                            max_alignment = alignment
                        total_size = utils.round_up(
                            total_size, alignment
                        ) + variant_size
                size = utils.round_up(total_size, max_alignment)
                align = max_alignment
            else:
                size, align = self.type_size(sy.info.underlying_typ)
        elif sy.kind == sym.TypeKind.DynArray:
            elem_size, elem_align = self.type_size(self.dyn_array_sym)
        elif sy.kind == sym.TypeKind.Array:
            elem_size, elem_align = self.type_size(sy.info.elem_typ)
            size, align = int(sy.info.size.lit) * elem_size, elem_align
        elif sy.kind == sym.TypeKind.Slice:
            size, align = self.pointer_size * 3, self.pointer_size
        elif sy.kind in (
            sym.TypeKind.Struct, sym.TypeKind.Tuple, sym.TypeKind.String
        ):
            total_size = 0
            max_alignment = 0
            types = sy.info.types if sy.kind == sym.TypeKind.Tuple else list(
                map(lambda it: it.typ, sy.full_fields())
            )
            for ftyp in types:
                field_size, alignment = self.type_size(ftyp)
                if alignment > max_alignment:
                    max_alignment = alignment
                total_size = utils.round_up(total_size, alignment) + field_size
            size = utils.round_up(total_size, max_alignment)
            align = max_alignment
        else:
            raise Exception(
                f"Compiler.type_size(): unsupported type `{sy.qualname()}`"
            )
        if raw_size:
            sy.raw_size = size
            sy.raw_align = align
        else:
            sy.size = size
            sy.align = align
        return size, align

    def evalue_comptime_if(self, comptime_if):
        if comptime_if.branch_idx != None:
            return comptime_if.branches[comptime_if.branch_idx].nodes
        for i, branch in enumerate(comptime_if.branches):
            if branch.is_else and comptime_if.branch_idx == None:
                comptime_if.branch_idx = i
            elif cond := self.evalue_comptime_condition(branch.cond):
                if cond:
                    comptime_if.branch_idx = i
            if comptime_if.branch_idx != None:
                return comptime_if.branches[comptime_if.branch_idx].nodes
        return []

    def evalue_comptime_condition(self, cond):
        if isinstance(cond, ast.ParExpr):
            return self.evalue_comptime_condition(cond.expr)
        elif isinstance(cond, ast.BoolLiteral):
            return bool(cond.lit)
        elif isinstance(cond, ast.Ident):
            return self.evalue_comptime_ident(cond.name, cond.pos)
        elif isinstance(cond, ast.UnaryExpr) and cond.op == token.Kind.Bang:
            val = self.evalue_comptime_condition(cond.right)
            if val != None:
                return not val
            return None
        elif isinstance(cond, ast.BinaryExpr) and cond.op in [
            token.Kind.LogicalAnd, token.Kind.LogicalOr
        ]:
            left = self.evalue_comptime_condition(cond.left)
            if left != None:
                if cond.op == token.Kind.LogicalOr and left:
                    return True
                right = self.evalue_comptime_condition(cond.right)
                if right != None:
                    if cond.op == token.Kind.LogicalAnd:
                        return left and right
                    return right
                return None
            return None
        else:
            report.error("invalid comptime condition", cond.pos)
        return None

    def evalue_comptime_ident(self, name, pos):
        # operating systems
        if name in ("_LINUX_", "_WINDOWS_"):
            return self.prefs.target_os.equals_to_string(name)
        # architectures
        elif name in ("_X86_", "_AMD64_"):
            return self.prefs.target_arch.equals_to_string(name)
        # bits
        elif name in ("_x32_", "_x64_"):
            if name == "_x32_":
                return self.prefs.target_bits == prefs.Bits.X32
            return self.prefs.target_bits == prefs.Bits.X64
        # endian
        elif name in ("_LITTLE_ENDIAN_", "_BIG_ENDIAN_"):
            if name == "_LITTLE_ENDIAN_":
                return self.prefs.target_endian == prefs.Endian.Little
            return self.prefs.target_endian == prefs.Endian.Big
        # build modes
        elif name in ("_DEBUG_", "_RELEASE_", "_TESTS_"):
            if name == "_DEBUG_":
                return self.prefs.build_mode == prefs.BuildMode.Debug
            elif name == "_RELEASE_":
                return self.prefs.build_mode == prefs.BuildMode.Release
            return self.prefs.build_mode == prefs.BuildMode.Test
        elif name.startswith("_") and name.endswith("_"):
            report.error(f"unknown builtin flag: `{name}`", pos)
            return False
        return name in self.prefs.flags

    # ========================================================

    def vlog(self, msg):
        if self.prefs.is_verbose:
            utils.eprint(utils.bold(utils.green("[rivet-log]")), msg)

    def abort(self):
        if report.ERRORS == 1:
            msg = f"could not compile module `{self.prefs.mod_name}`, aborting due to previous error"
        else:
            msg = f"could not compile module `{self.prefs.mod_name}`, aborting due to {report.ERRORS} previous errors"
        if report.WARNS > 0:
            word = "warning" if report.WARNS == 1 else "warnings"
            msg += f"; {report.WARNS} {word} emitted"
        utils.error(msg)
        exit(1)
