# Copyright (C) 2023 Jose Mendoza. All rights reserved.
# Use of this source code is governed by an MIT license that can
# be found in the LICENSE file.

from .token import Kind
from . import ast, sym, type, report, utils

class Resolver:
    def __init__(self, comp):
        self.comp = comp
        self.preludes = {}
        self.source_file = None
        self.sym = None
        self.self_sym = None

        self.inside_extend_type = False
        self.inside_typematch_type = False

    def resolve_files(self, source_files):
        self.load_preludes()
        for sf in source_files:
            self.sym = sf.sym
            self.source_file = sf
            self.resolve_decls(self.source_file.decls)

    def load_preludes(self):
        self.preludes["Throwable"] = self.comp.throwable_sym

    def resolve_decls(self, decls):
        for decl in decls:
            old_sym = self.sym
            old_self_sym = self.self_sym
            if isinstance(decl, ast.ComptimeIf):
                self.resolve_decls(self.comp.evalue_comptime_if(decl))
            elif isinstance(decl, ast.ExternDecl):
                self.resolve_decls(decl.decls)
            elif isinstance(decl, ast.ConstDecl):
                self.resolve_type(decl.typ)
                self.resolve_expr(decl.expr)
            elif isinstance(decl, ast.VarDecl):
                for v in decl.lefts:
                    self.resolve_type(v.typ)
                if not decl.is_extern:
                    self.resolve_expr(decl.right)
            elif isinstance(decl, ast.AliasDecl):
                if decl.is_typealias:
                    self.resolve_type(decl.parent)
                elif not decl.sym.ref_resolved:
                    decl.sym.ref_resolved = True
                    self.resolve_expr(decl.parent)
            elif isinstance(decl, ast.EnumDecl):
                if self.resolve_type(decl.underlying_typ):
                    for i, variant in enumerate(decl.sym.info.variants):
                        if not self.resolve_type(variant.typ):
                            continue
                        d_v = decl.variants[i]
                        if d_v.has_value:
                            variant.value = self.eval_size(d_v.value).lit
                        else:
                            if i > 0:
                                last_variant = decl.variants[i - 1]
                                if last_variant.has_value:
                                    variant.value = str(
                                        int(
                                            self.eval_size(last_variant.value
                                                           ).lit, 0
                                        ) + 1
                                    )
                                    continue
                            variant.value = str(i)
                    for attribute in decl.attributes.attributes:
                        if attribute.name == "default_value":
                            decl.sym.default_value = attribute.args[0].expr
                            self.resolve_expr(decl.sym.default_value)
                    for base in decl.bases:
                        self.inside_extend_type = True
                        if self.resolve_type(base):
                            base_sym = base.symbol()
                            if base_sym.kind == sym.TypeKind.Trait:
                                base_sym.info.implement(decl.sym)
                        self.inside_extend_type = False
                    for v in decl.variants:
                        if len(v.decls) > 0:
                            self.self_sym = v.typ.symbol()
                            self.resolve_decls(v.decls)
                    self.self_sym = decl.sym
                    self.resolve_decls(decl.decls)
            elif isinstance(decl, ast.TraitDecl):
                for base in decl.bases:
                    self.inside_extend_type = True
                    if self.resolve_type(base):
                        base_sym = base.symbol()
                        if base_sym.kind == sym.TypeKind.Trait:
                            decl.sym.info.bases.append(base_sym)
                            for impl in decl.sym.info.implements:
                                if base_sym not in impl.info.traits:
                                    base_sym.info.implement(impl)
                                    impl.info.traits.append(base_sym)
                    self.inside_extend_type = False
                self.self_sym = decl.sym
                self.resolve_decls(decl.decls)
            elif isinstance(decl, ast.StructDecl):
                self.self_sym = decl.sym
                for base in decl.bases:
                    self.inside_extend_type = True
                    if self.resolve_type(base):
                        base_sym = base.symbol()
                        if base_sym.kind == sym.TypeKind.Trait:
                            decl.sym.info.traits.append(base_sym)
                            base_sym.info.implement(decl.sym)
                        elif base_sym.kind == sym.TypeKind.Struct:
                            decl.sym.info.bases.append(base_sym)
                            for b_trait in base_sym.info.traits:
                                b_trait.info.implement(decl.sym)
                    self.inside_extend_type = False
                self.resolve_decls(decl.decls)
            elif isinstance(decl, ast.FieldDecl):
                self.resolve_type(decl.typ)
                if decl.has_def_expr:
                    self.resolve_expr(decl.def_expr)
            elif isinstance(decl, ast.ExtendDecl):
                self.inside_extend_type = True
                if self.resolve_type(decl.typ):
                    self.self_sym = decl.typ.symbol()
                    for base in decl.bases:
                        if self.resolve_type(base):
                            base_sym = base.symbol()
                            if base_sym.kind == sym.TypeKind.Trait:
                                base_sym.info.implements.append(self.self_sym)
                            elif self.self_sym.kind == sym.TypeKind.Struct and self.self_sym.kind == base_sym.kind:
                                self.self_sym.info.bases.append(base_sym)
                    self.inside_extend_type = False
                    self.resolve_decls(decl.decls)
            elif isinstance(decl, ast.FuncDecl):
                if decl.is_method:
                    self_typ = type.Type(self.self_sym)
                    if decl.self_is_ptr:
                        self_typ = type.Ptr(self_typ, decl.self_is_mut)
                    elif decl.self_is_boxed:
                        self_typ.is_boxed = True
                        self_typ.is_mut = decl.self_is_mut
                    try:
                        decl.scope.add(
                            sym.Obj(
                                False, "self", self_typ, sym.ObjLevel.Rec,
                                decl.name_pos
                            )
                        )
                    except utils.CompilerError as e:
                        report.error(e.args[0], decl.name_pos)
                    decl.self_typ = self_typ
                    decl.sym.self_typ = self_typ
                for arg in decl.args:
                    self.resolve_type(arg.typ)
                    try:
                        decl.scope.add(
                            sym.Obj(
                                arg.is_mut, arg.name, arg.typ, sym.ObjLevel.Arg,
                                arg.pos
                            )
                        )
                    except utils.CompilerError as e:
                        report.error(e.args[0], arg.pos)
                    if arg.has_def_expr:
                        self.resolve_expr(arg.def_expr)
                self.resolve_type(decl.ret_typ)
                self.resolve_stmts(decl.stmts)
            elif isinstance(decl, ast.TestDecl):
                self.resolve_stmts(decl.stmts)
            self.sym = old_sym
            self.self_sym = old_self_sym

    def resolve_stmts(self, stmts):
        for stmt in stmts:
            self.resolve_stmt(stmt)

    def resolve_stmt(self, stmt):
        if isinstance(stmt, ast.ComptimeIf):
            self.resolve_stmts(self.comp.evalue_comptime_if(stmt))
        elif isinstance(stmt, ast.VarDeclStmt):
            for v in stmt.lefts:
                if v.has_typ:
                    self.resolve_type(v.typ)
                try:
                    stmt.scope.add(
                        sym.Obj(
                            v.is_mut, v.name, v.typ, sym.ObjLevel.Local, v.pos
                        )
                    )
                except utils.CompilerError as e:
                    report.error(e.args[0], v.pos)
            self.resolve_expr(stmt.right)
        elif isinstance(stmt, ast.WhileStmt):
            self.resolve_expr(stmt.cond)
            if stmt.has_continue_expr:
                self.resolve_expr(stmt.continue_expr)
            self.resolve_stmt(stmt.stmt)
            if stmt.has_else_stmt:
                self.resolve_stmt(stmt.else_stmt)
        elif isinstance(stmt, ast.ForStmt):
            if stmt.index != None:
                try:
                    stmt.scope.add(
                        sym.Obj(
                            False, stmt.index.name, self.comp.void_t,
                            sym.ObjLevel.Local, stmt.index.pos
                        )
                    )
                except utils.CompilerError as e:
                    report.error(e.args[0], stmt.index.pos)
            try:
                stmt.scope.add(
                    sym.Obj(
                        False, stmt.value.name, self.comp.void_t,
                        sym.ObjLevel.Local, stmt.value.pos
                    )
                )
            except utils.CompilerError as e:
                report.error(e.args[0], stmt.value.pos)
            self.resolve_expr(stmt.iterable)
            self.resolve_stmt(stmt.stmt)
        elif isinstance(stmt, ast.DeferStmt):
            self.resolve_expr(stmt.expr)
        elif isinstance(stmt, ast.ExprStmt):
            self.resolve_expr(stmt.expr)

    def resolve_expr(self, expr):
        if isinstance(expr, ast.EmptyExpr):
            report.error("empty expression found", expr.pos)
            report.note("unexpected bug, please, report it")
        elif isinstance(expr, ast.ComptimeIf):
            self.resolve_expr(self.comp.evalue_comptime_if(expr)[0])
        elif isinstance(expr, ast.TypeNode):
            self.resolve_type(expr.typ)
        elif isinstance(expr, ast.AssignExpr):
            self.resolve_expr(expr.left)
            self.resolve_expr(expr.right)
        elif isinstance(expr, ast.Ident):
            self.resolve_ident(expr)
        elif isinstance(expr, ast.SelfExpr):
            if self_ := expr.scope.lookup("self"):
                expr.obj = self_
                expr.typ = self_.typ
            else:
                report.error("cannot resolve `self` expression", expr.pos)
        elif isinstance(expr, ast.SelfTyExpr):
            if self.self_sym:
                expr.sym = self.self_sym
            else:
                report.error("cannot resolve `Self` expression", expr.pos)
        elif isinstance(expr, ast.TupleLiteral):
            for e in expr.exprs:
                self.resolve_expr(e)
        elif isinstance(expr, ast.ArrayCtor):
            self.resolve_type(expr.elem_type)
            if expr.init_value:
                self.resolve_expr(expr.init_value)
            if expr.cap_value:
                self.resolve_expr(expr.cap_value)
            if expr.len_value:
                self.resolve_expr(expr.len_value)
                if not expr.is_dyn:
                    expr.len_res = self.eval_size(expr.len_value)
        elif isinstance(expr, ast.ArrayLiteral):
            for e in expr.elems:
                self.resolve_expr(e)
        elif isinstance(expr, ast.GuardExpr):
            for v in expr.vars:
                try:
                    expr.scope.add(
                        sym.Obj(
                            v.is_mut, v.name, self.comp.void_t, False, v.pos
                        )
                    )
                except utils.CompilerError as e:
                    report.error(e.args[0], v.pos)
            self.resolve_expr(expr.expr)
            if expr.has_cond:
                self.resolve_expr(expr.cond)
        elif isinstance(expr, ast.UnaryExpr):
            self.resolve_expr(expr.right)
        elif isinstance(expr, ast.BinaryExpr):
            self.resolve_expr(expr.left)
            self.inside_typematch_type = expr.op in (Kind.KwIs, Kind.KwNotIs)
            self.resolve_expr(expr.right)
            self.inside_typematch_type = False
            if expr.has_var:
                try:
                    expr.scope.add(
                        sym.Obj(
                            False, expr.var.name, self.comp.void_t,
                            sym.ObjLevel.Local, expr.var.pos
                        )
                    )
                except utils.CompilerError as e:
                    report.error(e.args[0], expr.var.pos)
        elif isinstance(expr, ast.ParExpr):
            self.resolve_expr(expr.expr)
        elif isinstance(expr, ast.IndexExpr):
            self.resolve_expr(expr.left)
            self.resolve_expr(expr.index)
        elif isinstance(expr, ast.CallExpr):
            self.resolve_expr(expr.left)
            for arg in expr.args:
                self.resolve_expr(arg.expr)
            if expr.has_spread_expr:
                self.resolve_expr(expr.spread_expr)
            if expr.err_handler.has_expr:
                if expr.err_handler.has_varname():
                    # register error value
                    try:
                        expr.err_handler.scope.add(
                            sym.Obj(
                                False, expr.err_handler.varname,
                                self.comp.throwable_t, sym.ObjLevel.Local,
                                expr.err_handler.varname_pos
                            )
                        )
                    except utils.CompilerError as e:
                        report.error(e.args[0], expr.err_handler.varname_pos)
                self.resolve_expr(expr.err_handler.expr)
        elif isinstance(expr, ast.BuiltinCallExpr):
            for arg in expr.args:
                self.resolve_expr(arg)
        elif isinstance(expr, ast.RangeExpr):
            if expr.has_start:
                self.resolve_expr(expr.start)
            if expr.has_end:
                self.resolve_expr(expr.end)
        elif isinstance(expr, ast.SelectorExpr):
            self.resolve_selector_expr(expr)
        elif isinstance(expr, ast.ReturnExpr):
            if expr.has_expr:
                self.resolve_expr(expr.expr)
        elif isinstance(expr, ast.ThrowExpr):
            self.resolve_expr(expr.expr)
        elif isinstance(expr, ast.Block):
            self.resolve_stmts(expr.stmts)
            if expr.is_expr:
                self.resolve_expr(expr.expr)
        elif isinstance(expr, ast.IfExpr):
            for b in expr.branches:
                if not b.is_else:
                    self.resolve_expr(b.cond)
                self.resolve_expr(b.expr)
        elif isinstance(expr, ast.MatchExpr):
            self.resolve_expr(expr.expr)
            for b in expr.branches:
                if not b.is_else:
                    for pat in b.pats:
                        self.inside_typematch_type = expr.is_typematch
                        self.resolve_expr(pat)
                        self.inside_typematch_type = False
                    if b.has_var:
                        try:
                            b.scope.add(
                                sym.Obj(
                                    False, b.var_name, self.comp.void_t,
                                    sym.ObjLevel.Local, b.var_pos
                                )
                            )
                        except utils.CompilerError as e:
                            report.error(e.args[0], b.var_pos)
                    if b.has_cond:
                        self.resolve_expr(b.cond)
                self.resolve_expr(b.expr)

    def find_symbol(self, symbol, name, pos):
        if isinstance(symbol, sym.SymRef):
            symbol = symbol.ref
        if s := symbol.find(name):
            self.check_vis(s, pos)
            if isinstance(s, sym.SymRef):
                return self.clean_sym_ref(s)
            return s
        elif isinstance(symbol, sym.Type) and symbol.kind == sym.TypeKind.Enum:
            if symbol.info.has_variant(name):
                return symbol
            else:
                report.error(
                    f"enum `{symbol.name}` has no variant `{name}`", pos
                )
                return None
        report.error(
            f"could not find `{name}` in {symbol.typeof()} `{symbol.name}`", pos
        )
        return None

    def find_prelude(self, name):
        if name in self.preludes:
            return self.preludes[name]
        return None

    def resolve_ident(self, ident):
        if ident.name == "_":
            ident.is_obj = True
            return # ignore special var
        elif ident.is_comptime:
            if not ast.is_comptime_constant(ident.name):
                report.error(
                    f"unknown comptime constant `{ident.name}`", ident.pos
                )
            return
        elif obj := ident.scope.lookup(ident.name):
            ident.obj = obj
            ident.typ = obj.typ
            ident.is_obj = True
        elif s := self.source_file.find_imported_symbol(ident.name):
            if isinstance(s, sym.Type) and s.kind == sym.TypeKind.Placeholder:
                report.error(
                    f"cannot find `{ident.name}` in this scope", ident.pos
                )
                ident.not_found = True
            ident.sym = s
            ident.is_sym = True
        elif s := self.find_prelude(ident.name):
            ident.sym = s
            ident.is_sym = True
        elif s := self.sym.find(ident.name):
            if isinstance(s, sym.Type) and s.kind == sym.TypeKind.Placeholder:
                report.error(
                    f"cannot find `{ident.name}` in this scope", ident.pos
                )
                ident.not_found = True
            ident.sym = s
            ident.is_sym = True
        elif s := self.comp.universe.find(ident.name):
            if isinstance(s, sym.Mod):
                report.error(
                    f"use of non-imported module `{ident.name}`", ident.pos
                )
                report.help("add an `import` with the path to the module")
            ident.sym = s
            ident.is_sym = True
        elif self.self_sym:
            if s := self.self_sym.find(ident.name):
                if not (
                    isinstance(s, sym.Type)
                    and s.kind == sym.TypeKind.Placeholder
                ):
                    ident.sym = s
                    ident.is_sym = True
        if ident.sym == None and ident.obj == None:
            report.error(f"cannot find `{ident.name}` in this scope", ident.pos)
            ident.not_found = True
        elif isinstance(ident.sym, sym.SymRef):
            ident.sym = self.clean_sym_ref(ident.sym)

    def clean_sym_ref(self, sym_ref):
        if not sym_ref.ref_resolved:
            sym_ref.ref_resolved = True
            self.resolve_expr(sym_ref.ref)
        if isinstance(
            sym_ref.ref, ast.SelectorExpr
        ) and sym_ref.ref.is_path and not sym_ref.ref.not_found:
            return sym_ref.ref.field_sym
        elif isinstance(sym_ref.ref, ast.Ident) and sym_ref.ref.sym:
            return sym_ref.ref.sym
        return sym_ref.ref

    def resolve_selector_expr(self, expr):
        self.resolve_expr(expr.left)
        if not (expr.is_indirect or expr.is_option_check):
            if isinstance(expr.left, ast.SelfTyExpr):
                expr.is_path = True
                if expr.left.sym == None:
                    expr.not_found = True
                    return
                expr.left_sym = expr.left.sym
            elif isinstance(expr.left, ast.Ident) and expr.left.is_sym:
                if isinstance(expr.left.sym, (sym.Var, sym.Const)):
                    return
                expr.is_path = True
                if expr.left.not_found:
                    expr.not_found = True
                    return
                expr.left_sym = expr.left.sym
            elif isinstance(expr.left, ast.SelectorExpr) and expr.left.is_path:
                if isinstance(expr.left.field_sym, (sym.Var, sym.Const)):
                    return
                expr.is_path = True
                if expr.left.not_found:
                    expr.not_found = True
                    return
                expr.left_sym = expr.left.field_sym
            if expr.is_path:
                if field_sym := self.find_symbol(
                    expr.left_sym, expr.field_name, expr.field_pos
                ):
                    expr.field_sym = field_sym
                else:
                    expr.not_found = True

    def resolve_type(self, typ):
        if isinstance(typ, type.Boxedptr):
            return True
        elif isinstance(typ, type.Ptr):
            return self.resolve_type(typ.typ)
        elif isinstance(typ, type.Variadic):
            if self.resolve_type(typ.typ):
                elem_sym = typ.typ.symbol()
                if elem_sym.kind == type.TypeKind.Trait:
                    elem_sym.info.has_objects = True
                typ.resolve(self.comp.universe.add_or_get_slice(typ.typ))
                return True
        elif isinstance(typ, type.Array):
            if self.resolve_type(typ.typ):
                if typ_size := self.eval_size(typ.size):
                    if int(typ_size.lit, 0) <= 0:
                        report.error(
                            f"array size cannot be zero or negative (size: {typ_size.lit})",
                            typ.size.pos
                        )
                    typ.size = typ_size
                    typ.resolve(
                        self.comp.universe.add_or_get_array(
                            typ.typ, typ_size, typ.is_mut
                        )
                    )
                    return True
                report.error(
                    "array size cannot use non-constant value", typ.size.pos
                )
        elif isinstance(typ, type.DynArray):
            if self.resolve_type(typ.typ):
                typ.resolve(
                    self.comp.universe.add_or_get_dyn_array(
                        typ.typ, typ.is_mut
                    )
                )
                return True
        elif isinstance(typ, type.Slice):
            if self.resolve_type(typ.typ):
                typ.resolve(
                    self.comp.universe.add_or_get_slice(typ.typ, typ.is_mut)
                )
                return True
        elif isinstance(typ, type.Tuple):
            res = False
            for t in typ.types:
                res = self.resolve_type(t)
            typ.resolve(self.comp.universe.add_or_get_tuple(typ.types))
            return res
        elif isinstance(typ, type.Func):
            res = False
            for i in range(len(typ.args)):
                res = self.resolve_type(typ.args[i].typ)
            res = self.resolve_type(typ.ret_typ)
            return res
        elif isinstance(typ, type.Option):
            if self.resolve_type(typ.typ):
                return True
            return False
        elif isinstance(typ, type.Result):
            if self.resolve_type(typ.typ):
                self.comp.throwable_sym.info.has_objects = True
                return True
            return False
        elif isinstance(typ, type.Type):
            if typ.is_resolved():
                return True # resolved
            result = False
            if isinstance(typ.expr, ast.Ident):
                self.resolve_ident(typ.expr)
                if typ.expr.sym != None:
                    if isinstance(typ.expr.sym, sym.Type):
                        pos = typ.expr.pos
                        typ.resolve(typ.expr.sym)
                        if typ.expr.sym.kind == sym.TypeKind.Alias: # unalias
                            if self.resolve_type(typ.expr.sym.info.parent):
                                typ.unalias()
                        typ_sym = typ.symbol()
                        result = True
                    else:
                        report.error(
                            f"expected type, found {typ.expr.sym.typeof()}",
                            typ.expr.pos
                        )
                elif typ.expr.is_obj:
                    report.error(
                        f"cannot find type `{typ.expr.name}` in this scope",
                        typ.expr.pos
                    )
            elif isinstance(typ.expr, ast.SelectorExpr):
                self.resolve_selector_expr(typ.expr)
                if (not typ.expr.not_found) and typ.expr.field_sym:
                    if typ.expr.field_sym.kind == sym.TypeKind.Placeholder:
                        report.error(
                            f"cannot find type `{typ.expr.field_sym.name}`",
                            typ.expr.pos
                        )
                    elif isinstance(typ.expr.field_sym, sym.Type):
                        pos = typ.expr.pos
                        typ.resolve(typ.expr.field_sym)
                        if typ.expr.field_sym.kind == sym.TypeKind.Alias: # unalias
                            if self.resolve_type(
                                typ.expr.field_sym.info.parent
                            ):
                                typ.unalias()
                        result = True
                    else:
                        report.error(
                            f"expected type, found {typ.expr.field_sym.typeof()}",
                            typ.expr.pos
                        )
            elif isinstance(typ.expr, ast.SelfTyExpr):
                if self.self_sym:
                    typ.resolve(self.self_sym)
                    result = True
                else:
                    report.error("cannot resolve type for `Self`", typ.expr.pos)
            else:
                report.error(f"expected type, found {typ.expr}", typ.expr.pos)
            if result and isinstance(
                typ, type.Type
            ) and not typ.is_boxed and not self.inside_extend_type and not self.inside_typematch_type:
                tsym = typ.symbol()
                if isinstance(tsym, sym.Type) and tsym.is_boxed():
                    report.error(
                        f"cannot use type `{tsym.name}` as a simple value",
                        typ.expr.pos
                    )
                    report.help(
                        f"type `{tsym.name}` is boxed, you should use `^{typ.expr}` instead"
                    )
            return result
        return False

    def eval_size(self, expr):
        if isinstance(expr, ast.ComptimeIf):
            return self.eval_size(self.comp.evalue_comptime_if(expr)[0])
        elif isinstance(expr, ast.Block) and expr.is_expr:
            return self.eval_size(expr.expr)
        elif isinstance(expr, ast.IntegerLiteral):
            return expr
        elif isinstance(expr, ast.ParExpr):
            return self.eval_size(expr.expr)
        elif isinstance(expr, ast.BinaryExpr):
            if left := self.eval_size(expr.left):
                if right := self.eval_size(expr.right):
                    il = int(left.lit, 0)
                    ir = int(right.lit, 0)
                    if expr.op == Kind.Plus:
                        return ast.IntegerLiteral(str(il + ir), expr.pos)
                    elif expr.op == Kind.Minus:
                        return ast.IntegerLiteral(str(il - ir), expr.pos)
                    elif expr.op == Kind.Mul:
                        return ast.IntegerLiteral(str(il * ir), expr.pos)
                    elif expr.op == Kind.Div:
                        return ast.IntegerLiteral(str(il // ir), expr.pos)
                    elif expr.op == Kind.Mod:
                        return ast.IntegerLiteral(str(il % ir), expr.pos)
                    elif expr.op == Kind.Amp:
                        return ast.IntegerLiteral(str(il & ir), expr.pos)
                    elif expr.op == Kind.Pipe:
                        return ast.IntegerLiteral(str(il | ir), expr.pos)
                    elif expr.op == Kind.Xor:
                        return ast.IntegerLiteral(str(il ^ ir), expr.pos)
                    elif expr.op == Kind.Lshift:
                        return ast.IntegerLiteral(str(il << ir), expr.pos)
                    elif expr.op == Kind.Rshift:
                        return ast.IntegerLiteral(str(il >> ir), expr.pos)
        elif isinstance(expr, ast.Ident):
            if s := self.source_file.sym.find(expr.name):
                if isinstance(s, sym.Const):
                    if s.has_evaled_expr:
                        return s.evaled_expr
                    if evaled_expr := self.eval_size(s.expr):
                        s.evaled_expr = evaled_expr
                        s.has_evaled_expr = True
                        return s.evaled_expr
            else:
                report.error(
                    f"cannot find `{expr.name}` in this scope", expr.pos
                )
        elif isinstance(expr, ast.SelectorExpr):
            self.resolve_selector_expr(expr)
            if not expr.not_found:
                if isinstance(expr.field_sym, sym.Const):
                    if expr.field_sym.has_evaled_expr:
                        return expr.field_sym.evaled_expr
                    if evaled_expr := self.eval_size(expr.field_sym.expr):
                        expr.field_sym.evaled_expr = evaled_expr
                        expr.field_sym.has_evaled_expr = True
                        return expr.field_sym.evaled_expr
        elif isinstance(expr, ast.BuiltinCallExpr):
            if expr.name in ("size_of", "align_of"):
                if self.resolve_type(expr.args[0].typ):
                    size, align = self.comp.type_size(expr.args[0].typ)
                    if expr.name == "size_of":
                        return ast.IntegerLiteral(str(size), expr.pos)
                    else:
                        return ast.IntegerLiteral(str(align), expr.pos)
        return None

    def check_vis(self, sym, pos):
        if not sym.is_public and not self.source_file.sym.has_access_to(sym):
            report.error(f"{sym.typeof()} `{sym.name}` is private", pos)
