# Copyright (C) 2023 Jose Mendoza. All rights reserved.
# Use of this source code is governed by an MIT license that can
# be found in the LICENSE file.

from .sym import TypeKind
from . import ast, parser, sym, type, report, utils

class Register:
    def __init__(self, comp):
        self.comp = comp
        self.source_file = None
        self.abi = sym.ABI.Rivet
        self.sym = None
        self.is_core_mod = False

    def walk_files(self, source_files):
        for sf in source_files:
            self.is_core_mod = sf.sym.is_core_mod()
            if self.comp.core_mod == None and self.is_core_mod:
                self.comp.core_mod = sf.sym
            self.sym = sf.sym
            self.source_file = sf
            self.walk_decls(self.source_file.decls)
        self.comp.throwable_t = type.Type(self.comp.throwable_sym, True)

    def walk_decls(self, decls):
        for decl in decls:
            old_abi = self.abi
            old_sym = self.sym
            if isinstance(decl, ast.ComptimeIf):
                self.walk_decls(self.comp.evalue_comptime_if(decl))
            elif isinstance(decl, ast.ImportDecl):
                self.walk_import_decl(decl)
            elif isinstance(decl, ast.ExternDecl):
                self.abi = decl.abi
                self.walk_decls(decl.decls)
            elif isinstance(decl, ast.ConstDecl):
                decl.sym = sym.Const(
                    decl.is_public, decl.name, decl.typ, decl.expr
                )
                self.add_sym(decl.sym, decl.pos)
            elif isinstance(decl, ast.VarDecl):
                for v in decl.lefts:
                    try:
                        v_sym = sym.Var(
                            decl.is_public, v.is_mut, decl.is_extern, self.abi,
                            v.name, v.typ
                        )
                        v_sym.pos = decl.pos
                        self.source_file.sym.add(v_sym)
                        v.sym = v_sym
                    except utils.CompilerError as e:
                        report.error(e.args[0], v.pos)
            elif isinstance(decl, ast.AliasDecl):
                try:
                    if decl.is_typealias:
                        self.add_sym(
                            sym.Type(
                                decl.is_public, decl.name, TypeKind.Alias,
                                info = sym.AliasInfo(decl.parent), attributes=decl.attributes
                            ), decl.pos
                        )
                    else:
                        # updated later
                        decl.sym = sym.SymRef(
                            decl.is_public, decl.name, decl.parent
                        )
                        self.sym.add(decl.sym)
                except utils.CompilerError as e:
                    report.error(e.args[0], decl.pos)
            elif isinstance(decl, ast.TraitDecl):
                try:
                    decl.sym = self.sym.add_and_return(
                        sym.Type(
                            decl.is_public, decl.name, TypeKind.Trait,
                            info = sym.TraitInfo(), attributes=decl.attributes
                        )
                    )
                    if self.is_core_mod and decl.name == "Throwable" and not self.comp.throwable_sym:
                        self.comp.throwable_sym = decl.sym
                    self.sym = decl.sym
                    self.walk_decls(decl.decls)
                except utils.CompilerError as e:
                    report.error(e.args[0], decl.pos)
            elif isinstance(decl, ast.StructDecl):
                try:
                    if self.is_core_mod and decl.name == "string":
                        decl.sym = self.comp.string_t.sym
                    else:
                        decl.sym = self.sym.add_and_return(
                            sym.Type(
                                decl.is_public, decl.name, TypeKind.Struct,
                                info = sym.StructInfo(
                                    decl.is_opaque,
                                    is_boxed = decl.attributes.has("boxed")
                                ), attributes=decl.attributes
                            )
                        )
                        if self.is_core_mod and decl.name == "DynArray":
                            self.comp.dyn_array_sym = decl.sym
                    self.sym = decl.sym
                    self.walk_decls(decl.decls)
                except utils.CompilerError as e:
                    report.error(e.args[0], decl.pos)
            elif isinstance(decl, ast.EnumDecl):
                try:
                    info = sym.EnumInfo(
                        decl.underlying_typ, decl.is_tagged,
                        decl.attributes.has("boxed")
                    )
                    decl.sym = self.sym.add_and_return(
                        sym.Type(decl.is_public, decl.name, TypeKind.Enum, attributes=decl.attributes)
                    )
                    for variant in decl.variants:
                        if info.has_variant(variant.name):
                            report.error(
                                f"enum `{decl.name}` has duplicate variant `{variant.name}`",
                                decl.pos
                            )
                            continue
                        fields = list(
                            filter(
                                lambda d: isinstance(d, ast.FieldDecl),
                                variant.decls
                            )
                        )
                        if len(variant.decls) > 0:
                            variant_sym = decl.sym.add_and_return(
                                sym.Type(
                                    decl.is_public, variant.name,
                                    TypeKind.Struct,
                                    info = sym.StructInfo(False, False, True)
                                )
                            )
                            old_v_sym = self.sym
                            self.sym = variant_sym
                            self.walk_decls(variant.decls)
                            self.sym = old_v_sym
                            variant.typ = type.Type(variant_sym)
                        info.add_variant(
                            variant.name, variant.has_typ, variant.typ,
                            len(fields)
                        )
                    decl.sym.info = info
                    self.sym = decl.sym
                    self.walk_decls(decl.decls)
                except utils.CompilerError as e:
                    report.error(e.args[0], decl.pos)
            elif isinstance(decl, ast.FieldDecl):
                if self.sym.has_field(decl.name):
                    report.error(
                        f"{self.sym.typeof()} `{self.sym.name}` has duplicate field `{decl.name}`",
                        decl.pos
                    )
                else:
                    self.sym.fields.append(
                        sym.Field(
                            decl.name, decl.is_mut, decl.is_public, decl.typ,
                            decl.has_def_expr, decl.def_expr, decl.attributes
                        )
                    )
            elif isinstance(decl, ast.ExtendDecl):
                if isinstance(decl.typ, type.Type):
                    if decl.typ.sym != None:
                        self.sym = decl.typ.sym
                    elif isinstance(decl.typ.expr, ast.Ident):
                        if typ_sym := self.sym.find(decl.typ.expr.name):
                            self.sym = typ_sym
                        else:
                            self.sym = self.sym.add_and_return(
                                sym.Type(
                                    False, decl.typ.expr.name,
                                    TypeKind.Placeholder
                                )
                            )
                    else:
                        report.error(
                            f"invalid type `{decl.typ}` to extend", decl.pos
                        )
                        continue
                    self.walk_decls(decl.decls)
                else:
                    report.error(
                        f"invalid type `{decl.typ}` to extend", decl.pos
                    )
            elif isinstance(decl, ast.FuncDecl):
                try:
                    decl.sym = self.sym.add_and_return(
                        sym.Func(
                            self.abi, decl.is_public, decl.is_extern,
                            decl.is_unsafe, decl.is_method, decl.is_variadic,
                            decl.name, decl.args, decl.ret_typ,
                            decl.has_named_args, decl.has_body, decl.name_pos,
                            decl.self_is_mut, decl.self_is_ptr,
                            attributes = decl.attributes,
                            self_is_boxed = decl.self_is_boxed
                        )
                    )
                    decl.sym.is_main = decl.is_main
                except utils.CompilerError as e:
                    report.error(e.args[0], decl.name_pos)
            self.abi = old_abi
            self.sym = old_sym

    def walk_import_decl(self, decl):
        if len(decl.subimports) > 0:
            for subimport in decl.subimports:
                self.walk_import_decl(subimport)
        elif decl.glob:
            for symbol in decl.mod_sym.syms:
                if not symbol.is_public:
                    continue
                self.check_imported_symbol(symbol, decl.pos)
                if decl.is_public:
                    try:
                        self.sym.add(sym.SymRef(True, symbol.name, symbol))
                    except utils.CompilerError as e:
                        report.error(e.args[0], decl.pos)
                else:
                    self.source_file.imported_symbols[symbol.name] = symbol
        elif len(decl.import_list) == 0:
            if decl.is_public:
                try:
                    self.sym.add(sym.SymRef(True, decl.alias, decl.mod_sym))
                except utils.CompilerError as e:
                    report.error(e.args[0], decl.pos)
            else:
                self.source_file.imported_symbols[decl.alias] = decl.mod_sym
        else:
            for import_info in decl.import_list:
                if import_info.name == "self":
                    self.source_file.imported_symbols[decl.alias] = decl.mod_sym
                elif symbol := decl.mod_sym.find(import_info.name):
                    self.check_vis(symbol, import_info.pos)
                    self.check_imported_symbol(symbol, import_info.pos)
                    self.source_file.imported_symbols[import_info.alias
                                                      ] = symbol
                else:
                    report.error(
                        f"could not find `{import_info.name}` in module `{decl.mod_sym.name}`",
                        import_info.pos
                    )

    def add_sym(self, sy, pos):
        try:
            self.sym.add(sy)
        except utils.CompilerError as e:
            report.error(e.args[0], pos)

    def check_vis(self, sym_, pos):
        if not sym_.is_public and not self.sym.has_access_to(sym_):
            report.error(f"{sym_.typeof()} `{sym_.name}` is private", pos)

    def check_imported_symbol(self, s, pos):
        if s.name in self.source_file.imported_symbols:
            report.error(f"{s.typeof()} `{s.name}` is already imported", pos)
        elif self.source_file.sym.find(s.name):
            report.error(
                f"another symbol with the name `{s.name}` already exists", pos
            )
            report.help("you can use `as` to change the name of the import")
