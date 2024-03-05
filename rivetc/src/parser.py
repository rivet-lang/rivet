# Copyright (C) 2023 Jose Mendoza. All rights reserved.
# Use of this source code is governed by an MIT license that can
# be found in the LICENSE file.

import os, glob

from .token import Kind
from .lexer import Lexer
from . import ast, sym, type, prefs, report, token, utils

class Parser:
    def __init__(self, comp):
        self.comp = comp

        self.lexer = None
        self.prev_tok = None
        self.tok = None
        self.peek_tok = None
        self.last_err_pos = None

        self.file_path = ""
        self.file_dir = ""
        self.mod_sym = None

        self.scope = None

        self.extern_abi = sym.ABI.Rivet

        self.inside_extern = False
        self.inside_mod = False
        self.inside_struct = False
        self.inside_trait = False
        self.inside_enum_variant_with_fields = False
        self.inside_extend = False
        self.inside_match_header = False
        self.inside_block = False

    def parse_mod(self, mod_sym, files):
        self.mod_sym = mod_sym
        source_files = []
        for file in files:
            source_files.append(self.parse_file(file))
        return source_files

    def parse_file(self, file):
        self.file_path = file
        self.file_dir = os.path.dirname(file)
        self.lexer = Lexer.from_file(self.comp, file)
        if report.ERRORS > 0:
            return ast.SourceFile(file, [], None)
        self.advance(2)
        return ast.SourceFile(file, self.parse_decls(), self.mod_sym)

    # ---- useful functions for working with tokens ----
    def next(self):
        self.prev_tok = self.tok
        self.tok = self.peek_tok
        self.peek_tok = self.lexer.next()

    def peek_token(self, n):
        return self.lexer.peek_token(n - 2)

    def advance(self, n):
        for _ in range(n):
            self.next()

    def accept(self, kind):
        if self.tok.kind == kind:
            self.next()
            return True
        return False

    def expect(self, kind):
        if self.accept(kind):
            return
        elif self.last_err_pos and self.last_err_pos.pos == self.tok.pos.pos:
            self.next() # avoid infinite output
            return
        self.last_err_pos = self.tok.pos
        kstr = str(kind)
        if token.is_keyword(kstr) or (len(kstr) > 0 and not kstr[0].isalpha()):
            kstr = f"`{kstr}`"
        report.error(f"expected {kstr}, found {self.tok} ", self.tok.pos)

    # ---- utilities ------------------
    def parse_name(self):
        lit = self.tok.lit
        self.expect(Kind.Name)
        return lit

    def open_scope(self):
        self.scope = sym.Scope(self.tok.pos.pos, self.scope)

    def close_scope(self):
        self.scope.end = self.tok.pos.pos
        if self.scope.parent:
            self.scope.parent.childrens.append(self.scope)
        self.scope = self.scope.parent

    # ---- comptime ------------------
    def parse_nodes(self, level):
        if level == 0: # decl
            decls = []
            if self.accept(Kind.Lbrace):
                while self.tok.kind != Kind.Rbrace:
                    decls.append(self.parse_decl())
                self.expect(Kind.Rbrace)
            else:
                decls.append(self.parse_decl())
            return decls
        elif level == 1: # stmts
            stmts = []
            if self.accept(Kind.Lbrace):
                while self.tok.kind != Kind.Rbrace:
                    stmts.append(self.parse_stmt())
                self.expect(Kind.Rbrace)
            else:
                stmts.append(self.parse_stmt())
            return stmts
        return [self.parse_expr()]

    def parse_comptime_if(self, level):
        branches = []
        has_else = False
        pos = self.tok.pos
        while self.tok.kind in (Kind.KwIf, Kind.KwElse):
            if self.accept(Kind.KwElse) and self.tok.kind != Kind.KwIf:
                branches.append(
                    ast.ComptimeIfBranch(
                        self.empty_expr(), True, self.parse_nodes(level),
                        Kind.KwElse
                    )
                )
                has_else = True
                break
            self.expect(Kind.KwIf)
            cond = self.parse_expr()
            branches.append(
                ast.ComptimeIfBranch(
                    cond, False, self.parse_nodes(level), cond.pos
                )
            )
            if self.tok.kind != Kind.KwElse:
                break
        return ast.ComptimeIf(branches, has_else, pos)

    # ---- declarations --------------
    def parse_doc_comment(self):
        pos = self.tok.pos
        lines = []
        while self.accept(Kind.DocComment):
            lines.append(self.prev_tok.lit)
        return ast.DocComment(lines, pos)

    def parse_attributes(self, parse_mod_attributes = False):
        if parse_mod_attributes and self.mod_sym.attributes == None:
            self.mod_sym.attributes = ast.Attributes()
        attributes = ast.Attributes()
        while self.accept(Kind.Hash):
            if parse_mod_attributes:
                self.expect(Kind.Bang)
            if self.accept(Kind.Lbracket):
                while True:
                    args = []
                    pos = self.tok.pos
                    if self.accept(Kind.KwUnsafe):
                        attribute_name = "unsafe"
                    else:
                        attribute_name = self.parse_name()
                    if self.accept(Kind.Lparen):
                        while True:
                            if self.tok.kind == Kind.Name and self.peek_tok.kind == Kind.Colon:
                                name = self.parse_name()
                                self.expect(Kind.Colon)
                            else:
                                name = ""
                            expr = self.parse_expr()
                            args.append(ast.AttributeArg(name, expr))
                            if not self.accept(Kind.Comma):
                                break
                        self.expect(Kind.Rparen)
                    attribute = ast.Attribute(attribute_name, args, pos)
                    if parse_mod_attributes:
                        self.mod_sym.attributes.add(attribute)
                    else:
                        attributes.add(attribute)
                    if not self.accept(Kind.Semicolon):
                        break
                self.expect(Kind.Rbracket)
        return attributes

    def is_public(self):
        is_public = self.accept(Kind.KwPub)
        return self.inside_trait or self.inside_enum_variant_with_fields or is_public

    def parse_abi(self):
        self.expect(Kind.Lparen)
        abi_pos = self.tok.pos
        abi = self.parse_name()
        self.expect(Kind.Rparen)
        if abi_f := sym.ABI.from_string(abi):
            return abi_f
        report.error(f"unknown ABI: `{abi}`", abi_pos)
        return sym.ABI.Rivet

    def parse_decls(self):
        decls = []
        while self.tok.kind != Kind.EOF:
            decls.append(self.parse_decl())
        return decls

    def parse_decl(self):
        doc_comment = self.parse_doc_comment()
        is_mod_attr = self.tok.kind == Kind.Hash and self.peek_tok.kind == Kind.Bang
        attributes = self.parse_attributes(is_mod_attr)
        if is_mod_attr:
            return ast.EmptyDecl()
        is_public = self.is_public()
        pos = self.tok.pos
        if self.accept(Kind.Dollar):
            if self.tok.kind == Kind.KwIf:
                return self.parse_comptime_if(0)
            else:
                report.error("invalid comptime construction", self.tok.pos)
                return
        elif self.accept(Kind.KwImport):
            return self.parse_import_decl(attributes, is_public, pos)
        elif self.accept(Kind.KwExtern):
            self.inside_extern = True
            # extern function or var
            abi = self.parse_abi()
            protos = []
            if self.accept(Kind.Lbrace):
                if is_public:
                    report.error(
                        "`extern` blocks cannot be declared public", pos
                    )
                self.extern_abi = abi
                while True:
                    protos.append(self.parse_decl())
                    if self.tok.kind == Kind.Rbrace:
                        break
                self.expect(Kind.Rbrace)
            else:
                report.error("invalid external declaration", pos)
            self.inside_extern = False
            return ast.ExternDecl(attributes, abi, protos, pos)
        elif self.accept(Kind.KwConst):
            pos = self.tok.pos
            name = self.parse_name()
            has_typ = self.accept(Kind.Colon)
            if has_typ:
                typ = self.parse_type()
            else:
                typ = self.comp.void_t
            self.expect(Kind.DeclAssign)
            expr = self.parse_expr()
            self.expect(Kind.Semicolon)
            return ast.ConstDecl(
                doc_comment, attributes, is_public, name, has_typ, typ, expr,
                pos
            )
        elif self.accept(Kind.KwVar):
            # variable declarations
            pos = self.prev_tok.pos
            lefts = []
            if self.accept(Kind.Lparen):
                # multiple variables
                while True:
                    lefts.append(self.parse_var_decl(True))
                    if not self.accept(Kind.Comma):
                        break
                self.expect(Kind.Rparen)
            else:
                lefts.append(self.parse_var_decl(True))
            if not self.inside_extern and self.accept(Kind.DeclAssign):
                right = self.parse_expr()
            else:
                right = self.empty_expr()
            self.expect(Kind.Semicolon)
            return ast.VarDecl(
                doc_comment, attributes, is_public, self.inside_extern,
                self.extern_abi, lefts, right, pos
            )
        elif self.accept(Kind.KwAlias):
            pos = self.tok.pos
            name = self.parse_name()
            self.expect(Kind.DeclAssign)
            if self.tok.kind.is_start_of_type() and self.tok.kind != Kind.Name:
                is_typealias = True
                parent = self.parse_type()
            else:
                is_typealias = False
                parent = self.parse_ident()
                if self.accept(Kind.Dot):
                    parent = self.parse_selector_expr(parent)
                    while self.accept(Kind.Dot):
                        parent = self.parse_selector_expr(parent)
            self.expect(Kind.Semicolon)
            return ast.AliasDecl(
                doc_comment, attributes, is_public, name, parent, is_typealias,
                pos
            )
        elif self.accept(Kind.KwTrait):
            pos = self.tok.pos
            name = self.parse_name()
            bases = []
            if self.accept(Kind.Lt):
                while True:
                    bases.append(self.parse_type())
                    if not self.accept(Kind.Comma):
                        break
            decls = []
            prev_inside_trait = self.inside_trait
            self.inside_trait = True
            self.expect(Kind.Lbrace)
            while not self.accept(Kind.Rbrace):
                decls.append(self.parse_decl())
            self.inside_trait = prev_inside_trait
            return ast.TraitDecl(
                doc_comment, attributes, is_public, name, bases, decls, pos
            )
        elif self.accept(Kind.KwStruct):
            prev_inside_struct = self.inside_struct
            self.inside_struct = True
            pos = self.tok.pos
            name = self.parse_name()
            is_opaque = self.accept(Kind.Semicolon)
            bases = []
            decls = []
            if not is_opaque:
                if self.accept(Kind.Lt):
                    while True:
                        bases.append(self.parse_type())
                        if not self.accept(Kind.Comma):
                            break
                self.expect(Kind.Lbrace)
                while self.tok.kind != Kind.Rbrace:
                    decls.append(self.parse_decl())
                self.expect(Kind.Rbrace)
            self.inside_struct = prev_inside_struct
            return ast.StructDecl(
                doc_comment, attributes, is_public, name, bases, decls,
                is_opaque, pos
            )
        elif (
            self.inside_struct or self.inside_trait
            or self.inside_enum_variant_with_fields or self.inside_extend
        ) and self.tok.kind in (Kind.KwMut, Kind.Name):
            return self.parse_field_decl(attributes, doc_comment, is_public)
        elif self.accept(Kind.KwEnum):
            pos = self.tok.pos
            name = self.parse_name()
            underlying_typ = self.comp.comptime_int_t
            if self.accept(Kind.KwAs):
                underlying_typ = self.parse_type()
            bases = []
            if self.accept(Kind.Lt):
                while True:
                    bases.append(self.parse_type())
                    if not self.accept(Kind.Comma):
                        break
            self.expect(Kind.Lbrace)
            variants = []
            decls = []
            is_tagged = False
            while True:
                v_name = self.parse_name()
                has_typ = False
                typ = self.comp.void_t
                variant = self.empty_expr()
                variant_decls = []
                if self.accept(Kind.Lbrace):
                    has_typ = True
                    is_tagged = True
                    prev_inside_enum_variant_with_fields = self.inside_enum_variant_with_fields
                    self.inside_enum_variant_with_fields = True
                    while not self.accept(Kind.Rbrace):
                        variant_decls.append(self.parse_decl())
                    self.inside_enum_variant_with_fields = prev_inside_enum_variant_with_fields
                elif self.accept(Kind.Lparen):
                    has_typ = True
                    is_tagged = True
                    typ = self.parse_type()
                    self.expect(Kind.Rparen)
                elif self.accept(Kind.Assign):
                    variant = self.parse_expr()
                variants.append(
                    ast.EnumVariant(
                        v_name, typ, has_typ, variant, variant_decls
                    )
                )
                if not self.accept(Kind.Comma):
                    break
            if self.accept(Kind.Semicolon):
                while self.tok.kind != Kind.Rbrace:
                    decls.append(self.parse_decl())
            self.expect(Kind.Rbrace)
            return ast.EnumDecl(
                doc_comment, attributes, is_public, name, underlying_typ, bases,
                variants, is_tagged, decls, pos
            )
        elif self.accept(Kind.KwExtend):
            prev_inside_extend = self.inside_extend
            self.inside_extend = True

            pos = self.prev_tok.pos
            typ = self.parse_type()
            bases = []
            if self.accept(Kind.Lt):
                while True:
                    bases.append(self.parse_type())
                    if not self.accept(Kind.Comma):
                        break

            decls = []
            self.expect(Kind.Lbrace)
            while not self.accept(Kind.Rbrace):
                decls.append(self.parse_decl())

            self.inside_extend = prev_inside_extend
            return ast.ExtendDecl(attributes, typ, bases, decls, pos)
        elif self.accept(Kind.KwFunc):
            return self.parse_func_decl(
                doc_comment, attributes, is_public,
                attributes.has("unsafe") or (
                    self.inside_extern and self.extern_abi != sym.ABI.Rivet
                    and not attributes.has("trusted")
                ), self.extern_abi if self.inside_extern else sym.ABI.Rivet
            )
        elif self.accept(Kind.KwTest):
            pos = self.prev_tok.pos
            name = self.tok.lit
            self.expect(Kind.String)
            self.open_scope()
            sc = self.scope
            stmts = []
            self.expect(Kind.Lbrace)
            while not self.accept(Kind.Rbrace):
                stmts.append(self.parse_stmt())
            self.close_scope()
            return ast.TestDecl(sc, name, stmts, pos)
        elif self.tok.kind != Kind.EOF:
            report.error(f"expected declaration, found {self.tok}", pos)
            self.next()
        return ast.EmptyDecl()

    def parse_import_decl(self, attributes, is_public, pos):
        return self.parse_import("", attributes, is_public, pos)

    def parse_import(self, prev_mod_path, attributes, is_public, pos):
        mod_path_pos = self.tok.pos
        path = self.parse_import_path()
        if len(prev_mod_path) > 0:
            path = f"{prev_mod_path}/{path}"
        subimports = []
        if self.tok.kind == Kind.Div and self.peek_tok.kind == Kind.Lbrace:
            self.advance(2)
            while True:
                if self.accept(Kind.KwSelf):
                    self_pos = self.prev_tok.pos
                    if self.accept(Kind.KwAs):
                        self_alias = self.parse_name()
                    else:
                        self_alias = ""
                    subimports.append(
                        ast.ImportDecl(
                            attributes, is_public, path, self_alias, False, [],
                            [], pos
                        )
                    )
                else:
                    subimport_pos = self.tok.pos
                    subimports.append(
                        self.parse_import(
                            path, attributes, is_public, subimport_pos
                        )
                    )
                if not self.accept(Kind.Comma):
                    break
            self.expect(Kind.Rbrace)
        glob, import_list = self.parse_import_list(mod_path_pos)
        alias = ""
        if len(subimports) == 0 and len(import_list) == 0 and self.accept(
            Kind.KwAs
        ):
            alias = self.parse_name()
        if len(prev_mod_path) == 0:
            self.expect(Kind.Semicolon)
        return ast.ImportDecl(
            attributes, is_public, path, alias, glob, subimports, import_list,
            pos
        )

    def parse_import_list(self, mod_path_pos):
        import_list = []
        glob = False
        if self.accept(Kind.Dot):
            if self.accept(Kind.Lbrace):
                lbrace_pos = self.prev_tok.pos
                while True:
                    info_pos = self.tok.pos
                    if self.accept(Kind.KwSelf):
                        name = "self"
                        info_alias = name
                        if self.accept(Kind.KwAs):
                            info_alias = self.parse_name()
                        import_list.append(
                            ast.ImportListInfo(name, info_alias, info_pos)
                        )
                    else:
                        name = self.parse_name()
                        info_alias = name
                        if self.accept(Kind.KwAs):
                            info_alias = self.parse_name()
                        import_list.append(
                            ast.ImportListInfo(name, info_alias, info_pos)
                        )
                    if not self.accept(Kind.Comma):
                        break
                self.expect(Kind.Rbrace)
                if len(import_list) == 1:
                    report.warn("unnecessary use of braces", lbrace_pos)
                    report.note("consider removing those braces")
            elif self.tok.kind == Kind.Name:
                info_pos = self.tok.pos
                name = self.parse_name()
                info_alias = name
                if self.accept(Kind.KwAs):
                    info_alias = self.parse_name()
                import_list.append(
                    ast.ImportListInfo(name, info_alias, info_pos)
                )
            elif self.accept(Kind.Mul):
                glob = True
            else:
                report.error("invalid syntax for unqualified import", pos)
                report.note("expected a single name, a list of names or `*`")
        return glob, import_list

    def parse_import_path(self):
        res = ""
        if self.accept(Kind.Dot):
            res += "."
            if self.peek_tok.kind != Kind.Lbrace:
                res += "/"
                self.expect(Kind.Div)
        else:
            while self.accept(Kind.DotDot):
                res += ".."
                if self.peek_tok.kind != Kind.Lbrace:
                    res += "/"
                    self.expect(Kind.Div)
        if self.tok.kind == Kind.Div and self.peek_tok.kind == Kind.Lbrace:
            return res
        res += self.parse_name()
        while self.tok.kind == Kind.Div and self.peek_tok.kind != Kind.Lbrace:
            self.next()
            res += "/" + self.parse_name()
        return res

    def parse_field_decl(self, attributes, doc_comment, is_public):
        # fields
        is_mut = self.accept(Kind.KwMut)
        pos = self.tok.pos
        name = self.parse_name()
        self.expect(Kind.Colon)
        typ = self.parse_type()
        has_def_expr = self.accept(Kind.DeclAssign)
        def_expr = None
        if has_def_expr:
            def_expr = self.parse_expr()
        self.expect(Kind.Semicolon)
        return ast.FieldDecl(
            attributes, doc_comment, is_public, is_mut, name, typ, def_expr,
            has_def_expr, pos
        )

    def parse_func_decl(
        self, doc_comment, attributes, is_public, is_unsafe, abi
    ):
        pos = self.tok.pos
        if self.tok.kind.is_overloadable_op():
            name = str(self.tok.kind)
            self.next()
        else:
            name = self.parse_name()

        args = []
        is_method = False
        is_variadic = False
        self_is_ptr = False
        self_is_boxed = False
        self_is_mut = False
        has_named_args = False

        self.open_scope()
        sc = self.scope
        self.expect(Kind.Lparen)
        if self.tok.kind != Kind.Rparen:
            # receiver (`self`|`&self`|`&mut self`|`^self`|`^mut self`)
            if self.tok.kind == Kind.KwSelf or (
                self.tok.kind in (Kind.Amp, Kind.Xor)
                and self.peek_tok.kind in (Kind.KwMut, Kind.KwSelf)
            ):
                is_method = True
                self_is_ptr = self.accept(Kind.Amp)
                self_is_boxed = not self_is_ptr and self.accept(Kind.Xor)
                self_is_mut = self.accept(Kind.KwMut)
                self.expect(Kind.KwSelf)
                if self.tok.kind != Kind.Rparen:
                    self.expect(Kind.Comma)
            # arguments
            while self.tok.kind != Kind.Rparen:
                if self.inside_extern and self.accept(Kind.Ellipsis):
                    is_variadic = True
                    break
                else:
                    arg_pos = self.tok.pos
                    arg_is_mut = self.accept(Kind.KwMut)
                    arg_name = self.parse_name()
                    self.expect(Kind.Colon)
                    arg_typ = self.parse_type()
                    is_variadic = isinstance(arg_typ, type.Variadic)
                    arg_expr = self.empty_expr()
                    if self.accept(Kind.DeclAssign):
                        has_named_args = True
                        arg_expr = self.parse_expr()
                    args.append(
                        sym.Arg(
                            arg_name, arg_is_mut, arg_typ, arg_expr,
                            not isinstance(arg_expr, ast.EmptyExpr), arg_pos
                        )
                    )
                if not self.accept(Kind.Comma):
                    break
        self.expect(Kind.Rparen)

        ret_typ = self.comp.void_t
        if self.accept(Kind.Arrow):
            is_result = self.accept(Kind.Bang)
            if self.tok.kind == Kind.Lbrace:
                if not is_result:
                    report.error(
                        "expected return type declaration", self.prev_tok.pos
                    )
            else:
                ret_typ = self.parse_type()
            if is_result:
                ret_typ = type.Result(ret_typ)

        stmts = []
        has_body = True
        if (self.inside_trait
            or self.inside_extern) and self.accept(Kind.Semicolon):
            has_body = False
        else:
            self.expect(Kind.Lbrace)
            while not self.accept(Kind.Rbrace):
                stmts.append(self.parse_stmt())
        self.close_scope()
        return ast.FuncDecl(
            doc_comment, attributes, is_public, self.inside_extern, is_unsafe,
            name, pos, args, ret_typ, stmts, sc, has_body, is_method,
            self_is_mut, self_is_ptr, has_named_args, self.mod_sym.is_root
            and self.mod_sym.name != "core" and name == "main", is_variadic,
            abi, self_is_boxed = self_is_boxed
        )

    # ---- statements --------------------------
    def decl_operator_is_used(self):
        i = 1
        assign_was_used = False
        while i < len(self.lexer.all_tokens):
            tok = self.peek_token(i)
            if tok.kind == Kind.Assign:
                assign_was_used = True
            elif tok.kind == Kind.DeclAssign and not assign_was_used:
                return True
            elif tok.kind in (
                Kind.KwIf, Kind.KwMatch, Kind.KwWhile, Kind.Lbrace,
                Kind.Semicolon
            ):
                break
            i += 1
        return False

    def parse_stmt(self):
        if self.accept(Kind.Dollar):
            if self.tok.kind == Kind.KwIf:
                return self.parse_comptime_if(1)
            else:
                report.error("invalid comptime construction", self.tok.pos)
                return
        elif self.accept(Kind.KwWhile):
            pos = self.prev_tok.pos
            is_inf = False
            continue_expr = self.empty_expr()
            if self.tok.kind == Kind.Lbrace:
                cond = ast.BoolLiteral(True, self.tok.pos)
                is_inf = True
            else:
                if self.decl_operator_is_used():
                    self.open_scope()
                    cond = self.parse_guard_expr()
                else:
                    cond = self.parse_expr()
                if self.accept(Kind.Colon):
                    continue_expr = self.parse_expr()
            stmt = self.parse_block_stmt()
            if isinstance(cond, ast.GuardExpr):
                self.close_scope()
            else_stmt = None
            if self.accept(Kind.KwElse):
                else_stmt = self.parse_block_stmt()
            return ast.WhileStmt(
                self.scope, cond, continue_expr, stmt, else_stmt, is_inf, pos
            )
        elif self.accept(Kind.KwFor):
            pos = self.prev_tok.pos
            self.open_scope()
            sc = self.scope
            # single or 2 variables
            if self.peek_token(1).kind == Kind.Comma:
                index = self.parse_var_decl(
                    support_mut = False, support_typ = False
                )
                self.expect(Kind.Comma)
                value = self.parse_var_decl(
                    support_ref = True, support_typ = False
                )
            else:
                index = None
                value = self.parse_var_decl(
                    support_ref = True, support_typ = False
                )
            self.expect(Kind.KwIn)
            iterable = self.parse_expr()
            stmt = self.parse_block_stmt()
            self.close_scope()
            return ast.ForStmt(sc, index, value, iterable, stmt, pos)
        elif self.accept(Kind.KwDefer):
            defer_mode = ast.DeferMode.NORMAL
            if self.accept(Kind.Lparen):
                defer_mode_name_pos = self.tok.pos
                defer_mode_name = self.parse_name()
                self.expect(Kind.Rparen)
                if defer_mode_name == "error":
                    defer_mode = ast.DeferMode.ERROR
                elif defer_mode_name == "success":
                    defer_mode = ast.DeferMode.SUCCESS
                else:
                    report.error(
                        f"invalid `defer` mode: `{defer_mode_name}`",
                        defer_mode_name_pos
                    )
            pos = self.prev_tok.pos
            if self.tok.kind == Kind.Lbrace:
                expr = self.parse_block_expr(False)
            else:
                expr = self.parse_expr()
            if expr.__class__ not in (ast.IfExpr, ast.MatchExpr, ast.Block):
                self.expect(Kind.Semicolon)
            return ast.DeferStmt(expr, defer_mode, pos, self.scope)
        elif (
            self.tok.kind in (Kind.Lparen, Kind.KwMut, Kind.Name) and
            self.peek_tok.kind not in (Kind.Dot, Kind.Lbracket, Kind.Lparen)
            and self.decl_operator_is_used()
        ):
            # variable declarations
            pos = self.prev_tok.pos
            lefts = []
            if self.accept(Kind.Lparen):
                # multiple variables
                while True:
                    lefts.append(self.parse_var_decl(False))
                    if not self.accept(Kind.Comma):
                        break
                self.expect(Kind.Rparen)
            else:
                lefts.append(self.parse_var_decl(False))
            self.expect(Kind.DeclAssign)
            right = self.parse_expr()
            self.expect(Kind.Semicolon)
            return ast.VarDeclStmt(self.scope, lefts, right, pos)
        expr = self.parse_expr()
        if not ((self.inside_block and self.tok.kind == Kind.Rbrace)
                or expr.__class__ in (ast.IfExpr, ast.MatchExpr, ast.Block)):
            self.expect(Kind.Semicolon)
        return ast.ExprStmt(expr, expr.pos)

    def parse_var_decl(
        self, inside_global = False, support_typ = True, support_ref = False,
        support_mut = True
    ):
        is_ref = support_ref and self.accept(Kind.Amp)
        is_mut = support_mut and self.accept(Kind.KwMut)
        pos = self.tok.pos
        name = self.parse_name()
        has_typ = False
        typ = self.comp.void_t
        if support_typ and self.accept(Kind.Colon):
            typ = self.parse_type()
            has_typ = True
        return ast.ObjDecl(
            is_mut, is_ref, name, has_typ, typ, sym.ObjLevel.Local, pos
        )

    def parse_block_stmt(self):
        expr = self.parse_block_expr(False)
        return ast.ExprStmt(expr, expr.pos)

    # ---- expressions -------------------------
    def parse_expr(self):
        return self.parse_or_expr()

    def parse_or_expr(self):
        left = self.parse_and_expr()
        while self.accept(Kind.LogicalOr):
            right = self.parse_and_expr()
            left = ast.BinaryExpr(left, Kind.LogicalOr, right, left.pos)
        return left

    def parse_and_expr(self):
        left = self.parse_equality_expr()
        while self.accept(Kind.LogicalAnd):
            right = self.parse_equality_expr()
            left = ast.BinaryExpr(left, Kind.LogicalAnd, right, left.pos)
        return left

    def parse_equality_expr(self):
        left = self.parse_relational_expr()
        while True:
            if self.tok.kind in [Kind.Eq, Kind.Ne]:
                op = self.tok.kind
                self.next()
                right = self.parse_relational_expr()
                left = ast.BinaryExpr(left, op, right, left.pos)
            else:
                break
        return left

    def parse_relational_expr(self):
        left = self.parse_shift_expr()
        while True:
            if self.tok.kind in [
                Kind.Gt, Kind.Lt, Kind.Ge, Kind.Le, Kind.OrElse, Kind.KwIn,
                Kind.KwNotIn
            ]:
                op = self.tok.kind
                self.next()
                right = self.parse_shift_expr()
                left = ast.BinaryExpr(left, op, right, left.pos)
            elif self.tok.kind in [Kind.KwIs, Kind.KwNotIs]:
                if self.inside_match_header and self.peek_tok.kind == Kind.Lbrace:
                    break
                op = self.tok.kind
                self.next()
                pos = self.tok.pos
                if self.accept(Kind.Dot):
                    name = self.parse_name()
                    right = ast.EnumLiteral(name, pos, True)
                else:
                    right = ast.TypeNode(self.parse_type(), pos)
                if self.accept(Kind.Lparen):
                    var = self.parse_var_decl(
                        support_ref = True, support_mut = True
                    )
                    self.expect(Kind.Rparen)
                else:
                    var = None
                left = ast.BinaryExpr(
                    left, op, right, left.pos, var, self.scope
                )
            else:
                break
        return left

    def parse_shift_expr(self):
        left = self.parse_additive_expr()
        while True:
            if self.tok.kind in [Kind.Lt, Kind.Gt]:
                op = Kind.Lshift if self.tok.kind == Kind.Lt else Kind.Rshift
                if self.tok.pos.pos + 1 == self.peek_tok.pos.pos:
                    self.advance(2)
                    right = self.parse_additive_expr()
                    left = ast.BinaryExpr(left, op, right, left.pos)
                else:
                    break
            elif self.tok.kind in [Kind.Amp, Kind.Pipe, Kind.Xor]:
                op = self.tok.kind
                if op in (
                    Kind.Amp, Kind.Xor
                ) and self.prev_tok.pos.line < self.tok.pos.line:
                    break
                self.next()
                right = self.parse_additive_expr()
                left = ast.BinaryExpr(left, op, right, left.pos)
            else:
                break
        return left

    def parse_additive_expr(self):
        left = self.parse_multiplicative_expr()
        while True:
            if self.tok.kind in [Kind.Plus, Kind.Minus]:
                op = self.tok.kind
                self.next()
                right = self.parse_multiplicative_expr()
                left = ast.BinaryExpr(left, op, right, left.pos)
            else:
                break
        return left

    def parse_multiplicative_expr(self):
        left = self.parse_unary_expr()
        while True:
            if self.tok.kind in [Kind.Mul, Kind.Div, Kind.Mod]:
                op = self.tok.kind
                self.next()
                right = self.parse_unary_expr()
                left = ast.BinaryExpr(left, op, right, left.pos)
            else:
                break
        return left

    def parse_unary_expr(self):
        expr = self.empty_expr()
        if self.tok.kind in [Kind.Amp, Kind.Bang, Kind.BitNot, Kind.Minus]:
            op = self.tok.kind
            pos = self.tok.pos
            self.next()
            is_mut_ptr = op == Kind.Amp and self.accept(Kind.KwMut)
            right = self.parse_unary_expr()
            expr = ast.UnaryExpr(right, op, is_mut_ptr, pos)
        elif self.tok.kind == Kind.Xor and self.peek_tok.kind != Kind.Lbracket:
            pos = self.tok.pos
            self.next()
            is_mut_ptr = self.accept(Kind.KwMut)
            right = self.parse_unary_expr()
            expr = ast.UnaryExpr(right, Kind.Xor, is_mut_ptr, pos)
        else:
            expr = self.parse_primary_expr()
        return expr

    def parse_primary_expr(self):
        expr = self.empty_expr()
        if self.accept(Kind.Dollar):
            if self.tok.kind == Kind.KwIf:
                expr = self.parse_comptime_if(3)
            else:
                report.error("invalid comptime construction", self.tok.pos)
                return
        elif self.tok.kind in [
            Kind.KwTrue, Kind.KwFalse, Kind.Char, Kind.Number, Kind.String,
            Kind.KwNone, Kind.KwSelf, Kind.KwSelfTy
        ]:
            expr = self.parse_literal()
        elif self.accept(Kind.At):
            pos = self.prev_tok.pos
            if self.peek_token(1).kind == Kind.Lparen: # builtin call
                if self.accept(Kind.KwAs):
                    name = "as"
                else:
                    name = self.parse_name()
                self.expect(Kind.Lparen)
                args = []
                dyn_array_is_mut = False
                if name in ("as", "size_of", "align_of"):
                    pos = self.tok.pos
                    args.append(ast.TypeNode(self.parse_type(), pos))
                    if self.tok.kind != Kind.Rparen:
                        self.expect(Kind.Comma)
                if self.tok.kind != Kind.Rparen:
                    while True:
                        args.append(self.parse_expr())
                        if not self.accept(Kind.Comma):
                            break
                self.expect(Kind.Rparen)
                expr = ast.BuiltinCallExpr(name, args, expr.pos)
            else: # builtin variable
                expr = self.parse_ident(True)
        elif self.tok.kind == Kind.Dot and self.peek_tok.kind == Kind.Name:
            pos = self.tok.pos
            self.next()
            name = self.parse_name()
            expr = ast.EnumLiteral(name, pos)
        elif self.tok.kind in (Kind.KwContinue, Kind.KwBreak):
            op = self.tok.kind
            pos = self.tok.pos
            self.next()
            expr = ast.LoopControlExpr(op, pos, self.scope)
        elif self.accept(Kind.KwReturn):
            pos = self.prev_tok.pos
            has_expr = self.tok.kind not in (
                Kind.Comma, Kind.Semicolon, Kind.Rbrace
            )
            if has_expr:
                expr = self.parse_expr()
            else:
                expr = self.empty_expr()
            expr = ast.ReturnExpr(expr, has_expr, pos, self.scope)
        elif self.accept(Kind.KwThrow):
            pos = self.prev_tok.pos
            expr = ast.ThrowExpr(self.parse_expr(), pos, self.scope)
        elif self.tok.kind == Kind.KwIf:
            expr = self.parse_if_expr()
        elif self.accept(Kind.KwMatch):
            expr = self.parse_match_expr()
        elif self.tok.kind == Kind.Lparen:
            pos = self.tok.pos
            self.next()
            e = self.parse_expr()
            if self.accept(Kind.Comma): # tuple
                exprs = [e]
                while True:
                    exprs.append(self.parse_expr())
                    if not self.accept(Kind.Comma):
                        break
                self.expect(Kind.Rparen)
                if len(exprs) > 8:
                    report.error(
                        "tuples can have a maximum of 8 expressions", pos
                    )
                expr = ast.TupleLiteral(exprs, pos)
            else:
                self.expect(Kind.Rparen)
                expr = ast.ParExpr(e, e.pos)
        elif self.tok.kind in (Kind.KwUnsafe, Kind.Lbrace):
            expr = self.parse_block_expr()
        elif self.tok.kind in (Kind.Lbracket, Kind.Xor):
            pos = self.tok.pos
            is_dyn = self.accept(Kind.Xor)
            elems = []
            self.next()
            if self.tok.kind != Kind.Rbracket:
                while True:
                    elems.append(self.parse_expr())
                    if not self.accept(Kind.Comma):
                        break
            self.expect(Kind.Rbracket)
            if not is_dyn and (
                len(elems) == 0 or len(elems) == 1 and self.tok.kind not in
                (Kind.Semicolon, Kind.Comma, Kind.Rbrace, Kind.Rparen)
            ):
                # []T() or [SIZE]T()
                is_dyn = len(elems) == 0
                is_mut = self.accept(Kind.KwMut)
                elem_type = self.parse_type()
                init_value = None
                cap_value = None
                len_value = None
                self.expect(Kind.Lparen)
                while self.tok.kind != Kind.Rparen:
                    arg_pos = self.tok.pos
                    arg_name = self.parse_name()
                    self.expect(Kind.Colon)
                    arg_value = self.parse_expr()
                    if arg_name == "init":
                        if init_value:
                            report.error(
                                "duplicate array constructor argument `init`",
                                arg_pos
                            )
                            break
                        else:
                            init_value = arg_value
                    elif arg_name == "len" and is_dyn:
                        if len_value:
                            report.error(
                                "duplicate array constructor argument `len`",
                                arg_pos
                            )
                            break
                        else:
                            len_value = arg_value
                    elif arg_name == "cap" and is_dyn:
                        if cap_value:
                            report.error(
                                "duplicate array constructor argument `cap`",
                                arg_pos
                            )
                            break
                        else:
                            cap_value = arg_value
                    else:
                        report.error(
                            f"unknown array constructor argument `{arg_name}`",
                            arg_pos
                        )
                        break
                    if self.tok.kind != Kind.Rparen:
                        self.expect(Kind.Comma)
                self.expect(Kind.Rparen)
                if not is_dyn:
                    len_value = elems[0]
                expr = ast.ArrayCtor(
                    is_dyn, is_mut, elem_type, init_value, cap_value, len_value,
                    pos
                )
            else:
                expr = ast.ArrayLiteral(elems, is_dyn, pos)
        elif self.tok.kind == Kind.Name:
            if self.peek_tok.kind == Kind.Char:
                if self.tok.lit == "b":
                    expr = self.parse_character_literal()
                else:
                    report.error(
                        "only `b` is recognized as a valid prefix for a character literal",
                        self.tok.pos,
                    )
                    self.next()
            elif self.tok.kind == Kind.Name and self.peek_tok.kind == Kind.String:
                if self.tok.lit in ("c", "b", "r"):
                    expr = self.parse_string_literal()
                else:
                    report.error(
                        "only `c`, `b` and `r` are recognized as valid prefixes for a string literal",
                        self.tok.pos,
                    )
                    self.next()
            else:
                expr = self.parse_ident()
        else:
            expr = self.empty_expr()

        while True:
            if self.tok.kind.is_assign():
                # assignment
                op = self.tok.kind
                self.expect(op)
                expr = ast.AssignExpr(expr, op, self.parse_expr(), expr.pos)
            elif self.tok.kind == Kind.Lparen and not self.decl_operator_is_used(
            ) and isinstance(
                expr, (
                    ast.Ident, ast.SelectorExpr, ast.ParExpr, ast.SelfTyExpr,
                    ast.EnumLiteral
                )
            ):
                self.next()
                args = []
                has_spread_expr = False
                spread_expr = self.empty_expr()
                if self.tok.kind != Kind.Rparen:
                    expecting_named_arg = False
                    while True:
                        if (
                            self.tok.kind == Kind.Name
                            and self.peek_tok.kind == Kind.Colon
                        ):
                            # named argument
                            name_p = self.tok.pos
                            name = self.parse_name()
                            self.expect(Kind.Colon)
                            expr2 = self.parse_expr()
                            args.append(ast.CallArg(expr2, name_p, name))
                            expecting_named_arg = True
                        elif self.accept(Kind.Ellipsis):
                            spread_pos = self.prev_tok.pos
                            has_spread_expr = True
                            spread_expr = self.parse_expr()
                            if self.tok.kind == Kind.Comma:
                                report.error(
                                    "spread expression must be the final argument",
                                    spread_pos
                                )
                        else:
                            if expecting_named_arg:
                                report.error(
                                    "expected named argument, found single expression",
                                    self.tok.pos
                                )
                            expr2 = self.parse_expr()
                            args.append(ast.CallArg(expr2, expr2.pos))
                        if not self.accept(Kind.Comma):
                            break
                self.expect(Kind.Rparen)
                err_handler_pos = self.tok.pos
                is_propagate = False
                varname = ""
                varname_pos = self.tok.pos
                err_expr = None
                has_err_expr = False
                if self.accept(Kind.Bang):
                    # check result value, if error propagate
                    err_handler_pos = self.prev_tok.pos
                    is_propagate = True
                elif self.accept(Kind.KwCatch):
                    if self.accept(Kind.Pipe):
                        varname_pos = self.tok.pos
                        varname = self.parse_name()
                        self.expect(Kind.Pipe)
                    err_expr = self.parse_expr()
                    has_err_expr = True
                expr = ast.CallExpr(
                    expr, args, has_spread_expr, spread_expr,
                    ast.CallErrorHandler(
                        is_propagate, varname, err_expr, has_err_expr,
                        varname_pos, self.scope, err_handler_pos
                    ), expr.pos, self.scope
                )
            elif self.accept(Kind.Lbracket):
                index = self.empty_expr()
                if self.accept(Kind.Colon):
                    if self.tok.kind == Kind.Rbracket:
                        index = ast.RangeExpr(
                            None, None, False, index.pos, False, False
                        )
                    else:
                        index = ast.RangeExpr(
                            None, self.parse_expr(), False, index.pos, False,
                            True
                        )
                else:
                    index = self.parse_expr()
                    if self.accept(Kind.Colon):
                        if self.tok.kind == Kind.Rbracket:
                            index = ast.RangeExpr(
                                index, None, False, index.pos, True, False
                            )
                        else:
                            index = ast.RangeExpr(
                                index, self.parse_expr(), False, index.pos,
                                True, True
                            )
                self.expect(Kind.Rbracket)
                expr = ast.IndexExpr(expr, index, expr.pos)
            elif ( # avoid `expr` + `.EnumLiteral` concatenation
                self.prev_tok.pos.line != self.tok.pos.line and self.tok.kind == Kind.Dot
                and self.peek_tok.kind == Kind.Name and self.peek_tok.lit[0].isupper()
            ):
                break
            elif self.accept(Kind.Dot):
                if self.accept(Kind.Xor):
                    expr = ast.SelectorExpr(
                        expr, "", expr.pos, self.prev_tok.pos,
                        is_boxed_indirect = True
                    )
                elif self.accept(Kind.Mul):
                    expr = ast.SelectorExpr(
                        expr, "", expr.pos, self.prev_tok.pos,
                        is_indirect = True
                    )
                else:
                    expr = self.parse_selector_expr(expr)
            elif self.accept(Kind.Question):
                # check option value, panic if is `none`: `x?`
                expr = ast.SelectorExpr(
                    expr, "", expr.pos, self.prev_tok.pos,
                    is_option_check = True
                )
            else:
                break
        return expr

    def parse_block_expr(self, accept_expr = True):
        # block expression
        pos = self.tok.pos
        is_unsafe = self.accept(Kind.KwUnsafe)
        self.expect(Kind.Lbrace)
        prev_inside_block = self.inside_block
        self.inside_block = True
        stmts = []
        has_expr = False
        self.open_scope()
        sc = self.scope
        expr = None
        while not self.accept(Kind.Rbrace):
            stmt = self.parse_stmt()
            if accept_expr:
                has_expr = isinstance(
                    stmt, ast.ExprStmt
                ) and self.prev_tok.kind != Kind.Semicolon and self.tok.kind == Kind.Rbrace
                if has_expr:
                    expr = stmt.expr
                else:
                    stmts.append(stmt)
            else:
                stmts.append(stmt)
        self.close_scope()
        self.inside_block = prev_inside_block
        return ast.Block(sc, is_unsafe, stmts, expr, has_expr, pos)

    def parse_if_expr(self):
        branches = []
        has_else = False
        pos = self.tok.pos
        while self.tok.kind in (Kind.KwIf, Kind.KwElse):
            if self.accept(Kind.KwElse) and self.tok.kind != Kind.KwIf:
                branches.append(
                    ast.IfBranch(
                        self.empty_expr(), self.parse_block_expr(), True,
                        Kind.KwElse
                    )
                )
                has_else = True
                break
            self.expect(Kind.KwIf)
            if self.decl_operator_is_used():
                self.open_scope()
                cond = self.parse_guard_expr()
            else:
                cond = self.parse_expr()
            branches.append(
                ast.IfBranch(cond, self.parse_block_expr(), False, Kind.KwIf)
            )
            if isinstance(cond, ast.GuardExpr):
                self.close_scope()
            if self.tok.kind != Kind.KwElse:
                break
        return ast.IfExpr(branches, has_else, pos)

    def parse_match_expr(self):
        branches = []
        pos = self.prev_tok.pos
        is_typematch = False
        prev_inside_match_header = self.inside_match_header
        self.inside_match_header = True
        if self.tok.kind == Kind.Lbrace:
            expr = ast.BoolLiteral(True, pos)
        else:
            if self.decl_operator_is_used():
                self.open_scope()
                expr = self.parse_guard_expr()
            else:
                expr = self.parse_expr()
            is_typematch = self.accept(Kind.KwIs)
        self.expect(Kind.Lbrace)
        self.inside_match_header = prev_inside_match_header
        while True:
            self.open_scope()
            pats = []
            has_var = False
            var_is_ref = False
            var_is_mut = False
            var_name = ""
            var_pos = token.NO_POS
            has_cond = False
            cond = self.empty_expr()
            is_else = self.accept(Kind.KwElse)
            if not is_else:
                while True:
                    if is_typematch:
                        t_pos = self.tok.pos
                        pats.append(ast.TypeNode(self.parse_type(), t_pos))
                    else:
                        if self.accept(Kind.Dot):
                            t_pos = self.tok.pos
                            branch_expr = ast.EnumLiteral(
                                self.parse_name(), t_pos, True
                            )
                        else:
                            branch_expr = self.parse_expr()
                        if self.accept(Kind.DotDot
                                       ) or self.accept(Kind.Ellipsis):
                            if self.prev_tok.kind == Kind.DotDot:
                                report.error(
                                    "match only supports inclusive ranges, not exclusive",
                                    self.prev_tok.pos
                                )
                                report.help("use `...` instead of `..`")
                            branch_expr = ast.RangeExpr(
                                branch_expr, self.parse_expr(), True,
                                branch_expr.pos
                            )
                        pats.append(branch_expr)
                    if not self.accept(Kind.Comma):
                        break
                if self.accept(Kind.Lparen):
                    has_var = True
                    var_is_ref = self.accept(Kind.Amp)
                    var_is_mut = self.accept(Kind.KwMut)
                    var_pos = self.tok.pos
                    var_name = self.parse_name()
                    self.expect(Kind.Rparen)
                if self.accept(Kind.KwIf):
                    has_cond = True
                    cond = self.parse_expr()
            self.expect(Kind.Arrow)
            branches.append(
                ast.MatchBranch(
                    pats, has_var, var_is_ref, var_is_mut, var_name, var_pos,
                    has_cond, cond, self.parse_expr(), is_else, self.scope
                )
            )
            self.close_scope()
            if not self.accept(Kind.Comma):
                break
        if isinstance(expr, ast.GuardExpr):
            self.close_scope()
        self.expect(Kind.Rbrace)
        return ast.MatchExpr(expr, branches, is_typematch, self.scope, pos)

    def parse_guard_expr(self):
        pos = self.prev_tok.pos
        vars = []
        if self.accept(Kind.Lparen):
            while True:
                vars.append(self.parse_var_decl(support_typ = False))
                if not self.accept(Kind.Comma):
                    break
        else:
            vars.append(self.parse_var_decl(support_typ = False))
        self.expect(Kind.DeclAssign)
        e = self.parse_expr()
        if self.accept(Kind.Semicolon):
            has_cond = True
            cond = self.parse_expr()
        else:
            has_cond = False
            cond = self.empty_expr()
        return ast.GuardExpr(vars, e, has_cond, cond, self.scope, pos)

    def parse_selector_expr(self, left):
        field_pos = self.tok.pos
        if self.tok.kind == Kind.Number:
            name = self.tok.lit
            self.next()
        else:
            name = self.parse_name()
        return ast.SelectorExpr(left, name, left.pos, field_pos)

    def parse_literal(self):
        if self.tok.kind in [Kind.KwTrue, Kind.KwFalse]:
            pos = self.tok.pos
            lit = self.tok.kind == Kind.KwTrue
            self.next()
            return ast.BoolLiteral(lit, pos)
        elif self.tok.kind == Kind.Char:
            return self.parse_character_literal()
        elif self.tok.kind == Kind.Number:
            return self.parse_integer_literal()
        elif self.tok.kind == Kind.String:
            return self.parse_string_literal()
        elif self.accept(Kind.KwNone):
            return ast.NoneLiteral(self.prev_tok.pos)
        elif self.accept(Kind.KwSelf):
            return ast.SelfExpr(self.scope, self.prev_tok.pos)
        elif self.accept(Kind.KwSelfTy):
            return ast.SelfTyExpr(self.scope, self.prev_tok.pos)
        else:
            report.error(f"expected literal, found {self.tok}", self.tok.pos)
        return self.empty_expr()

    def parse_integer_literal(self):
        pos = self.tok.pos
        lit = self.tok.lit
        self.next()
        return ast.FloatLiteral(lit, pos) if lit[:2] not in [
            '0x', '0o', '0b'
        ] and utils.index_any(lit,
                              ".eE") >= 0 else ast.IntegerLiteral(lit, pos)

    def parse_character_literal(self):
        is_byte = False
        if self.tok.kind == Kind.Name:
            is_byte = self.tok.lit == "b"
            self.expect(Kind.Name)
        lit = self.tok.lit
        pos = self.tok.pos
        self.expect(Kind.Char)
        return ast.CharLiteral(lit, pos, is_byte)

    def parse_string_literal(self):
        is_raw = False
        is_bytestr = False
        is_cstr = False
        if self.tok.kind == Kind.Name:
            is_raw = self.tok.lit == "r"
            is_bytestr = self.tok.lit == "b"
            is_cstr = self.tok.lit == "c"
            self.expect(Kind.Name)
        lit = self.tok.lit
        pos = self.tok.pos
        self.expect(Kind.String)
        while self.accept(Kind.String):
            lit += self.prev_tok.lit
        return ast.StringLiteral(lit, is_raw, is_bytestr, is_cstr, pos)

    def parse_ident(self, is_comptime = False):
        pos = self.tok.pos
        name = self.parse_name()
        sc = self.scope
        if sc == None:
            sc = sym.Scope(sc)
        return ast.Ident(name, pos, sc, is_comptime)

    def empty_expr(self):
        return ast.EmptyExpr(self.tok.pos)

    # ---- types -------------------------------
    def parse_type(self):
        pos = self.tok.pos
        if self.accept(Kind.Question):
            # option
            return type.Option(self.parse_type())
        elif self.tok.kind == Kind.KwFunc:
            # function types
            args = []
            self.expect(Kind.KwFunc)
            self.expect(Kind.Lparen)
            if self.tok.kind != Kind.Rparen:
                while True:
                    pos = self.tok.pos
                    is_mut = self.accept(Kind.KwMut)
                    arg_typ = self.parse_type()
                    args.append(
                        sym.Arg(
                            f"arg{len(args)}", is_mut, arg_typ, None, False, pos
                        )
                    )
                    if not self.accept(Kind.Comma):
                        break
            self.expect(Kind.Rparen)
            if self.accept(Kind.Arrow):
                ret_typ = self.parse_type()
            else:
                ret_typ = self.comp.void_t
            return type.Func(
                False, sym.ABI.Rivet, False, args, False, ret_typ, False, False
            )
        elif self.accept(Kind.Amp):
            # pointers
            is_mut = self.accept(Kind.KwMut)
            if self.tok.kind == Kind.Amp:
                report.error("cannot declare pointer to pointer", pos)
                report.help("use an indexable pointer instead (`[&]T`)")
            return type.Ptr(self.parse_type(), is_mut)
        elif self.accept(Kind.Lbracket):
            # arrays or dynamic arrays
            if self.tok.kind != Kind.Rbracket:
                if self.accept(Kind.Amp):
                    # indexable pointers
                    self.expect(Kind.Rbracket)
                    is_mut = self.accept(Kind.KwMut)
                    return type.Ptr(self.parse_type(), is_mut, True)
                elif self.accept(Kind.Colon):
                    # slices
                    self.expect(Kind.Rbracket)
                    is_mut = self.accept(Kind.KwMut)
                    return type.Slice(self.parse_type(), is_mut)
                # array
                size = self.parse_expr()
                self.expect(Kind.Rbracket)
                is_mut = self.accept(Kind.KwMut)
                return type.Array(self.parse_type(), size, is_mut)
            self.expect(Kind.Rbracket)
            is_mut = self.accept(Kind.KwMut)
            return type.DynArray(self.parse_type(), is_mut)
        elif self.accept(Kind.Lparen):
            # tuples
            types = []
            while True:
                types.append(self.parse_type())
                if not self.accept(Kind.Comma):
                    break
            if len(types) > 8:
                report.error("tuples can have a maximum of 8 types", pos)
                report.help("you can use a struct instead")
            self.expect(Kind.Rparen)
            return type.Tuple(types)
        elif self.accept(Kind.Ellipsis):
            return type.Variadic(self.parse_type())
        elif self.accept(Kind.KwSelfTy):
            return type.Type.unresolved(
                ast.SelfTyExpr(self.scope, self.prev_tok.pos)
            )
        elif self.accept(Kind.KwNone):
            return self.comp.none_t
        elif self.tok.kind in (Kind.Xor, Kind.Name):
            prev_tok_kind = self.prev_tok.kind
            is_boxed = self.accept(Kind.Xor)
            is_mut = is_boxed and self.accept(Kind.KwMut)
            if self.accept(Kind.KwSelfTy):
                return type.Type.unresolved(
                    ast.SelfTyExpr(self.scope, self.prev_tok.pos), is_boxed,
                    is_mut
                )
            expr = self.parse_ident()
            if self.accept(Kind.Dot):
                res = self.parse_selector_expr(expr)
                while self.accept(Kind.Dot):
                    res = self.parse_selector_expr(res)
                return type.Type.unresolved(res, is_boxed, is_mut)
            # normal type
            lit = expr.name
            if lit == "never":
                if prev_tok_kind != Kind.Arrow:
                    report.error("invalid use of `never` type", pos)
                return self.comp.never_t
            elif lit == "rawptr":
                return self.comp.rawptr_t
            elif lit == "boxedptr":
                return self.comp.boxedptr_t
            elif lit == "bool":
                if is_boxed:
                    return self.comp.bool_t.to_boxed(is_mut)
                return self.comp.bool_t
            elif lit == "rune":
                if is_boxed:
                    return self.comp.rune_t.to_boxed(is_mut)
                return self.comp.rune_t
            elif lit == "int":
                if is_boxed:
                    return self.comp.int_t.to_boxed(is_mut)
                return self.comp.int_t
            elif lit == "int8":
                if is_boxed:
                    return self.comp.int8_t.to_boxed(is_mut)
                return self.comp.int8_t
            elif lit == "int16":
                if is_boxed:
                    return self.comp.int16_t.to_boxed(is_mut)
                return self.comp.int16_t
            elif lit == "int32":
                if is_boxed:
                    return self.comp.int32_t.to_boxed(is_mut)
                return self.comp.int32_t
            elif lit == "int64":
                if is_boxed:
                    return self.comp.int64_t.to_boxed(is_mut)
                return self.comp.int64_t
            elif lit == "uint":
                if is_boxed:
                    return self.comp.uint_t.to_boxed(is_mut)
                return self.comp.uint_t
            elif lit == "uint8":
                if is_boxed:
                    return self.comp.uint8_t.to_boxed(is_mut)
                return self.comp.uint8_t
            elif lit == "uint16":
                if is_boxed:
                    return self.comp.uint16_t.to_boxed(is_mut)
                return self.comp.uint16_t
            elif lit == "uint32":
                if is_boxed:
                    return self.comp.uint32_t.to_boxed(is_mut)
                return self.comp.uint32_t
            elif lit == "uint64":
                if is_boxed:
                    return self.comp.uint64_t.to_boxed(is_mut)
                return self.comp.uint64_t
            elif lit == "float32":
                if is_boxed:
                    return self.comp.float32_t.to_boxed(is_mut)
                return self.comp.float32_t
            elif lit == "float64":
                if is_boxed:
                    return self.comp.float64_t.to_boxed(is_mut)
                return self.comp.float64_t
            elif lit == "string":
                if is_boxed:
                    return self.comp.string_t.to_boxed(is_mut)
                return self.comp.string_t
            elif lit == "comptime_int":
                if is_boxed:
                    return self.comp.comptime_int_t.to_boxed(is_mut)
                return self.comp.comptime_int_t
            elif lit == "comptime_float":
                if is_boxed:
                    return self.comp.comptime_float_t.to_boxed(is_mut)
                return self.comp.comptime_float_t
            return type.Type.unresolved(expr, is_boxed, is_mut)
        else:
            report.error(f"expected type, found {self.tok}", pos)
            self.next()
        return type.Type.unresolved(self.empty_expr())
