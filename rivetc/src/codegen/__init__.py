# Copyright (C) 2023 Jose Mendoza. All rights reserved.
# Use of this source code is governed by an MIT license that can
# be found in the LICENSE file.

import os

from ..sym import TypeKind
from .. import ast, sym, type, token, prefs, report, utils
from ..token import Kind, OVERLOADABLE_OPERATORS_STR, NO_POS

from .c import CGen
from . import ir, cg_utils

class TestInfo:
    def __init__(self, name, func):
        self.name = name
        self.func = func

class Codegen:
    def __init__(self, comp):
        self.comp = comp
        self.out_rir = ir.RIRFile(self.comp.prefs.mod_name)
        self.void_types = (self.comp.void_t, self.comp.never_t)

        self.source_file = None

        self.init_global_vars_fn = None
        self.cur_func = None
        self.cur_func_is_main = False
        self.cur_func_ret_typ = self.comp.void_t
        self.cur_func_defer_stmts = []

        self.inside_trait = False
        self.inside_test = False
        self.inside_var_decl = False
        self.inside_selector_expr = False
        self.inside_lhs_assign = False

        self.generated_string_literals = {}
        self.generated_tuple_types = []
        self.generated_opt_res_types = []
        self.generated_array_returns = []
        self.generated_tests = []

        self.loop_entry_label = ""
        self.loop_exit_label = ""
        self.loop_scope = None
        self.while_continue_expr = None

    def gen_source_files(self, source_files):
        for mod in self.comp.universe.syms:
            if isinstance(mod, sym.Mod):
                self.gen_mod_attributes(mod.name, mod.attributes)

        self.gen_types()

        self.out_rir.globals.append(
            ir.GlobalVar(False, False, ir.DYN_ARRAY_T, "_R4core4ARGS")
        )

        # generate 'init_string_lits' function
        self.init_string_lits_fn = ir.FuncDecl(
            False, ast.Attributes(), False, "_R4core16init_string_litsF", [],
            False, ir.VOID_T, False
        )
        self.out_rir.decls.append(self.init_string_lits_fn)

        # generate 'init_globals' function
        self.init_global_vars_fn = ir.FuncDecl(
            False, ast.Attributes(), False, "_R4core12init_globalsF", [], False,
            ir.VOID_T, False
        )
        self.out_rir.decls.append(self.init_global_vars_fn)

        # generate 'drop_globals' function
        g_fn = ir.FuncDecl(
            False, ast.Attributes(), False, "_R4core15destroy_globalsF", [],
            False, ir.VOID_T, False
        )
        self.out_rir.decls.append(g_fn)

        for source_file in source_files:
            self.source_file = source_file
            self.gen_decls(source_file.decls)

        # generate 'main' function
        argc = ir.Ident(ir.C_INT_T, "_argc")
        argv = ir.Ident(ir.CHAR_T.ptr().ptr(), "_argv")
        main_fn = ir.FuncDecl(
            False, ast.Attributes(), False, "main", [argc, argv], False,
            ir.C_INT_T, False
        )
        if self.comp.prefs.build_mode == prefs.BuildMode.Test:
            self.cur_func = main_fn
            self.cur_func.add_call("_R4core16init_string_litsF")
            testRunner = ir.Ident(ir.TEST_RUNNER_T, "_testRunner")
            main_fn.alloca(testRunner)
            tests_field = ir.Selector(
                ir.DYN_ARRAY_T, testRunner, ir.Name("tests")
            )
            main_fn.store(
                ir.Selector(ir.UINT64_T, testRunner, ir.Name("ok_tests")),
                ir.IntLit(ir.UINT64_T, "0")
            )
            main_fn.store(
                ir.Selector(ir.UINT64_T, testRunner, ir.Name("fail_tests")),
                ir.IntLit(ir.UINT64_T, "0")
            )
            main_fn.store(
                ir.Selector(ir.UINT64_T, testRunner, ir.Name("skip_tests")),
                ir.IntLit(ir.UINT64_T, "0")
            )
            tests_dyn_array = ir.Selector(
                ir.DYN_ARRAY_T, testRunner, ir.Name("tests")
            )
            test_t = ir.TEST_T.ptr()
            gtests_array = []
            for i, gtest in enumerate(self.generated_tests):
                test_value = ir.Ident(ir.TEST_T, f"test_value_{i}")
                main_fn.alloca(test_value)
                main_fn.store(
                    ir.Selector(ir.UINT8_T, test_value, ir.Name("result")),
                    ir.IntLit(ir.UINT8_T, "0")
                )
                main_fn.store(
                    ir.Selector(ir.STRING_T, test_value, ir.Name("err_pos")),
                    ir.Ident(ir.STRING_T, "_R4core12empty_string")
                )
                main_fn.store(
                    ir.Selector(ir.STRING_T, test_value, ir.Name("err_msg")),
                    ir.Ident(ir.STRING_T, "_R4core12empty_string")
                )
                main_fn.store(
                    ir.Selector(ir.STRING_T, test_value, ir.Name("name")),
                    self.gen_string_literal(gtest.name)
                )
                main_fn.store(
                    ir.Selector(
                        ir.Function(test_t, ir.VOID_T), test_value,
                        ir.Name("fn")
                    ), ir.Name(gtest.func)
                )
                gtests_array.append(test_value)
            test_t_size, _ = self.comp.type_size(
                type.Type(self.comp.universe["core"]["Test"])
            )
            main_fn.store(
                tests_field,
                ir.Inst(
                    ir.InstKind.Call, [
                        ir.Name("_R4core8DynArray19from_array_no_allocF"),
                        ir.ArrayLit(
                            ir.Array(ir.TEST_T, str(len(self.generated_tests))),
                            gtests_array
                        ),
                        ir.IntLit(ir.UINT_T, str(test_t_size)),
                        ir.IntLit(ir.UINT_T, str(len(self.generated_tests)))
                    ]
                )
            )
            main_fn.add_call(
                "_R4core4mainF", [
                    argc,
                    ir.Inst(ir.InstKind.Cast,
                            [argv, ir.UINT8_T.ptr().ptr()]),
                    ir.Inst(ir.InstKind.GetPtr, [testRunner])
                ]
            )
        else:
            main_fn.add_call(
                "_R4core4mainF", [
                    argc,
                    ir.Inst(ir.InstKind.Cast,
                            [argv, ir.UINT8_T.ptr().ptr()]),
                    ir.Name(
                        f"_R{len(self.comp.prefs.mod_name)}{self.comp.prefs.mod_name}4mainF"
                    )
                ]
            )
        main_fn.add_ret(ir.IntLit(ir.C_INT_T, "0"))
        self.out_rir.decls.append(main_fn)

        if report.ERRORS == 0:
            if self.comp.prefs.emit_rir:
                self.comp.vlog("generating RIR output (with --emit-rir)...")
                with open(f"{self.comp.prefs.mod_name}.rir", "w") as f:
                    f.write(str(self.out_rir).strip())
            if self.comp.prefs.target_backend == prefs.Backend.C:
                self.comp.vlog("generating C output from RIR...")
                CGen(self.comp).gen(self.out_rir)
            if self.comp.prefs.build_mode == prefs.BuildMode.Test:
                exit_code = os.system(self.comp.prefs.mod_output)
                os.remove(self.comp.prefs.mod_output)
                # assert exit_code == 0
                if exit_code != 0:
                    exit(1)

    def gen_mod_attributes(self, mod_name, attributes):
        mod_folder = os.path.join(prefs.RIVET_DIR, "obj", mod_name)
        if attributes == None:
            return
        for attribute in attributes.attributes:
            if attribute.name == "link_library":
                self.comp.prefs.libraries_to_link.append(
                    attribute.args[0].expr.lit
                )
            elif attribute.name == "compile_c_source":
                if not os.path.exists(mod_folder):
                    os.mkdir(mod_folder)
                old_wd = os.getcwd()
                os.chdir(os.path.dirname(os.path.realpath(attribute.pos.file)))
                cfile = os.path.realpath(attribute.args[0].expr.lit)
                os.chdir(old_wd)
                objfile = os.path.join(
                    mod_folder,
                    f"{os.path.basename(cfile)}.{self.comp.prefs.get_obj_postfix()}.o"
                )
                self.comp.prefs.objects_to_link.append(objfile)
                msg = f"compile_c_source: compiling object for C file `{cfile}`..."
                if os.path.exists(objfile):
                    if os.path.getmtime(objfile) < os.path.getmtime(cfile):
                        msg = f"compile_c_source: {objfile} is older than {cfile}, rebuilding..."
                    else:
                        continue
                self.comp.vlog(msg)
                args = [
                    self.comp.prefs.target_backend_compiler, "-c", "-o",
                    objfile, cfile, "-m64" if self.comp.prefs.target_bits
                    == prefs.Bits.X64 else "-m32",
                    "-O3" if self.comp.prefs.build_mode
                    == prefs.BuildMode.Release else "-g",
                    f'-L{os.path.dirname(cfile)}',
                ]
                for f in self.comp.prefs.flags:
                    args.append(f"-D{f}")
                self.comp.vlog(f"  compile_c_source: Arguments: {args}")
                res = utils.execute(*args)
                if res.exit_code != 0:
                    utils.error(
                        f"error while compiling the object file `{objfile}`:\n{res.err}"
                    )
        if report.ERRORS > 0:
            self.abort()

    def gen_decls(self, decls):
        for decl in decls:
            self.gen_decl(decl)

    def gen_decl(self, decl):
        self.cur_func_defer_stmts = []
        if isinstance(decl, ast.ComptimeIf):
            self.gen_decls(self.comp.evalue_comptime_if(decl))
        elif isinstance(decl, ast.ExternDecl):
            if decl.abi != sym.ABI.Rivet:
                self.gen_decls(decl.decls)
        elif isinstance(decl, ast.VarDecl):
            self.inside_var_decl = True
            for l in decl.lefts:
                is_extern = decl.is_extern and decl.abi != sym.ABI.Rivet
                name = l.name if is_extern else cg_utils.mangle_symbol(l.sym)
                typ = self.ir_type(l.typ)
                self.out_rir.globals.append(
                    ir.GlobalVar(is_extern, is_extern, typ, name)
                )
                if not decl.is_extern:
                    ident = ir.Ident(typ, name)
                    self.cur_func = self.init_global_vars_fn
                    value = self.gen_expr_with_cast(l.typ, decl.right)
                    if isinstance(typ, ir.Array):
                        size, _ = self.comp.type_size(l.typ)
                        if isinstance(value,
                                      ir.ArrayLit) and len(value.elems) > 0:
                            self.cur_func.add_call(
                                "_R4core3mem4copyF",
                                [ident, value,
                                 ir.IntLit(ir.UINT_T, str(size))]
                            )
                    else:
                        self.cur_func.store(ident, value)
            self.inside_var_decl = False
        elif isinstance(decl, ast.EnumDecl):
            for v in decl.variants:
                self.gen_decls(v.decls)
            self.gen_decls(decl.decls)
        elif isinstance(decl, ast.TraitDecl):
            self.inside_trait = True
            self.gen_decls(decl.decls)
            self.inside_trait = False
        elif isinstance(decl, ast.StructDecl):
            self.gen_decls(decl.decls)
        elif isinstance(decl, ast.ExtendDecl):
            self.gen_decls(decl.decls)
        elif isinstance(decl, ast.FuncDecl):
            if self.inside_trait and not decl.has_body:
                return
            if decl.is_main and self.comp.prefs.build_mode == prefs.BuildMode.Test:
                return
            args = []
            if decl.is_method:
                self_typ = self.ir_type(decl.self_typ)
                if (decl.self_is_ptr or
                    decl.self_is_boxed) and not isinstance(self_typ, ir.Ptr):
                    self_typ = self_typ.ptr(decl.self_is_boxed)
                args.append(ir.Ident(self_typ, "self"))
            for i, arg in enumerate(decl.args):
                if self.inside_trait and i == 0: continue
                arg_typ = self.ir_type(arg.typ)
                arg_typ_sym = arg.typ.symbol()
                args.append(ir.Ident(arg_typ, arg.name))
            ret_typ = self.ir_type(decl.ret_typ)
            arr_ret_struct = ""
            if isinstance(ret_typ, ir.Array):
                # In C functions cannot return an array, so we create a special
                # struct for this.
                if self.comp.prefs.target_backend == prefs.Backend.C:
                    name = f"ArrayReturn{len(self.generated_array_returns)}"
                    name = f"_R{len(name)}{name}"
                    if name not in self.generated_array_returns:
                        arr_ret_struct = name
                        self.out_rir.types.append(
                            ir.Struct(False, name, [ir.Field("arr", ret_typ)])
                        )
                        self.generated_array_returns.append(name)
                    ret_typ = ir.Type(name)
            if decl.is_extern and not decl.has_body:
                name = decl.sym.name
            elif (not decl.is_method) and decl.attributes.has("export"):
                export_attribute = decl.attributes.find("export")
                if isinstance(export_attribute.args[0].expr, ast.StringLiteral):
                    name = export_attribute.args[0].expr.lit
                else:
                    assert False
            else:
                name = cg_utils.mangle_symbol(decl.sym)
            fn_decl = ir.FuncDecl(
                False, decl.attributes, decl.is_extern and not decl.has_body,
                name, args, decl.is_variadic and decl.is_extern, ret_typ,
                decl.ret_typ == self.comp.never_t
            )
            self.cur_func = fn_decl
            self.cur_func.arr_ret_struct = arr_ret_struct
            self.cur_func_is_main = decl.is_main
            self.cur_func_ret_typ = decl.ret_typ
            self.gen_defer_stmt_vars(decl.defer_stmts)
            self.gen_stmts(decl.stmts)
            fn_dec_ret_type_str = str(fn_decl.ret_typ)
            if fn_dec_ret_type_str == "void" or fn_dec_ret_type_str == "_R6Result_R4void":
                self.gen_defer_stmts(scope = decl.scope)
            if fn_dec_ret_type_str == "_R6Result_R4void" and len(
                fn_decl.instrs
            ) == 0:
                self.cur_func.add_ret(self.result_void(decl.ret_typ))
            elif fn_dec_ret_type_str != "void" and not (
                len(fn_decl.instrs) > 0
                and isinstance(fn_decl.instrs[-1], ir.Inst)
                and fn_decl.instrs[-1].kind == ir.InstKind.Ret
            ):
                self.cur_func.add_ret(self.default_value(decl.ret_typ))
            if decl.is_extern and not decl.has_body:
                self.out_rir.externs.append(fn_decl)
            else:
                self.out_rir.decls.append(fn_decl)
        elif isinstance(decl, ast.TestDecl):
            if self.comp.prefs.build_mode == prefs.BuildMode.Test:
                if not self.source_file.sym.is_root:
                    return # skip non-root module tests
                self.inside_test = True
                test_name = utils.smart_quote(decl.name, True)
                test_func = f"__test{len(self.generated_tests)}__"
                test_func = f"_R{len(test_func)}{test_func}"
                test_fn = ir.FuncDecl(
                    False, ast.Attributes(), False, test_func,
                    [ir.Ident(ir.TEST_T.ptr(), "test")], False, ir.VOID_T, False
                )
                self.cur_func = test_fn
                self.gen_defer_stmt_vars(decl.defer_stmts)
                self.gen_stmts(decl.stmts)
                self.gen_defer_stmts(scope = decl.scope)
                self.generated_tests.append(TestInfo(test_name, test_func))
                self.out_rir.decls.append(test_fn)
                self.inside_test = False

    def gen_stmts(self, stmts):
        for stmt in stmts:
            self.gen_stmt(stmt)

    def gen_stmt(self, stmt):
        if isinstance(stmt, ast.ComptimeIf):
            self.gen_stmts(self.comp.evalue_comptime_if(stmt))
        elif isinstance(stmt, ast.ForStmt):
            old_loop_scope = self.loop_scope
            self.loop_scope = stmt.scope
            old_while_continue_expr = self.while_continue_expr
            old_entry_label = self.loop_entry_label
            old_exit_label = self.loop_exit_label
            iterable_sym = stmt.iterable.typ.symbol()
            self.loop_entry_label = self.cur_func.local_name()
            body_label = self.cur_func.local_name()
            self.loop_exit_label = self.cur_func.local_name()
            self.cur_func.add_comment("for in stmt")
            if stmt.index:
                idx_name = self.cur_func.unique_name(stmt.index.name)
                stmt.scope.update_ir_name(stmt.index.name, idx_name)
            else:
                idx_name = self.cur_func.local_name()
            iterable = self.gen_expr(stmt.iterable)
            self.cur_func.inline_alloca(
                ir.UINT_T, idx_name, ir.IntLit(ir.UINT_T, "0")
            )
            idx = ir.Ident(ir.UINT_T, idx_name)
            self.cur_func.add_label(self.loop_entry_label)
            if iterable_sym.kind == TypeKind.Array:
                len_ = ir.IntLit(ir.UINT_T, iterable_sym.info.size.lit)
            else:
                len_ = ir.Selector(ir.UINT_T, iterable, ir.Name("len"))
            self.cur_func.add_cond_br(
                ir.Inst(ir.InstKind.Cmp, [ir.Name("<"), idx, len_]), body_label,
                self.loop_exit_label
            )
            self.cur_func.add_label(body_label)
            value_t_ir = self.ir_type(iterable_sym.info.elem_typ)
            value_t_is_boxed = isinstance(
                value_t_ir, ir.Ptr
            ) and value_t_ir.is_managed
            if iterable_sym.kind == TypeKind.Array:
                value = ir.Inst(
                    ir.InstKind.GetElementPtr, [iterable, idx], value_t_ir
                )
            else:
                value = ir.Selector(ir.RAWPTR_T, iterable, ir.Name("ptr"))
                value = ir.Inst(
                    ir.InstKind.Add, [
                        ir.Inst(
                            ir.InstKind.Cast,
                            [value, value_t_ir.ptr(value_t_is_boxed)]
                        ), idx
                    ]
                )
            if stmt.value.is_ref and not isinstance(value_t_ir, ir.Ptr):
                value_t_ir = ir.Ptr(value_t_ir)
            if not stmt.value.is_ref or (
                isinstance(value_t_ir, ir.Ptr) and value_t_ir.is_managed
            ):
                value = ir.Inst(ir.InstKind.LoadPtr, [value], value_t_ir)
            unique_ir_name = self.cur_func.unique_name(stmt.value.name)
            self.cur_func.inline_alloca(value_t_ir, unique_ir_name, value)
            stmt.scope.update_ir_name(stmt.value.name, unique_ir_name)
            self.while_continue_expr = ir.Inst(ir.InstKind.Inc, [idx])
            self.gen_stmt(stmt.stmt)
            self.cur_func.add_inst(self.while_continue_expr)
            self.cur_func.add_br(self.loop_entry_label)
            self.cur_func.add_label(self.loop_exit_label)
            self.loop_entry_label = old_entry_label
            self.loop_exit_label = old_exit_label
            self.loop_scope = old_loop_scope
            self.while_continue_expr = old_while_continue_expr
        elif isinstance(stmt, ast.WhileStmt):
            old_loop_scope = self.loop_scope
            self.loop_scope = stmt.scope
            old_while_continue_expr = self.while_continue_expr
            old_entry_label = self.loop_entry_label
            old_exit_label = self.loop_exit_label
            self.cur_func.add_comment(f"while stmt (is_inf: {stmt.is_inf})")
            self.loop_entry_label = self.cur_func.local_name()
            body_label = self.cur_func.local_name()
            self.loop_exit_label = self.cur_func.local_name()
            else_stmt_label = self.cur_func.local_name(
            ) if stmt.has_else_stmt else ""
            self.while_continue_expr = stmt.continue_expr
            self.cur_func.add_label(self.loop_entry_label)
            if stmt.is_inf:
                cond = ir.IntLit(self.comp.bool_t, "1")
                self.cur_func.add_br(body_label)
            else:
                if isinstance(stmt.cond, ast.GuardExpr):
                    cond = self.gen_guard_expr(
                        stmt.cond, body_label, else_stmt_label
                        if stmt.has_else_stmt else self.loop_exit_label
                    )
                else:
                    cond = self.gen_expr_with_cast(self.comp.bool_t, stmt.cond)
                if isinstance(cond, ir.IntLit) and cond.lit == "1":
                    self.cur_func.add_br(body_label)
                else:
                    self.cur_func.add_cond_br(
                        cond, body_label, else_stmt_label
                        if stmt.has_else_stmt else self.loop_exit_label
                    )
            gen_stmt = True
            if isinstance(cond, ir.IntLit) and cond.lit == "0":
                self.cur_func.add_comment("skip while stmt (cond: false)")
                gen_stmt = False
            self.cur_func.add_label(body_label)
            if gen_stmt:
                self.gen_stmt(stmt.stmt)
                if stmt.has_continue_expr:
                    self.gen_expr(stmt.continue_expr)
                self.cur_func.add_comment(
                    f"while stmt (goto to `{self.loop_entry_label}` for continue)"
                )
                self.cur_func.add_br(self.loop_entry_label)
            if stmt.has_else_stmt:
                self.cur_func.add_label(else_stmt_label)
                self.gen_stmt(stmt.else_stmt)
            self.cur_func.add_label(self.loop_exit_label)
            self.loop_entry_label = old_entry_label
            self.loop_exit_label = old_exit_label
            self.loop_scope = old_loop_scope
            self.while_continue_expr = old_while_continue_expr
        elif isinstance(stmt, ast.VarDeclStmt):
            if len(stmt.lefts) == 1:
                left = stmt.lefts[0]
                left_ir_typ = self.ir_type(left.typ)
                ident = ir.Ident(
                    left_ir_typ,
                    self.cur_func.local_name() if left.name == "_" else
                    self.cur_func.unique_name(left.name)
                )
                stmt.scope.update_ir_name(left.name, ident.name)
                if isinstance(left_ir_typ, ir.Array):
                    size, _ = self.comp.type_size(left.typ)
                    self.cur_func.alloca(ident)
                    val = self.gen_expr_with_cast(left.typ, stmt.right, ident)
                    if isinstance(val, ir.ArrayLit) and len(val.elems) > 0:
                        self.cur_func.add_call(
                            "_R4core3mem4copyF",
                            [ident, val,
                             ir.IntLit(ir.UINT_T, str(size))]
                        )
                else:
                    self.cur_func.alloca(
                        ident, self.gen_expr_with_cast(left.typ, stmt.right)
                    )
            else:
                right = self.gen_expr(stmt.right)
                for i, left in enumerate(stmt.lefts):
                    left_ir_typ = self.ir_type(left.typ)
                    ident = ir.Ident(
                        left_ir_typ,
                        self.cur_func.local_name() if left.name == "_" else
                        self.cur_func.unique_name(left.name)
                    )
                    stmt.scope.update_ir_name(left.name, ident.name)
                    if isinstance(left_ir_typ, ir.Array):
                        size, _ = self.comp.type_size(left.typ)
                        self.cur_func.alloca(ident)
                        self.cur_func.add_call(
                            "_R4core3mem4copyF", [
                                ident,
                                ir.Selector(
                                    left_ir_typ, right, ir.Name(f"f{i}")
                                ),
                                ir.IntLit(ir.UINT_T, str(size))
                            ]
                        )
                    else:
                        self.cur_func.alloca(
                            ident,
                            ir.Selector(left_ir_typ, right, ir.Name(f"f{i}"))
                        )
        elif isinstance(stmt, ast.DeferStmt):
            self.cur_func.store(
                ir.Ident(ir.BOOL_T, stmt.flag_var), ir.IntLit(ir.BOOL_T, "1")
            )
            self.cur_func_defer_stmts.append(stmt)
        elif isinstance(stmt, ast.ExprStmt):
            _ = self.gen_expr(stmt.expr)

    def gen_expr_with_cast(self, expected_typ_, expr, custom_tmp = None):
        expected_typ = self.ir_type(expected_typ_)
        res_expr = self.gen_expr(expr, custom_tmp)
        assert res_expr != None

        if expected_typ == res_expr.typ:
            return res_expr

        if isinstance(res_expr, ir.IntLit) and self.comp.is_int(expected_typ_):
            res_expr.typ = expected_typ
        elif isinstance(res_expr,
                        ir.FloatLit) and self.comp.is_float(expected_typ_):
            res_expr.typ = expected_typ
        elif self.comp.is_number(
            expr.typ
        ) and self.comp.is_number(expected_typ_) and expr.typ != expected_typ_:
            res_expr = ir.Inst(ir.InstKind.Cast, [res_expr, expected_typ])

        if isinstance(res_expr.typ, ir.Ptr) and res_expr.typ != ir.RAWPTR_T:
            if isinstance(expected_typ, ir.Ptr):
                nr_level_expected = expected_typ.nr_level()
                nr_level = res_expr.typ.nr_level()
                if nr_level > nr_level_expected and expected_typ != ir.RAWPTR_T:
                    while nr_level > nr_level_expected:
                        res_expr = ir.Inst(
                            ir.InstKind.LoadPtr, [res_expr], res_expr.typ.typ
                        )
                        nr_level -= 1
                elif nr_level < nr_level_expected:
                    while nr_level < nr_level_expected:
                        res_expr = ir.Inst(
                            ir.InstKind.GetPtr, [res_expr], res_expr.typ.ptr()
                        )
                        nr_level += 1
            else:
                res_expr = ir.Inst(
                    ir.InstKind.LoadPtr, [res_expr], res_expr.typ.typ
                )
        elif isinstance(expected_typ, ir.Ptr
                        ) and res_expr.typ not in (ir.VOID_T, ir.RAWPTR_T):
            nr_level_expected = expected_typ.nr_level()
            nr_level = res_expr.typ.nr_level(
            ) if isinstance(res_expr.typ, ir.Ptr) else 0
            while nr_level < nr_level_expected:
                res_expr = ir.Inst(
                    ir.InstKind.GetPtr, [res_expr], res_expr.typ.ptr()
                )
                nr_level += 1

        expr_sym = expr.typ.symbol()
        expected_sym = expected_typ_.symbol()

        expr_typ = expr.expected_typ if hasattr(
            expr, "expected_typ"
        ) else expr.typ

        if expected_sym.kind == TypeKind.Trait and expr_typ != expected_typ_ and expr_sym != expected_sym and expr.typ != self.comp.none_t:
            res_expr = self.trait_value(res_expr, expr_typ, expected_typ_)
        elif expr_sym.kind == TypeKind.Enum and expr_sym.info.is_tagged and expr_sym.info.has_variant(
            expected_sym.name
        ):
            tmp = self.cur_func.local_name()
            tmp_t = expected_typ
            variant_idx = expr_sym.info.get_variant_by_type(expected_typ_).value
            self.cur_func.add_call(
                "_R4core16tagged_enum_castF", [
                    ir.Selector(ir.UINT_T, res_expr, ir.Name("_idx_")),
                    variant_idx
                ]
            )
            obj_f = ir.Selector(
                ir.Type(cg_utils.mangle_symbol(expr_sym) + "6_Union"), res_expr,
                ir.Name("obj")
            )
            value = ir.Selector(
                self.ir_type(expr.typ), obj_f, ir.Name(f"v{variant_idx}")
            )
            self.cur_func.inline_alloca(tmp_t, tmp, value)
            res_expr = ir.Ident(tmp_t, tmp)

        if isinstance(expected_typ_, type.Variadic):
            expr_sym = expr.typ.symbol()
            if expr_sym.kind == TypeKind.DynArray:
                res_expr = ir.Inst(
                    ir.InstKind.Call, [
                        ir.Name("_R4core8DynArray5sliceM"),
                        ir.Inst(ir.InstKind.GetPtr, [res_expr]),
                        ir.IntLit(ir.UINT_T, "0"),
                        ir.Selector(ir.UINT_T, res_expr, ir.Name("len"))
                    ]
                )
            elif expr_sym.kind == TypeKind.Array:
                elem_size, _ = self.comp.type_size(expr_sym.info.elem_typ)
                res_expr = ir.Inst(
                    ir.InstKind.Call, [
                        ir.Name("_R4core11array_sliceF"), res_expr,
                        ir.IntLit(ir.UINT_T, str(elem_size)),
                        ir.IntLit(ir.UINT_T, str(expr_sym.info.size)),
                        ir.IntLit(ir.UINT_T, "0"),
                        ir.IntLit(ir.UINT_T, str(expr_sym.info.size))
                    ]
                )
            elif expr_sym.kind == TypeKind.Slice:
                pass # valid

        # wrap option value
        if isinstance(expected_typ_,
                      type.Option) and (not expected_typ_.is_pointer()):
            if isinstance(res_expr, ir.NoneLit):
                res_expr = self.option_none(expected_typ_)
            elif not (
                isinstance(res_expr, ir.Skip)
                or isinstance(expr_typ, type.Option)
            ):
                res_expr = self.option_value(expected_typ_, res_expr)

        return res_expr

    def gen_expr(self, expr, custom_tmp = None):
        if isinstance(expr, ast.ComptimeIf):
            return self.gen_expr(self.comp.evalue_comptime_if(expr)[0])
        elif isinstance(expr, ast.ParExpr):
            return self.gen_expr(expr.expr)
        elif isinstance(expr, ast.NoneLiteral):
            return ir.NoneLit(ir.RAWPTR_T)
        elif isinstance(expr, ast.BoolLiteral):
            return ir.IntLit(ir.BOOL_T, str(int(expr.lit)))
        elif isinstance(expr, ast.CharLiteral):
            if expr.is_byte:
                return ir.IntLit(
                    ir.UINT8_T,
                    str(utils.bytestr(cg_utils.decode_escape(expr.lit)).buf[0])
                )
            return ir.RuneLit(ir.RUNE_T, expr.lit)
        elif isinstance(expr, ast.IntegerLiteral):
            assert expr.typ, expr.pos
            if expr.lit.startswith("0o") or expr.lit.startswith("0b"):
                # use hex variants
                return ir.IntLit(
                    self.ir_type(expr.typ), str(hex(int(expr.lit, 0)))
                )
            return ir.IntLit(self.ir_type(expr.typ), expr.lit)
        elif isinstance(expr, ast.FloatLiteral):
            return ir.FloatLit(ir.Float64_T, expr.lit)
        elif isinstance(expr, ast.StringLiteral):
            escaped_val = utils.smart_quote(expr.lit, expr.is_raw)
            if expr.is_bytestr:
                return ir.ArrayLit(
                    self.ir_type(expr.typ), [
                        ir.IntLit(ir.UINT8_T, str(b))
                        for b in list(utils.bytestr(escaped_val).buf)
                    ]
                )
            size = utils.bytestr(expr.lit).len
            if not expr.is_raw:
                size -= expr.lit.count("\\") - expr.lit.count("\\\\")
            if expr.typ == self.comp.string_t:
                return self.gen_string_literal(escaped_val, size)
            return ir.StringLit(escaped_val, str(size))
        elif isinstance(expr, ast.EnumLiteral):
            enum_sym = expr.typ.symbol()
            if expr.is_instance:
                return self.tagged_enum_value(enum_sym, expr.value, None)
            return ir.IntLit(
                self.ir_type(enum_sym.info.underlying_typ),
                str(expr.variant_info.value)
            )
        elif isinstance(expr, ast.SelfExpr):
            self_typ = self.ir_type(expr.typ)
            return ir.Ident(self_typ, "self")
        elif isinstance(expr, ast.Ident):
            if isinstance(expr.sym, sym.Const):
                return self.gen_const(expr.sym)
            elif isinstance(expr.sym, sym.Var):
                ir_typ = self.ir_type(expr.typ)
                if expr.sym.is_extern:
                    return ir.Ident(
                        ir_typ,
                        cg_utils.mangle_symbol(expr.sym)
                        if expr.sym.abi == sym.ABI.Rivet else expr.sym.name
                    )
                return ir.Ident(ir_typ, cg_utils.mangle_symbol(expr.sym))
            elif isinstance(expr.sym, sym.Func):
                return ir.Ident(
                    self.ir_type(expr.typ), cg_utils.mangle_symbol(expr.sym)
                )
            elif expr.is_comptime:
                if expr.name == "_RIVET_COMMIT_":
                    return self.gen_string_literal(utils.commit_hash())
                elif expr.name == "_RIVET_VERSION_":
                    return self.gen_string_literal(utils.full_version())
            # runtime object
            return ir.Ident(self.ir_type(expr.typ), expr.obj.ir_name)
        elif isinstance(expr, ast.BuiltinCallExpr):
            if expr.name == "as":
                arg1 = expr.args[1]
                arg1_is_rawptr = isinstance(
                    arg1.typ, type.Ptr
                ) and arg1.typ.typ == self.comp.void_t
                if (
                    isinstance(expr.typ, type.Ptr) and expr.typ.value_is_boxed()
                    and (arg1.typ == expr.typ.typ or arg1_is_rawptr)
                ):
                    if not arg1_is_rawptr:
                        return self.gen_expr(arg1)
                    ir_typ = self.ir_type(expr.typ.typ)
                    return ir.Inst(
                        ir.InstKind.Cast, [self.gen_expr(arg1), ir_typ], ir_typ
                    )
                else:
                    ir_typ = self.ir_type(expr.typ)
                res = self.gen_expr(arg1)
                if isinstance(res, ir.IntLit):
                    if self.comp.is_int(ir_typ) or expr.typ == self.comp.bool_t:
                        res.typ = ir_typ
                        return res
                typ_sym = arg1.typ.symbol()
                expr_typ_sym = expr.typ.symbol()
                if typ_sym.kind == TypeKind.Trait:
                    tmp = self.cur_func.local_name()
                    self.cur_func.inline_alloca(
                        ir_typ, tmp,
                        ir.Inst(
                            ir.InstKind.Cast, [
                                ir.Inst(
                                    ir.InstKind.Call, [
                                        ir.Name("_R4core10trait_castF"),
                                        ir.Selector(
                                            ir.RAWPTR_T, res, ir.Name("obj")
                                        ),
                                        ir.Selector(
                                            ir.UINT_T, res, ir.Name("_idx_")
                                        ),
                                        ir.IntLit(
                                            ir.UINT_T, str(expr_typ_sym.id)
                                        )
                                    ]
                                ), ir_typ
                            ]
                        )
                    )
                    return ir.Ident(ir_typ, tmp)
                elif typ_sym.kind == TypeKind.Enum and typ_sym.info.is_tagged:
                    tmp = self.cur_func.local_name()
                    tmp_t = ir_typ
                    variant_idx = typ_sym.info.get_variant_by_type(
                        expr.typ
                    ).value
                    self.cur_func.add_call(
                        "_R4core16tagged_enum_castF", [
                            ir.Selector(ir.UINT_T, res, ir.Name("_idx_")),
                            variant_idx
                        ]
                    )
                    obj_f = ir.Selector(
                        ir.Type(cg_utils.mangle_symbol(typ_sym) + "6_Union"),
                        res, ir.Name("obj")
                    )
                    value = ir.Selector(
                        self.ir_type(expr.typ), obj_f,
                        ir.Name(f"v{variant_idx}")
                    )
                    if isinstance(tmp_t, ir.Ptr):
                        value = ir.Inst(ir.InstKind.GetPtr, [value], tmp_t)
                    self.cur_func.inline_alloca(tmp_t, tmp, value)
                    return ir.Ident(tmp_t, tmp)
                tmp = self.cur_func.local_name()
                self.cur_func.inline_alloca(
                    ir_typ, tmp,
                    ir.Inst(ir.InstKind.Cast, [res, ir_typ], ir_typ)
                )
                return ir.Ident(ir_typ, tmp)
            elif expr.name in ("size_of", "align_of"):
                size, align = self.comp.type_size(expr.args[0].typ)
                if expr.name == "size_of":
                    return ir.IntLit(ir.UINT_T, str(size))
                return ir.IntLit(ir.UINT_T, str(align))
            elif expr.name == "assert":
                msg_ = f"`{expr.args[0]}`"
                msg = utils.smart_quote(msg_, True)
                if self.inside_test:
                    tmp_idx_ = ir.Ident(ir.TEST_T.ptr(), "test")
                    pos = utils.smart_quote(str(expr.pos), False)
                    self.cur_func.add_call(
                        "_R4core11assert_testF", [
                            self.gen_expr(expr.args[0]),
                            self.gen_string_literal(
                                msg,
                                utils.bytestr(msg_).len
                            ),
                            self.gen_string_literal(
                                pos,
                                utils.bytestr(str(expr.pos)).len
                            ), tmp_idx_
                        ]
                    )
                    l1 = self.cur_func.local_name()
                    l2 = self.cur_func.local_name()
                    self.cur_func.add_cond_br(
                        ir.Selector(
                            ir.BOOL_T, tmp_idx_, ir.Name("early_return")
                        ), l1, l2
                    )
                    self.cur_func.add_label(l1)
                    self.cur_func.add_ret_void()
                    self.cur_func.add_label(l2)
                elif self.comp.prefs.build_mode != prefs.BuildMode.Release:
                    self.cur_func.add_call(
                        "_R4core6assertF", [
                            self.gen_expr(expr.args[0]),
                            self.gen_string_literal(
                                msg,
                                utils.bytestr(msg_).len
                            )
                        ]
                    )
            elif expr.name in ("ptr_add", "ptr_sub", "ptr_diff"):
                return ir.Inst(
                    ir.InstKind.Add
                    if expr.name == "ptr_add" else ir.InstKind.Sub,
                    [self.gen_expr(expr.args[0]),
                     self.gen_expr(expr.args[1])]
                )
            elif expr.name == "unreachable":
                self.runtime_error("entered unreachable code")
            elif expr.name == "breakpoint" and self.comp.prefs.build_mode != prefs.BuildMode.Release:
                self.cur_func.breakpoint()
        elif isinstance(expr, ast.TupleLiteral):
            expr_sym = expr.typ.symbol()
            tmp = self.stacked_instance(self.ir_type(expr.typ))
            for i, elem in enumerate(expr.exprs):
                elem_typ = expr_sym.info.types[i]
                field_expr = self.gen_expr_with_cast(elem_typ, elem)
                self.cur_func.store(
                    ir.Selector(elem_typ, tmp, ir.Name(f"f{i}")), field_expr
                )
            return tmp
        elif isinstance(expr, ast.AssignExpr):
            if isinstance(expr.left, ast.TupleLiteral):
                if isinstance(expr.right, ast.TupleLiteral):
                    for i, l in enumerate(expr.left.exprs):
                        self.gen_expr(
                            ast.AssignExpr(
                                l, expr.op, expr.right.exprs[i], expr.pos
                            )
                        )
                else:
                    right = self.gen_expr(expr.right)
                    for i, l in enumerate(expr.left.exprs):
                        left, require_store_ptr = self.gen_left_assign(
                            l, expr.right, expr.op
                        )
                        if left == None:
                            continue
                        inst = ir.InstKind.StorePtr if require_store_ptr else ir.InstKind.Store
                        self.cur_func.add_inst(
                            ir.Inst(
                                inst, [
                                    left,
                                    ir.Selector(l.typ, right, ir.Name(f"f{i}"))
                                ]
                            )
                        )
                return ir.Skip()
            left, require_store_ptr = self.gen_left_assign(
                expr.left, expr.right, expr.op
            )
            if left == None:
                return ir.Skip()
            expr_left_typ_ir = self.ir_type(expr.left.typ)
            expr_left_sym = expr.left.typ.symbol()
            if expr.op == Kind.Assign:
                if isinstance(expr_left_typ_ir, ir.Array):
                    self.gen_expr_with_cast(expr.left.typ, stmt.right, ident)
                else:
                    value = self.gen_expr_with_cast(expr.left.typ, expr.right)
                    if require_store_ptr:
                        self.cur_func.store_ptr(left, value)
                    else:
                        self.cur_func.store(left, value)
            else:
                single_op = expr.op.single()
                right = self.gen_expr_with_cast(expr.left.typ, expr.right)
                if expr_left_sym.kind == TypeKind.Struct and expr_left_sym.exists(
                    str(single_op)
                ):
                    ov_m = OVERLOADABLE_OPERATORS_STR[str(single_op)]
                    left_operand = left
                    right_operand = right
                    if not isinstance(expr_left_typ_ir, ir.Ptr):
                        left_operand = ir.Inst(
                            ir.InstKind.GetPtr, [left_operand]
                        )
                        right_operand = ir.Inst(
                            ir.InstKind.GetPtr, [right_operand]
                        )
                    self.cur_func.store(
                        left,
                        ir.Inst(
                            ir.InstKind.Call, [
                                ir.Name(
                                    f"{cg_utils.mangle_symbol(expr_left_sym)}{len(ov_m)}{ov_m}M"
                                ), left_operand, right_operand
                            ]
                        )
                    )
                elif op_kind := ir.get_ir_op(single_op):
                    value = ir.Inst(op_kind, [left, right])
                    if require_store_ptr:
                        self.cur_func.store_ptr(left, value)
                    else:
                        self.cur_func.store(left, value)
                else:
                    assert False, expr
        elif isinstance(expr, ast.Block):
            self.gen_defer_stmt_vars(expr.defer_stmts)
            self.gen_stmts(expr.stmts)
            self.gen_defer_stmts(scope = expr.scope)
            if expr.is_expr:
                return self.gen_expr_with_cast(expr.typ, expr.expr)
            return ir.Skip()
        elif isinstance(expr, ast.CallExpr):
            if expr.is_ctor:
                typ_sym = expr.typ.symbol()
                if typ_sym.kind == TypeKind.Trait:
                    value = expr.args[0].expr
                    return self.trait_value(
                        self.gen_expr_with_cast(value.typ, value), value.typ,
                        expr.typ
                    )
                elif typ_sym.kind == TypeKind.Enum:
                    if expr.is_enum_variant:
                        tmp = self.stacked_instance(
                            ir.Type(
                                cg_utils.mangle_symbol(expr.enum_variant_sym)
                            )
                        )
                        initted_fields = []
                        type_fields = expr.enum_variant_sym.full_fields()
                        for i, f in enumerate(expr.args):
                            if f.is_named:
                                for ff in type_fields:
                                    if ff.name == f.name:
                                        field = f
                                        break
                            else:
                                field = type_fields[i]
                            initted_fields.append(field.name)
                            self.cur_func.store(
                                ir.Selector(
                                    self.ir_type(field.typ), tmp,
                                    ir.Name(field.name)
                                ), self.gen_expr_with_cast(field.typ, f.expr)
                            )
                        if expr.has_spread_expr:
                            spread_val = self.gen_expr_with_cast(
                                type.Type(expr.enum_variant_sym),
                                expr.spread_expr
                            )
                        else:
                            spread_val = None
                        for f in expr.enum_variant_sym.full_fields():
                            if f.name in initted_fields:
                                continue
                            if f.typ.symbol().kind == TypeKind.Array:
                                continue
                            f_typ = self.ir_type(f.typ)
                            sltor = ir.Selector(f_typ, tmp, ir.Name(f.name))
                            if f.has_def_expr:
                                value = self.gen_expr_with_cast(
                                    f.typ, f.def_expr
                                )
                            elif expr.has_spread_expr:
                                value = ir.Selector(
                                    f_typ, spread_val, ir.Name(f.name)
                                )
                            else:
                                value = self.default_value(f.typ)
                            self.cur_func.store(
                                ir.Selector(f_typ, tmp, ir.Name(f.name)), value
                            )
                        return self.tagged_enum_variant_with_fields_value(
                            typ_sym, expr.left.value
                            if isinstance(expr.left, ast.EnumLiteral) else
                            expr.left.field_name, tmp, custom_tmp = custom_tmp
                        )
                    if isinstance(expr.left, ast.EnumLiteral):
                        if len(expr.args) > 0:
                            x = expr.args[0].expr
                        else:
                            x = None
                        return self.tagged_enum_value(
                            typ_sym, expr.left.value, x, custom_tmp = custom_tmp
                        )
                    if len(expr.args) > 0:
                        x = expr.args[0].expr
                    else:
                        x = None
                    return self.tagged_enum_value(
                        typ_sym, expr.left.field_name, x,
                        custom_tmp = custom_tmp
                    )
                if custom_tmp:
                    tmp = custom_tmp
                elif typ_sym.is_boxed():
                    size, _ = self.comp.type_size(expr.typ, True)
                    tmp = self.boxed_instance(self.ir_type(expr.typ), size)
                else:
                    tmp = self.stacked_instance(self.ir_type(expr.typ))
                initted_fields = []
                type_fields = typ_sym.full_fields()
                for i, f in enumerate(expr.args):
                    if f.is_named:
                        for ff in type_fields:
                            if ff.name == f.name:
                                field = f
                                break
                    else:
                        field = type_fields[i]
                    initted_fields.append(field.name)
                    self.cur_func.store(
                        ir.Selector(
                            self.ir_type(field.typ), tmp, ir.Name(field.name)
                        ), self.gen_expr_with_cast(field.typ, f.expr)
                    )
                if expr.has_spread_expr:
                    spread_val = self.gen_expr_with_cast(
                        expr.spread_expr.typ, expr.spread_expr
                    )
                else:
                    spread_val = None
                for f in typ_sym.full_fields():
                    if f.name in initted_fields or f.typ.symbol(
                    ).kind == TypeKind.Array:
                        continue
                    f_typ = self.ir_type(f.typ)
                    sltor = ir.Selector(f_typ, tmp, ir.Name(f.name))
                    if f.has_def_expr:
                        value = self.gen_expr_with_cast(f.typ, f.def_expr)
                    elif expr.has_spread_expr:
                        value = ir.Selector(f_typ, spread_val, ir.Name(f.name))
                    else:
                        value = self.default_value(f.typ)
                    self.cur_func.store(
                        ir.Selector(f_typ, tmp, ir.Name(f.name)), value
                    )
                return tmp
            args = []
            is_vtable_call = False
            if not expr.sym:
                raise Exception(f"expr.sym is `None` [ {expr} ] at {expr.pos}")
            if expr.sym.is_method:
                left_sym = expr.sym.self_typ.symbol()
                left2_sym = expr.left.left.typ.symbol()
                if left_sym.kind == TypeKind.Trait and not expr.sym.has_body:
                    self_expr = self.gen_expr_with_cast(
                        expr.left.left.typ, expr.left.left
                    )
                    is_vtable_call = True
                    if isinstance(self_expr.typ, ir.Ptr):
                        self_expr = ir.Inst(
                            ir.InstKind.LoadPtr, [self_expr], self_expr.typ.typ
                        )
                    if left_sym.kind == TypeKind.Trait:
                        if left2_sym.kind == TypeKind.Trait and left_sym != left2_sym:
                            id_value = ir.Inst(
                                ir.InstKind.Call, [
                                    ir.Name(
                                        f"{cg_utils.mangle_symbol(left_sym)}17__index_of_vtbl__"
                                    ),
                                    ir.Selector(
                                        ir.UINT_T, self_expr, ir.Name("_idx_")
                                    )
                                ]
                            )
                        else:
                            id_value = ir.Selector(
                                ir.UINT_T, self_expr, ir.Name("_id_")
                            )
                    else:
                        id_value = ir.Inst(
                            ir.InstKind.Call, [
                                ir.Name(
                                    f"{cg_utils.mangle_symbol(left_sym)}17__index_of_vtbl__"
                                ),
                                ir.Selector(
                                    ir.UINT_T, self_expr, ir.Name("_idx_")
                                )
                            ]
                        )
                    args.append(
                        ir.Selector(
                            ir.RAWPTR_T,
                            ir.Inst(
                                ir.InstKind.LoadPtr, [
                                    ir.Inst(
                                        ir.InstKind.Add, [
                                            ir.Name(
                                                cg_utils
                                                .mangle_symbol(left_sym) +
                                                "4VTBL"
                                            ), id_value
                                        ]
                                    )
                                ]
                            ),
                            ir.Name(
                                OVERLOADABLE_OPERATORS_STR[expr.sym.name]
                                if expr.sym.name in
                                OVERLOADABLE_OPERATORS_STR else expr.sym.name
                            )
                        )
                    )
                    if left_sym.kind == TypeKind.Trait and not expr.sym.has_body:
                        args.append(
                            ir.Selector(ir.RAWPTR_T, self_expr, ir.Name("obj"))
                        )
                    else:
                        args.append(self_expr)
            if not is_vtable_call:
                if expr.is_closure:
                    name = self.gen_expr_with_cast(expr.left.typ, expr.left)
                elif (not expr.sym.is_method
                      ) and expr.sym.attributes.has("export"):
                    export_attribute = expr.sym.attributes.find("export")
                    if isinstance(
                        export_attribute.args[0].expr, ast.StringLiteral
                    ):
                        name = export_attribute.args[0].expr.lit
                    else:
                        assert False
                elif expr.sym.is_extern and expr.sym.abi != sym.ABI.Rivet and not expr.sym.has_body:
                    name = ir.Name(expr.sym.name)
                else:
                    name = ir.Name(cg_utils.mangle_symbol(expr.sym))
                args.append(name)
                if expr.sym.is_method:
                    left_sym = expr.sym.self_typ.symbol()
                    if left_sym.kind == TypeKind.DynArray:
                        expr.sym = self.comp.dyn_array_sym[expr.sym.name]
                    receiver = expr.left.left
                    if left_sym.kind == TypeKind.Trait and expr.sym.self_typ != receiver.typ:
                        self_expr = self.gen_expr_with_cast(
                            expr.sym.self_typ, receiver
                        )
                    else:
                        self_expr = self.gen_expr(receiver)
                    if expr.sym.self_is_ptr and not isinstance(
                        self_expr.typ, ir.Ptr
                    ):
                        self_expr = ir.Inst(ir.InstKind.GetPtr, [self_expr])
                    elif isinstance(
                        receiver.typ, type.Ptr
                    ) and not expr.sym.self_is_ptr:
                        self_expr = ir.Inst(
                            ir.InstKind.LoadPtr, [self_expr], self_expr.typ.typ
                        )
                    args.append(self_expr)
            args_len = expr.sym.args_len()
            for i, arg in enumerate(expr.args):
                if expr.sym.is_variadic and i == args_len:
                    break
                fn_arg = expr.sym.get_arg(i)
                fn_arg_typ = fn_arg.typ
                fn_arg_typ_sym = fn_arg_typ.symbol()
                arg_value = self.gen_expr_with_cast(fn_arg_typ, arg.expr)
                if expr.sym.is_method:
                    left_sym = expr.left.left_typ.symbol()
                    if left_sym.kind == TypeKind.DynArray and expr.sym.name == "push":
                        if arg.typ.value_is_boxed():
                            arg_value = ir.Inst(
                                ir.InstKind.GetPtr, [arg_value],
                                arg_value.typ.ptr()
                            )
                args.append(arg_value)
            if expr.has_spread_expr:
                args.append(
                    self.gen_expr_with_cast(
                        expr.sym.args[-1].typ, expr.spread_expr
                    )
                )
            elif expr.sym.is_variadic:
                variadic_count = len(expr.args) - args_len
                if expr.sym.is_extern:
                    for i in range(args_len, len(expr.args)):
                        arg = expr.args[i]
                        args.append(self.gen_expr_with_cast(arg.typ, arg.expr))
                else:
                    var_arg = expr.sym.args[-1]
                    if variadic_count == 1 and len(
                        expr.args
                    ) > 0 and isinstance(
                        expr.args[-1].expr.typ, type.Variadic
                    ):
                        arg = expr.args[-1]
                        args.append(self.gen_expr_with_cast(arg.typ, arg.expr))
                    elif variadic_count > 0:
                        vargs = []
                        for i in range(args_len, len(expr.args)):
                            vargs.append(
                                self.gen_expr_with_cast(
                                    var_arg.typ.typ, expr.args[i].expr
                                )
                            )
                        args.append(self.variadic_args(vargs, var_arg.typ.typ))
                    else:
                        args.append(self.empty_slice())
            if expr.sym.ret_typ == self.comp.never_t:
                self.gen_defer_stmts(
                    scope = expr.scope, run_defer_previous = True
                )
            inst = ir.Inst(ir.InstKind.Call, args)
            if expr.sym.ret_typ in self.void_types:
                self.cur_func.add_inst(inst)
            else:
                is_void_value = expr.typ in self.void_types
                tmp = "" if custom_tmp else self.cur_func.local_name()
                if isinstance(expr.sym.ret_typ, type.Array):
                    size, _ = self.comp.type_size(expr.sym.ret_typ)
                    if custom_tmp:
                        id = custom_tmp
                    else:
                        id = ir.Ident(self.ir_type(expr.sym.ret_typ), tmp)
                        self.cur_func.alloca(id)
                    self.cur_func.add_call(
                        "_R4core3mem4copyF", [
                            id,
                            ir.Selector(
                                self.ir_type(expr.sym.ret_typ), inst,
                                ir.Name("arr")
                            ),
                            ir.IntLit(ir.UINT_T, str(size))
                        ]
                    )
                elif expr.sym.is_method and expr.sym.name == "pop" and left_sym.kind == TypeKind.DynArray:
                    ret_typ = self.ir_type(expr.typ)
                    value = ir.Inst(ir.InstKind.Cast, [inst, ret_typ.ptr()])
                    if custom_tmp:
                        self.cur_func.store(
                            custom_tmp,
                            ir.Inst(ir.InstKind.LoadPtr, [value], ret_typ.typ)
                        )
                    else:
                        self.cur_func.inline_alloca(
                            ret_typ, tmp,
                            ir.Inst(ir.InstKind.LoadPtr, [value], ret_typ)
                        )
                else:
                    if custom_tmp:
                        self.cur_func.store(custom_tmp, inst)
                    else:
                        self.cur_func.inline_alloca(
                            self.ir_type(expr.sym.ret_typ), tmp, inst
                        )
                if expr.has_err_handler():
                    err_handler_is_void = (
                        not expr.err_handler.is_propagate
                    ) and expr.err_handler.expr.typ in self.void_types
                    res_value = ir.Ident(self.ir_type(expr.sym.ret_typ), tmp)
                    panic_l = self.cur_func.local_name()
                    else_value = "" if err_handler_is_void else self.cur_func.local_name(
                    )
                    exit_l = "" if expr.err_handler.is_propagate else self.cur_func.local_name(
                    )
                    res_value_is_err = ir.Selector(
                        ir.BOOL_T, res_value, ir.Name("is_err")
                    )
                    self.cur_func.add_cond_br(
                        res_value_is_err, panic_l,
                        exit_l if err_handler_is_void else else_value
                    )
                    self.cur_func.add_label(panic_l)
                    if expr.err_handler.is_propagate:
                        self.gen_return_trace_add(expr.pos)
                        self.gen_defer_stmts(
                            True, res_value_is_err, scope = expr.scope,
                            run_defer_previous = True
                        )
                        if self.cur_func_is_main or self.inside_var_decl:
                            self.cur_func.add_call(
                                "_R4core15uncatched_errorF", [
                                    ir.Selector(
                                        ir.THROWABLE_T, res_value,
                                        ir.Name("err")
                                    )
                                ]
                            )
                        elif self.inside_test:
                            pos = utils.smart_quote(str(expr.pos), False)
                            self.cur_func.add_call(
                                "_R4core18test_error_throwedF", [
                                    ir.Selector(
                                        ir.THROWABLE_T, res_value,
                                        ir.Name("err")
                                    ),
                                    self.gen_string_literal(pos),
                                    ir.Ident(ir.TEST_T, "test")
                                ]
                            )
                            self.cur_func.add_ret_void()
                        else:
                            tmp2 = self.stacked_instance(
                                self.ir_type(self.cur_func_ret_typ)
                            )
                            self.cur_func.store(
                                ir.Selector(ir.BOOL_T, tmp2, ir.Name("is_err")),
                                ir.IntLit(ir.BOOL_T, "1")
                            )
                            self.cur_func.store(
                                ir.Selector(
                                    ir.THROWABLE_T, tmp2, ir.Name("err")
                                ),
                                ir.Selector(
                                    ir.THROWABLE_T, res_value, ir.Name("err")
                                )
                            )
                            self.cur_func.add_ret(tmp2)
                        self.cur_func.add_label(else_value)
                        if is_void_value:
                            return ir.Skip()
                        return ir.Selector(
                            self.ir_type(expr.sym.ret_typ.typ), res_value,
                            ir.Name("value")
                        )
                    else: # `catch`
                        self.gen_return_trace_clear()
                        if expr.err_handler.has_varname():
                            err_ir_name = self.cur_func.unique_name(
                                expr.err_handler.varname
                            )
                            expr.err_handler.scope.update_ir_name(
                                expr.err_handler.varname, err_ir_name
                            )
                            self.cur_func.inline_alloca(
                                ir.THROWABLE_T, err_ir_name,
                                ir.Selector(
                                    ir.THROWABLE_T, res_value, ir.Name("err")
                                )
                            )
                        if err_handler_is_void:
                            _ = self.gen_expr_with_cast(
                                expr.sym.ret_typ.typ, expr.err_handler.expr
                            )
                            self.cur_func.add_label(exit_l)
                            return ir.Selector(
                                self.ir_type(expr.typ), res_value,
                                ir.Name("value")
                            )
                        tmp2 = self.stacked_instance(
                            self.ir_type(expr.sym.ret_typ.typ),
                            self.gen_expr_with_cast(
                                expr.sym.ret_typ.typ, expr.err_handler.expr
                            )
                        )
                        self.cur_func.add_br(exit_l)
                        self.cur_func.add_label(else_value)
                        self.cur_func.store(
                            tmp2,
                            ir.Selector(
                                self.ir_type(expr.typ), res_value,
                                ir.Name("value")
                            )
                        )
                        self.cur_func.add_label(exit_l)
                        return tmp2
                return ir.Ident(self.ir_type(expr.sym.ret_typ), tmp)
        elif isinstance(expr, ast.SelectorExpr):
            if expr.is_path:
                if isinstance(expr.field_sym, sym.Const):
                    return self.gen_const(expr.field_sym)
                elif isinstance(
                    expr.left_sym, sym.Type
                ) and expr.left_sym.kind == TypeKind.Enum:
                    if expr.left_sym.info.is_tagged:
                        return self.tagged_enum_value(
                            expr.left_sym, expr.field_name, None,
                            custom_tmp = custom_tmp
                        )
                    if v := expr.left_sym.info.get_variant(expr.field_name):
                        return ir.IntLit(
                            self.ir_type(expr.left_sym.info.underlying_typ),
                            str(v.value)
                        )
                elif isinstance(expr.left_sym, sym.Func):
                    return ir.Ident(
                        self.ir_type(expr.typ),
                        cg_utils.mangle_symbol(expr.left_sym)
                    )
                elif isinstance(
                    expr.field_sym, sym.Var
                ) and expr.field_sym.is_extern and expr.field_sym.abi != sym.ABI.Rivet:
                    return ir.Ident(self.ir_type(expr.typ), expr.field_sym.name)
                return ir.Ident(
                    self.ir_type(expr.typ),
                    cg_utils.mangle_symbol(expr.field_sym)
                )
            old_inside_selector_expr = self.inside_selector_expr
            self.inside_selector_expr = True
            left_sym = expr.left_typ.symbol()
            self.inside_selector_expr = old_inside_selector_expr
            ir_left_typ = self.ir_type(expr.left_typ)
            ir_typ = self.ir_type(expr.typ)
            if (
                expr.is_indirect or expr.is_boxed_indirect
            ) or expr.is_option_check:
                left = self.gen_expr(expr.left)
                if expr.is_indirect or expr.is_boxed_indirect:
                    return ir.Inst(ir.InstKind.LoadPtr, [left], ir_left_typ.typ)
                panic_l = self.cur_func.local_name()
                exit_l = self.cur_func.local_name()
                if expr.left_typ.is_pointer():
                    self.cur_func.add_cond_br(
                        ir.Inst(
                            ir.InstKind.Cmp,
                            [ir.Name("=="), left,
                             ir.NoneLit(ir.RAWPTR_T)]
                        ), panic_l, exit_l
                    )
                    value = left
                else:
                    self.cur_func.add_cond_br(
                        ir.Selector(ir.BOOL_T, left, ir.Name("is_none")),
                        panic_l, exit_l
                    )
                    value = ir.Selector(ir_typ, left, ir.Name("value"))
                self.cur_func.add_label(panic_l)
                self.runtime_error(f"attempt to use none value (`{expr.left}`)")
                self.cur_func.add_label(exit_l)
                return value
            left = self.gen_expr(expr.left)
            if isinstance(left, ir.StringLit):
                if expr.field_name == "ptr":
                    return ir.StringLit(left.lit, left.len)
                elif expr.field_name == "len":
                    return ir.IntLit(ir.UINT_T, str(left.len))
            elif left_sym.kind == TypeKind.Array and expr.field_name == "len":
                return ir.IntLit(ir.UINT_T, str(left_sym.info.size))
            if left_sym.kind == TypeKind.Trait:
                ir_typ = ir_typ.ptr(True)
            return ir.Selector(
                ir_typ, left,
                ir.Name(
                    f"f{expr.field_name}" if left_sym.kind ==
                    TypeKind.Tuple else expr.field_name
                )
            )
        elif isinstance(expr, ast.ArrayCtor):
            if expr.is_dyn:
                if not expr.init_value and not expr.cap_value and not expr.len_value:
                    # []T()
                    return self.empty_dyn_array(expr.typ.symbol())
                if expr.init_value:
                    method_name = "_R4core8DynArray13new_with_initF"
                else:
                    method_name = "_R4core8DynArray12new_with_lenF"
                size, _ = self.comp.type_size(expr.elem_type)
                args = []
                if expr.init_value:
                    init_value = self.gen_expr_with_cast(
                        expr.elem_type, expr.init_value
                    )
                    args.append(ir.Inst(ir.InstKind.GetPtr, [init_value]))
                # element size
                args.append(ir.IntLit(ir.UINT_T, str(size)))
                # length
                if expr.len_value:
                    args.append(self.gen_expr(expr.len_value))
                else:
                    args.append(ir.IntLit(ir.UINT_T, "0"))
                # capacity
                if expr.cap_value:
                    args.append(self.gen_expr(expr.cap_value))
                else:
                    args.append(ir.IntLit(ir.UINT_T, "0"))
                return ir.Inst(ir.InstKind.Call, [ir.Name(method_name), *args])
            else:
                if custom_tmp:
                    final_value = custom_tmp
                else:
                    tmp_name = self.cur_func.local_name()
                    tmp_t = self.ir_type(expr.typ)
                    tmp = ir.Ident(tmp_t, tmp_name)
                    self.cur_func.inline_alloca(tmp_t, tmp_name)
                    final_value = tmp
                if expr.init_value:
                    size, _ = self.comp.type_size(expr.elem_type)
                    init_value = self.gen_expr_with_cast(
                        expr.elem_type, expr.init_value
                    )
                    self.cur_func.add_call(
                        "_R4core14array_init_setF", [
                            final_value,
                            ir.IntLit(ir.UINT_T, str(size)),
                            ir.IntLit(
                                ir.UINT_T, str(expr.typ.symbol().info.size)
                            ),
                            ir.Inst(ir.InstKind.GetPtr, [init_value])
                        ]
                    )
                if custom_tmp:
                    return ir.Skip()
                return tmp
        elif isinstance(expr, ast.ArrayLiteral):
            typ_sym = expr.typ.symbol()
            if len(expr.elems) == 0:
                if expr.is_dyn:
                    return self.stacked_instance(
                        self.ir_type(expr.typ), self.empty_dyn_array(typ_sym)
                    )
                return self.default_value(expr.typ)
            elem_typ = typ_sym.info.elem_typ
            size, _ = self.comp.type_size(elem_typ)
            elems = []
            for i, elem in enumerate(expr.elems):
                elems.append(self.gen_expr_with_cast(elem_typ, elem))
            arr_lit = ir.ArrayLit(self.ir_type(elem_typ), elems)
            if expr.is_dyn:
                return self.stacked_instance(
                    self.ir_type(expr.typ),
                    ir.Inst(
                        ir.InstKind.Call, [
                            ir.Name("_R4core8DynArray10from_arrayF"), arr_lit,
                            ir.IntLit(ir.UINT_T, str(size)),
                            ir.IntLit(ir.UINT_T, str(len(elems)))
                        ]
                    )
                )
            if custom_tmp:
                size, _ = self.comp.type_size(expr.typ)
                self.cur_func.add_call(
                    "_R4core3mem4copyF",
                    [custom_tmp, arr_lit,
                     ir.IntLit(ir.UINT_T, str(size))]
                )
                return ir.Skip()
            return arr_lit
        elif isinstance(expr, ast.IndexExpr):
            s = expr.left.typ.symbol()
            left = self.gen_expr_with_cast(expr.left.typ, expr.left)
            if isinstance(expr.index, ast.RangeExpr):
                if expr.index.has_start:
                    start = self.gen_expr(expr.index.start)
                else:
                    start = ir.IntLit(ir.UINT_T, "0")
                if expr.index.has_end:
                    end = self.gen_expr(expr.index.end)
                else:
                    if s.kind == TypeKind.Array:
                        end = ir.IntLit(ir.UINT_T, s.info.size.lit)
                    elif isinstance(left, ir.StringLit):
                        end = ir.IntLit(ir.UINT_T, left.len)
                    else:
                        end = None
                tmp = self.cur_func.local_name()
                if s.kind in (TypeKind.DynArray, TypeKind.Slice):
                    if end == None:
                        method_name = "_R4core5Slice10slice_fromM" if s.kind == TypeKind.Slice else "_R4core8DynArray10slice_fromM"
                        inst = ir.Inst(
                            ir.InstKind.Call, [
                                ir.Name(method_name),
                                ir.Inst(ir.InstKind.GetPtr, [left]), start
                            ]
                        )
                    else:
                        method_name = "_R4core5Slice5sliceM" if s.kind == TypeKind.Slice else "_R4core8DynArray5sliceM"
                        inst = ir.Inst(
                            ir.InstKind.Call, [
                                ir.Name(method_name),
                                ir.Inst(ir.InstKind.GetPtr, [left]), start, end
                            ]
                        )
                else:
                    size, _ = self.comp.type_size(s.info.elem_typ)
                    if end == None:
                        inst = ir.Inst(
                            ir.InstKind.Call, [
                                ir.Name("_R4core16array_slice_fromF"), left,
                                ir.IntLit(ir.UINT_T, str(size)),
                                ir.IntLit(ir.UINT_T, s.info.size.lit), start
                            ]
                        )
                    else:
                        inst = ir.Inst(
                            ir.InstKind.Call, [
                                ir.Name("_R4core11array_sliceF"), left,
                                ir.IntLit(ir.UINT_T, str(size)),
                                ir.IntLit(ir.UINT_T, s.info.size.lit), start,
                                end
                            ]
                        )
                self.cur_func.inline_alloca(self.ir_type(expr.typ), tmp, inst)
                return ir.Ident(self.ir_type(expr.typ), tmp)
            idx = self.gen_expr(expr.index)
            if isinstance(s.info, sym.ArrayInfo):
                self.cur_func.add_call(
                    "_R4core11array_indexF",
                    [ir.IntLit(ir.UINT_T, s.info.size.lit), idx]
                )
            tmp = self.cur_func.local_name()
            expr_typ_ir = self.ir_type(expr.typ)
            if isinstance(expr.left_typ, type.Ptr) or s.kind == TypeKind.Array:
                if expr.is_ref:
                    expr_typ_ir = expr_typ_ir.ptr()
                value = ir.Inst(
                    ir.InstKind.GetElementPtr, [left, idx], expr_typ_ir
                )
                if not expr.is_ref:
                    value = ir.Inst(ir.InstKind.LoadPtr, [value], expr_typ_ir)
            elif s.kind == TypeKind.String:
                value = ir.Inst(
                    ir.InstKind.Call, [
                        ir.Name("_R4core6string2atM"),
                        ir.Inst(ir.InstKind.GetPtr, [left]), idx
                    ], expr_typ_ir
                )
            elif s.kind in (TypeKind.DynArray, TypeKind.Slice):
                method_name = "_R4core5Slice3getM" if s.kind == TypeKind.Slice else "_R4core8DynArray3getM"
                expr_typ_ir2 = expr_typ_ir.ptr()
                if not isinstance(left.typ, type.Ptr):
                    left = ir.Inst(ir.InstKind.GetPtr, [left], left.typ.ptr())
                if expr.is_ref:
                    expr_typ_ir = expr_typ_ir.ptr()
                value = ir.Inst(
                    ir.InstKind.Cast, [
                        ir.Inst(
                            ir.InstKind.Call, [ir.Name(method_name), left, idx]
                        ), expr_typ_ir2
                    ], expr_typ_ir2
                )
                load_ptr = True
                if self.inside_lhs_assign and self.inside_selector_expr:
                    if not s.info.elem_typ.value_is_boxed():
                        load_ptr = False
                        expr_typ_ir = expr_typ_ir2
                if load_ptr and not expr.is_ref:
                    value = ir.Inst(ir.InstKind.LoadPtr, [value], expr_typ_ir)
            else:
                assert False, (expr, expr.pos)
            self.cur_func.inline_alloca(expr_typ_ir, tmp, value)
            return ir.Ident(expr_typ_ir, tmp)
        elif isinstance(expr, ast.UnaryExpr):
            if expr.op == Kind.Xor:
                right = self.gen_expr(expr.right)
                if isinstance(right.typ, ir.Ptr) and right.typ.is_managed:
                    return right
                size, _ = self.comp.type_size(expr.right_typ, True)
                res = self.boxed_instance(self.ir_type(expr.right_typ), size)
                self.cur_func.store_ptr(res, right)
                return res
            right = self.gen_expr(expr.right)
            expr_typ = self.ir_type(expr.typ)
            if expr.op == Kind.Amp:
                if isinstance(right.typ, ir.Ptr
                              ) and right.typ.nr_level() == expr_typ.nr_level():
                    return right
                tmp = self.cur_func.local_name()
                self.cur_func.inline_alloca(
                    expr_typ, tmp,
                    ir.Inst(ir.InstKind.GetPtr, [right], expr_typ)
                )
                return ir.Ident(expr_typ, tmp)
            if expr.op == Kind.Bang:
                kind = ir.InstKind.BooleanNot
            elif expr.op == Kind.BitNot:
                kind = ir.InstKind.BitNot
            else:
                kind = ir.InstKind.Neg
            return ir.Inst(kind, [right], expr_typ)
        elif isinstance(expr, ast.BinaryExpr):
            expr_left_typ = expr.left.typ
            expr_right_typ = expr.right.typ
            if isinstance(expr_left_typ, type.Option):
                if expr.op in (Kind.Eq, Kind.Ne):
                    left = self.gen_expr(expr.left)
                    if expr_left_typ.is_pointer():
                        op = "==" if expr.op == Kind.Eq else "!="
                        return ir.Inst(
                            ir.InstKind.Cmp,
                            [op, left, ir.NoneLit(ir.RAWPTR_T)], ir.BOOL_T
                        )
                    val = ir.Selector(ir.BOOL_T, left, ir.Name("is_none"))
                    if expr.op == Kind.Ne:
                        val = ir.Inst(ir.InstKind.BooleanNot, [val], ir.BOOL_T)
                    return val
                elif expr.op == Kind.OrElse:
                    expr_typ = expr_left_typ
                    is_not_never = expr.right.typ != self.comp.never_t
                    left = self.gen_expr(expr.left)
                    is_none_label = self.cur_func.local_name()
                    is_not_none_label = self.cur_func.local_name()
                    exit_label = self.cur_func.local_name(
                    ) if is_not_never else ""
                    if expr_typ.is_pointer():
                        cond = ir.Inst(
                            ir.InstKind.Cmp,
                            [ir.Name("=="), left,
                             ir.NoneLit(ir.RAWPTR_T)]
                        )
                    else:
                        cond = ir.Selector(ir.BOOL_T, left, ir.Name("is_none"))
                    tmp = self.stacked_instance(self.ir_type(expr_typ.typ))
                    self.cur_func.add_cond_br(
                        cond, is_none_label, is_not_none_label
                    )
                    self.cur_func.add_label(is_none_label)
                    right = self.gen_expr_with_cast(expr_typ.typ, expr.right)
                    if is_not_never:
                        self.cur_func.store(tmp, right)
                        self.cur_func.add_br(exit_label)
                    self.cur_func.add_label(is_not_none_label)
                    if expr_typ.is_pointer():
                        self.cur_func.store(tmp, left)
                    else:
                        self.cur_func.store(
                            tmp,
                            ir.Selector(expr_typ.typ, left, ir.Name("value"))
                        )
                    if is_not_never:
                        self.cur_func.add_label(exit_label)
                    return tmp
            elif expr.op in (Kind.LogicalAnd, Kind.LogicalOr):
                left = self.gen_expr_with_cast(expr_left_typ, expr.left)
                tmp = self.stacked_instance(
                    self.ir_type(self.comp.bool_t), left
                )
                left_l = self.cur_func.local_name()
                exit_l = self.cur_func.local_name()
                if expr.op == Kind.LogicalAnd:
                    self.cur_func.add_cond_br(left, left_l, exit_l)
                else:
                    self.cur_func.add_cond_br(left, exit_l, left_l)
                self.cur_func.add_label(left_l)
                self.cur_func.store(
                    tmp, self.gen_expr_with_cast(expr_left_typ, expr.right)
                )
                self.cur_func.add_label(exit_l)
                return tmp
            elif expr.op in (Kind.KwIs, Kind.KwNotIs):
                left = self.gen_expr_with_cast(expr_left_typ, expr.left)
                tmp = self.cur_func.local_name()
                kind = "==" if expr.op == Kind.KwIs else "!="
                left_sym = expr_left_typ.symbol()
                expr_right_sym = expr_right_typ.symbol()
                if left_sym.kind == TypeKind.Enum:
                    if left_sym.info.is_tagged:
                        cmp = ir.Inst(
                            ir.InstKind.Cmp, [
                                ir.Name(kind),
                                ir.Selector(ir.UINT_T, left, ir.Name("_idx_")),
                                ir.IntLit(
                                    ir.UINT_T,
                                    str(expr.right.variant_info.value)
                                )
                            ]
                        )
                    else:
                        cmp = ir.Inst(
                            ir.InstKind.Cmp, [
                                ir.Name(kind), left,
                                ir.IntLit(
                                    ir.UINT_T,
                                    str(expr.right.variant_info.value)
                                )
                            ]
                        )
                elif left_sym.kind == TypeKind.Trait:
                    cmp = ir.Inst(
                        ir.InstKind.Cmp, [
                            ir.Name(kind),
                            ir.Selector(ir.UINT_T, left, ir.Name("_id_")),
                            ir.IntLit(
                                ir.UINT_T,
                                str(left_sym.info.indexof(expr_right_sym))
                            )
                        ]
                    )
                else:
                    cmp = ir.Inst(
                        ir.InstKind.Cmp, [
                            ir.Name(kind),
                            ir.Selector(ir.UINT_T, left, ir.Name("_idx_")),
                            ir.IntLit(ir.UINT_T, str(expr_right_sym.id))
                        ]
                    )
                self.cur_func.inline_alloca(ir.BOOL_T, tmp, cmp)
                if expr.has_var:
                    expr_var_exit_label = self.cur_func.local_name()
                    self.cur_func.add_cond_single_br(
                        ir.Inst(
                            ir.InstKind.BooleanNot, [ir.Ident(ir.BOOL_T, tmp)]
                        ), expr_var_exit_label
                    )
                    var_t = self.ir_type(expr.var.typ)
                    var_t2 = var_t if isinstance(var_t, ir.Ptr) else var_t.ptr()
                    if left_sym.kind == TypeKind.Enum:
                        union_name = f"{cg_utils.mangle_symbol(left_sym)}6_Union"
                        union_type = ir.Type(union_name)
                        obj_val = ir.Selector(union_type, left, ir.Name("obj"))
                        val = ir.Selector(
                            ir.Type(self.ir_type(expr.typ)), obj_val,
                            ir.Name(f"v{expr.right.variant_info.value}")
                        )
                        if expr.var.is_ref:
                            val = ir.Inst(ir.InstKind.GetPtr, [val], var_t2)
                    else:
                        val = ir.Inst(
                            ir.InstKind.Cast, [
                                ir.Selector(ir.RAWPTR_T, left, ir.Name("obj")),
                                var_t2
                            ]
                        )
                        if not (
                            (isinstance(var_t2, ir.Ptr) and var_t2.is_managed)
                            or expr.var.is_ref
                        ):
                            val = ir.Inst(
                                ir.InstKind.LoadPtr, [val], var_t2.typ
                            )
                    unique_name = self.cur_func.unique_name(expr.var.name)
                    expr.scope.update_ir_name(expr.var.name, unique_name)
                    self.cur_func.inline_alloca(var_t, unique_name, val)
                    self.cur_func.add_label(expr_var_exit_label)
                return ir.Ident(ir.BOOL_T, tmp)
            elif expr.op in (Kind.KwIn, Kind.KwNotIn):
                expr_left_typ = self.comp.comptime_number_to_type(expr_left_typ)
                left = self.gen_expr_with_cast(expr_left_typ, expr.left)
                right = self.gen_expr(expr.right)
                left_sym = expr_left_typ.symbol()
                right_sym = expr.right.typ.symbol()
                contains_method = f"contains_{right_sym.id}"
                right_is_dyn_array = right_sym.kind == sym.TypeKind.DynArray
                if right_is_dyn_array:
                    full_name = f"_R4core8DynArray{len(contains_method)}{contains_method}"
                else:
                    full_name = f"_R4core5Array{len(contains_method)}{contains_method}"
                if not right_sym.info.has_contains_method:
                    self.generate_contains_method(
                        left_sym, right_sym, right_is_dyn_array, expr_left_typ,
                        expr_right_typ, full_name
                    )
                args = [ir.Name(full_name), right]
                if not right_is_dyn_array:
                    args.append(ir.IntLit(ir.UINT_T, str(right_sym.info.size)))
                args.append(left)
                call = ir.Inst(ir.InstKind.Call, args, ir.BOOL_T)
                if expr.op == Kind.KwNotIn:
                    call = ir.Inst(ir.InstKind.BooleanNot, [call], ir.BOOL_T)
                tmp = self.cur_func.local_name()
                self.cur_func.inline_alloca(ir.BOOL_T, tmp, call)
                return ir.Ident(ir.BOOL_T, tmp)

            left = self.gen_expr_with_cast(expr_left_typ, expr.left)
            right = self.gen_expr_with_cast(expr_left_typ, expr.right)

            tmp = self.cur_func.local_name()
            typ_sym = expr_left_typ.symbol()
            if expr.op.is_overloadable_op() and (
                typ_sym.kind in (
                    TypeKind.Array, TypeKind.DynArray, TypeKind.String,
                    TypeKind.Struct, TypeKind.Slice
                ) or (typ_sym.kind == TypeKind.Enum and typ_sym.info.is_tagged)
            ) and not isinstance(expr_left_typ, type.Ptr):
                if typ_sym.kind == TypeKind.Array:
                    if expr.op == Kind.Eq:
                        name = "_R4core8array_eqF"
                    elif expr.op == Kind.Ne:
                        name = "_R4core8array_neF"
                    size, _ = self.comp.type_size(expr_left_typ)
                    self.cur_func.inline_alloca(
                        self.ir_type(expr.typ), tmp,
                        ir.Inst(
                            ir.InstKind.Call, [
                                ir.Name(name), left, right,
                                ir.IntLit(ir.UINT_T, str(size))
                            ]
                        )
                    )
                else:
                    op_method = OVERLOADABLE_OPERATORS_STR[str(expr.op)]
                    left_is_ptr = isinstance(left.typ, ir.Ptr)
                    right_is_ptr = isinstance(right.typ, ir.Ptr)
                    self.cur_func.inline_alloca(
                        self.ir_type(expr.typ), tmp,
                        ir.Inst(
                            ir.InstKind.Call, [
                                ir.Name(
                                    cg_utils.mangle_symbol(typ_sym) +
                                    f"{len(op_method)}{op_method}M"
                                ), left if left_is_ptr else
                                ir.Inst(ir.InstKind.GetPtr, [left]),
                                right if right_is_ptr else
                                ir.Inst(ir.InstKind.GetPtr, [right])
                            ]
                        )
                    )
                return ir.Ident(expr.typ, tmp)
            if expr.op.is_relational():
                kind = str(expr.op)
                self.cur_func.inline_alloca(
                    self.ir_type(expr.typ), tmp,
                    ir.Inst(ir.InstKind.Cmp, [ir.Name(kind), left, right])
                )
            elif expr.op in (Kind.Div, Kind.Mod):
                is_div = expr.op == Kind.Div
                kind = ir.InstKind.Div if is_div else ir.InstKind.Mod
                self.cur_func.inline_alloca(
                    self.ir_type(expr.typ), tmp, ir.Inst(kind, [left, right])
                )
            else:
                if op_kind := ir.get_ir_op(expr.op):
                    self.cur_func.inline_alloca(
                        self.ir_type(expr.typ), tmp,
                        ir.Inst(op_kind, [left, right])
                    )
                else:
                    assert False
            return ir.Ident(self.ir_type(expr.typ), tmp)
        elif isinstance(expr, ast.IfExpr):
            is_void_value = expr.typ in self.void_types
            exit_label = self.cur_func.local_name()
            else_label = self.cur_func.local_name(
            ) if expr.has_else else exit_label
            tmp = ir.Ident(
                self.ir_type(expr.expected_typ),
                self.cur_func.local_name() if not is_void_value else ""
            )
            if not is_void_value:
                self.cur_func.alloca(tmp)
            self.cur_func.add_comment(f"if expr (end: {exit_label})")
            next_branch = ""
            for i, b in enumerate(expr.branches):
                is_branch_void_value = b.typ in self.void_types
                self.cur_func.add_comment(f"if branch (is_else: {b.is_else})")
                if b.is_else:
                    self.cur_func.add_label(else_label)
                else:
                    if isinstance(b.cond, ast.GuardExpr):
                        cond = self.gen_guard_expr(b.cond, "", "", False)
                    else:
                        cond = self.gen_expr_with_cast(self.comp.bool_t, b.cond)
                    branch_label = self.cur_func.local_name()
                    if i == len(expr.branches) - 1:
                        next_branch = exit_label
                    elif i + 1 == len(expr.branches
                                      ) - 1 and expr.branches[i + 1].is_else:
                        next_branch = else_label
                    else:
                        next_branch = self.cur_func.local_name()
                    if isinstance(b.cond, ast.GuardExpr):
                        self.cur_func.add_cond_single_br(
                            ir.Inst(ir.InstKind.BooleanNot, [cond]), next_branch
                        )
                        if b.cond.has_cond:
                            self.cur_func.add_cond_single_br(
                                ir.Inst(
                                    ir.InstKind.BooleanNot,
                                    [self.gen_expr(b.cond.cond)]
                                ), next_branch
                            )
                    else:
                        self.cur_func.add_cond_br(
                            cond, branch_label, next_branch
                        )
                    self.cur_func.add_label(branch_label)
                if is_branch_void_value:
                    self.gen_expr_with_cast(
                        expr.expected_typ, b.expr
                    ) # ignore void value
                else:
                    self.cur_func.store(
                        tmp, self.gen_expr_with_cast(expr.expected_typ, b.expr)
                    )
                self.cur_func.add_comment(
                    "if expr branch (goto to other branch)"
                )
                self.cur_func.add_br(exit_label)
                if len(next_branch) > 0 and next_branch != else_label:
                    self.cur_func.add_label(next_branch)
            self.cur_func.add_label(exit_label)
            if not is_void_value:
                return tmp
        elif isinstance(expr, ast.MatchExpr):
            is_void_value = expr.typ in self.void_types
            exit_match = self.cur_func.local_name()
            self.cur_func.add_comment(f"match expr (end: {exit_match})")
            tmp = ir.Ident(
                self.ir_type(expr.expected_typ),
                self.cur_func.local_name() if not is_void_value else ""
            )
            if not is_void_value:
                self.cur_func.alloca(tmp)
            if isinstance(expr.expr, ast.GuardExpr):
                cond = self.gen_guard_expr(expr.expr, "", "", False)
                self.cur_func.add_cond_single_br(cond, exit_match)
                if expr.expr.has_cond:
                    self.cur_func.add_cond_single_br(
                        ir.Inst(
                            ir.InstKind.BooleanNot,
                            [self.gen_expr(expr.expr.cond)]
                        ), exit_match
                    )
                match_expr = ir.Ident(
                    self.ir_type(expr.expr.typ), expr.expr.vars[0].name
                )
            else:
                match_expr = self.gen_expr_with_cast(expr.expr.typ, expr.expr)
            for b in expr.branches:
                is_branch_void_value = b.typ in self.void_types
                b_label = "" if b.is_else else self.cur_func.local_name()
                b_exit = exit_match if b.is_else else self.cur_func.local_name()
                if not b.is_else:
                    self.cur_func.add_comment(
                        f"match expr patterns (len: {len(b.pats)})"
                    )
                for i, p in enumerate(b.pats):
                    next_pat = self.cur_func.local_name(
                    ) if i < len(b.pats) - 1 else b_exit
                    tmp2 = self.cur_func.local_name()
                    if expr.is_typematch:
                        if p.typ.sym.kind == TypeKind.Trait:
                            value_idx_x = ir.IntLit(
                                ir.UINT_T,
                                str(
                                    expr.expected_typ.symbol().indexof(
                                        p.typ.sym
                                    )
                                )
                            )
                        elif p.typ.sym.kind == TypeKind.Enum:
                            value_idx_x = ir.IntLit(
                                ir.UINT_T, str(p.variant_info.value)
                            )
                        else:
                            value_idx_x = ir.IntLit(
                                ir.UINT_T, str(p.typ.sym.id)
                            )
                        if p.typ.sym.kind == TypeKind.Enum and not p.typ.sym.info.is_tagged:
                            self.cur_func.inline_alloca(
                                ir.BOOL_T, tmp2,
                                ir.Inst(
                                    ir.InstKind.Cmp,
                                    [ir.Name("=="), match_expr, value_idx_x]
                                )
                            )
                        else:
                            self.cur_func.inline_alloca(
                                ir.BOOL_T, tmp2,
                                ir.Inst(
                                    ir.InstKind.Cmp, [
                                        ir.Name("=="),
                                        ir.Selector(
                                            self.ir_type(expr.expr.typ),
                                            match_expr,
                                            ir.Name(
                                                "_id_" if p.typ.sym.kind ==
                                                TypeKind.Trait else "_idx_"
                                            )
                                        ), value_idx_x
                                    ]
                                )
                            )
                        if b.has_var:
                            var_t = self.ir_type(b.var_typ)
                            var_t2 = var_t.ptr(
                            ) if not isinstance(var_t, ir.Ptr) else var_t
                            e_expr_typ_sym = expr.expr.typ.symbol()
                            if e_expr_typ_sym.kind == TypeKind.Enum:
                                obj_f = ir.Selector(
                                    e_expr_typ_sym.name + "6_Union", match_expr,
                                    ir.Name("obj")
                                )
                                val = ir.Selector(
                                    self.ir_type(p.variant_info.typ), obj_f,
                                    ir.Name(f"v{p.variant_info.value}")
                                )
                                if b.var_is_ref:
                                    val = ir.Inst(ir.InstKind.GetPtr, [val])
                            else:
                                val = ir.Inst(
                                    ir.InstKind.Cast, [
                                        ir.Selector(
                                            ir.RAWPTR_T, match_expr,
                                            ir.Name("obj")
                                        ), var_t
                                    ]
                                )
                                if not (
                                    isinstance(var_t, ir.Ptr)
                                    and var_t.is_managed
                                ):
                                    val = ir.Inst(
                                        ir.InstKind.LoadPtr, [val], var_t.typ
                                    )
                            unique_name = self.cur_func.unique_name(b.var_name)
                            b.scope.update_ir_name(b.var_name, unique_name)
                            self.cur_func.inline_alloca(var_t, unique_name, val)
                    else:
                        p_typ_sym = p.typ.symbol()
                        tmp2_i = ir.Ident(ir.BOOL_T, tmp2)
                        if isinstance(p, ast.RangeExpr):
                            rend_l = self.cur_func.local_name()
                            start = self.gen_expr_with_cast(p.typ, p.start)
                            end = self.gen_expr_with_cast(p.typ, p.end)
                            self.cur_func.alloca(tmp2_i)
                            self.cur_func.add_cond_br(
                                ir.Inst(
                                    ir.InstKind.Cmp,
                                    [ir.Name(">="), match_expr, start]
                                ), rend_l, next_pat
                            )
                            self.cur_func.add_label(rend_l)
                            self.cur_func.store(
                                tmp2_i,
                                ir.Inst(
                                    ir.InstKind.Cmp,
                                    [ir.Name("<="), match_expr, end]
                                )
                            )
                        else:
                            p_conv = self.gen_expr_with_cast(p.typ, p)
                            if p_typ_sym.kind.is_primitive(
                            ) or p_typ_sym.kind == TypeKind.Enum:
                                inst = ir.Inst(
                                    ir.InstKind.Cmp,
                                    [ir.Name("=="), match_expr, p_conv]
                                )
                            else:
                                lhs = match_expr if isinstance(
                                    match_expr.typ, ir.Ptr
                                ) else ir.Inst(
                                    ir.InstKind.GetPtr, [match_expr]
                                )
                                rhs = p_conv if isinstance(
                                    p_conv.typ, ir.Ptr
                                ) else ir.Inst(ir.InstKind.GetPtr, [p_conv])
                                inst = ir.Inst(
                                    ir.InstKind.Call, [
                                        ir.Name(
                                            f"{cg_utils.mangle_symbol(p_typ_sym)}4_eq_M"
                                        ), lhs, rhs
                                    ]
                                )
                            self.cur_func.inline_alloca(ir.BOOL_T, tmp2, inst)
                    self.cur_func.add_cond_br(
                        ir.Ident(ir.BOOL_T, tmp2), b_label, next_pat
                    )
                    if i < len(b.pats) - 1:
                        self.cur_func.add_label(next_pat)
                if not b.is_else:
                    self.cur_func.add_label(b_label)
                    if b.has_cond:
                        self.cur_func.add_cond_single_br(
                            ir.Inst(
                                ir.InstKind.BooleanNot, [
                                    self.gen_expr_with_cast(
                                        self.comp.bool_t, b.cond
                                    )
                                ]
                            ), b_exit
                        )
                if is_branch_void_value:
                    self.gen_expr_with_cast(
                        expr.expected_typ, b.expr
                    ) # ignore void value
                else:
                    self.cur_func.store(
                        tmp, self.gen_expr_with_cast(expr.expected_typ, b.expr)
                    )
                self.cur_func.add_br(exit_match)
                if not b.is_else:
                    self.cur_func.add_label(b_exit)
            self.cur_func.add_label(exit_match)
            if not is_void_value:
                return tmp
        elif isinstance(expr, ast.LoopControlExpr):
            if expr.op == Kind.KwContinue:
                if self.while_continue_expr and not isinstance(
                    self.while_continue_expr, ast.EmptyExpr
                ):
                    if isinstance(self.while_continue_expr, ir.Inst):
                        self.cur_func.add_inst(self.while_continue_expr)
                    else:
                        self.gen_expr(self.while_continue_expr)
                self.cur_func.add_br(self.loop_entry_label)
            else:
                self.gen_defer_stmts(
                    scope = expr.scope, run_defer_previous = True,
                    scope_limit = self.loop_scope
                )
                self.cur_func.add_br(self.loop_exit_label)
            return ir.Skip()
        elif isinstance(expr, ast.ReturnExpr):
            wrap_result = isinstance(self.cur_func_ret_typ, type.Result)
            ret_typ = self.cur_func_ret_typ.typ if wrap_result else self.cur_func_ret_typ
            if self.inside_test:
                self.cur_func.store(
                    ir.Selector(
                        ir.UINT8_T, ir.Ident(ir.TEST_T.ptr(), "test"),
                        ir.Name("result")
                    ), ir.IntLit(ir.UINT8_T, "1")
                )
                self.gen_defer_stmts(
                    scope = expr.scope, run_defer_previous = True
                )
                self.cur_func.add_ret_void()
            elif expr.has_expr:
                is_array = self.cur_func_ret_typ.symbol().kind == TypeKind.Array
                expr_ = self.gen_expr_with_cast(ret_typ, expr.expr)
                if is_array and self.comp.prefs.target_backend == prefs.Backend.C:
                    size, _ = self.comp.type_size(ret_typ)
                    tmp = self.stacked_instance(
                        ir.Type(self.cur_func.arr_ret_struct)
                    )
                    self.cur_func.add_call(
                        "_R4core3mem4copyF", [
                            ir.Selector(
                                self.ir_type(ret_typ), tmp, ir.Name("arr")
                            ), expr_,
                            ir.IntLit(ir.UINT_T, str(size))
                        ]
                    )
                    expr_ = tmp
                if wrap_result:
                    expr_ = self.result_value(self.cur_func_ret_typ, expr_)
                self.gen_defer_stmts(
                    scope = expr.scope, run_defer_previous = True
                )
                self.cur_func.add_ret(expr_)
            elif wrap_result:
                self.gen_defer_stmts(
                    scope = expr.scope, run_defer_previous = True
                )
                self.cur_func.add_ret(self.result_void(self.cur_func_ret_typ))
            else:
                self.gen_defer_stmts(
                    scope = expr.scope, run_defer_previous = True
                )
                self.cur_func.add_ret_void()
            return ir.Skip()
        elif isinstance(expr, ast.ThrowExpr):
            t_sym = expr.expr.typ.symbol()
            if t_sym.implement_trait(
                self.comp.throwable_sym
            ) or t_sym == self.comp.throwable_sym:
                self.gen_return_trace_add(expr.pos)
                expr_ = self.result_error(
                    self.cur_func_ret_typ, expr.expr.typ,
                    self.gen_expr(expr.expr)
                )
                self.gen_defer_stmts(
                    True, ir.Selector(ir.BOOL_T, expr_, ir.Name("is_err")),
                    scope = expr.scope, run_defer_previous = True
                )
                self.cur_func.add_ret(expr_)
                return ir.Skip()
            else:
                assert False
        else:
            if expr is None:
                raise Exception(expr)
            raise Exception(expr.__class__, expr.pos)
        return ir.Skip()

    def gen_left_assign(self, expr, right, assign_op):
        old_inside_lhs_assign = self.inside_lhs_assign
        self.inside_lhs_assign = True
        left = None
        require_store_ptr = False
        if isinstance(expr, ast.Ident):
            if expr.name == "_":
                self.cur_func.add_inst(
                    ir.Inst(
                        ir.InstKind.Cast, [self.gen_expr(right), ir.VOID_T]
                    )
                )
                self.inside_lhs_assign = old_inside_lhs_assign
                return None, require_store_ptr
            else:
                left = self.gen_expr(expr)
        elif isinstance(expr, ast.SelectorExpr):
            if expr.is_indirect or expr.is_boxed_indirect:
                left_ir = self.gen_expr(expr.left)
                left = ir.Inst(ir.InstKind.LoadPtr, [left_ir], left_ir.typ.typ)
            else:
                left = self.gen_expr(expr)
        elif isinstance(expr, ast.IndexExpr):
            left_ir_typ = self.ir_type(expr.left_typ)
            left_sym = expr.left_typ.symbol()
            sym_is_boxed = left_sym.is_boxed()
            if left_sym.kind in (
                TypeKind.DynArray, TypeKind.Slice
            ) and assign_op == Kind.Assign:
                rec = self.gen_expr_with_cast(expr.left_typ, expr.left)
                if not isinstance(left_ir_typ, ir.Ptr):
                    rec = ir.Inst(ir.InstKind.GetPtr, [rec])
                expr_right = self.gen_expr_with_cast(right.typ, right)
                val_sym = right.typ.symbol()
                method_name = "_R4core5Slice3setM" if left_sym.kind == TypeKind.Slice else "_R4core8DynArray3setM"
                self.cur_func.add_call(
                    method_name, [
                        rec,
                        self.gen_expr(expr.index),
                        ir.Inst(ir.InstKind.GetPtr, [expr_right])
                    ]
                )
                self.inside_lhs_assign = old_inside_lhs_assign
                return None, require_store_ptr
            if isinstance(left_ir_typ, (ir.Ptr, ir.Array)):
                expr.is_ref = True
            left = self.gen_expr_with_cast(expr.typ, expr)
            if isinstance(left.typ, ir.Ptr):
                require_store_ptr = left.typ.nr_level() > 0
        self.inside_lhs_assign = old_inside_lhs_assign
        return left, require_store_ptr

    def gen_defer_stmt_vars(self, defer_stmts):
        for defer_stmt in defer_stmts:
            defer_stmt.flag_var = self.cur_func.local_name()
            self.cur_func.alloca(
                ir.Ident(ir.BOOL_T, defer_stmt.flag_var),
                ir.IntLit(ir.BOOL_T, "0")
            )

    def gen_defer_stmts(
        self, gen_errdefer = False, last_ret_was_err = None, scope = None,
        run_defer_previous = False, scope_limit = None
    ):
        for i in range(len(self.cur_func_defer_stmts) - 1, -1, -1):
            defer_stmt = self.cur_func_defer_stmts[i]
            if not (
                (run_defer_previous and scope.start >= defer_stmt.scope.start)
                or (scope.start == defer_stmt.scope.start)
            ):
                continue
            if defer_stmt.mode == ast.DeferMode.ERROR and not gen_errdefer:
                # should be run only when an error occurs
                continue
            if defer_stmt.mode == ast.DeferMode.SUCCESS and gen_errdefer:
                # should not be run in case an error occurs
                continue
            if scope_limit != None and defer_stmt.scope.start == scope_limit.start:
                # do not generate `defer` that are in a scope greater than
                # the established limit, this is used by `break`
                break
            defer_start = self.cur_func.local_name()
            defer_end = self.cur_func.local_name()
            self.cur_func.add_comment(
                f"defer_stmt (start: {defer_start}, end: {defer_end}, mode: {defer_stmt.mode})"
            )
            self.cur_func.add_cond_br(
                ir.Ident(ir.BOOL_T, defer_stmt.flag_var), defer_start, defer_end
            )
            self.cur_func.add_label(defer_start)
            if defer_stmt.mode == ast.DeferMode.ERROR:
                self.cur_func.add_cond_single_br(
                    ir.Inst(ir.InstKind.BooleanNot, [last_ret_was_err]),
                    defer_end
                )
            self.gen_expr(defer_stmt.expr)
            self.cur_func.add_label(defer_end)

    def gen_const(self, const_sym):
        if const_sym.has_evaled_expr:
            const_sym.has_ir_expr = True
            const_sym.ir_expr = self.gen_expr_with_cast(
                const_sym.typ, const_sym.evaled_expr
            )
            return const_sym.ir_expr
        if const_sym.has_ir_expr:
            return const_sym.ir_expr
        const_sym.has_ir_expr = True
        const_sym.ir_expr = self.gen_expr_with_cast(
            const_sym.typ, const_sym.expr
        )
        return const_sym.ir_expr

    def result_void(self, typ):
        tmp = self.stacked_instance(self.ir_type(typ))
        self.cur_func.store(
            ir.Selector(ir.BOOL_T, tmp, ir.Name("is_err")),
            ir.IntLit(ir.BOOL_T, "0")
        )
        return tmp

    def result_value(self, typ, value):
        tmp = self.stacked_instance(self.ir_type(typ))
        self.cur_func.store(
            ir.Selector(ir.BOOL_T, tmp, ir.Name("is_err")),
            ir.IntLit(ir.BOOL_T, "0")
        )
        self.cur_func.store(
            ir.Selector(
                self.ir_type(self.cur_func_ret_typ.typ), tmp, ir.Name("value")
            ), value
        )
        return tmp

    def result_error(self, typ, expr_t, expr):
        tmp = self.stacked_instance(self.ir_type(typ))
        self.cur_func.store(
            ir.Selector(ir.BOOL_T, tmp, ir.Name("is_err")),
            ir.IntLit(ir.BOOL_T, "1")
        )
        self.cur_func.store(
            ir.Selector(ir.THROWABLE_T, tmp, ir.Name("err")),
            self.trait_value(expr, expr_t, self.comp.throwable_t)
        )
        return tmp

    def option_value(self, typ, value):
        tmp = self.stacked_instance(self.ir_type(typ))
        self.cur_func.store(
            ir.Selector(ir.BOOL_T, tmp, ir.Name("is_none")),
            ir.IntLit(ir.BOOL_T, "0")
        )
        self.cur_func.store(
            ir.Selector(self.ir_type(typ.typ), tmp, ir.Name("value")), value
        )
        return tmp

    def option_none(self, typ):
        tmp = self.stacked_instance(self.ir_type(typ))
        self.cur_func.store(
            ir.Selector(ir.BOOL_T, tmp, ir.Name("is_none")),
            ir.IntLit(ir.BOOL_T, "1")
        )
        return tmp

    def runtime_error(self, msg):
        self.cur_func.add_call(
            "_R4core13runtime_errorF", [
                self.gen_string_literal(utils.smart_quote(msg, False)),
                self.empty_slice()
            ]
        )

    def variadic_args(self, vargs, var_arg_typ_):
        if len(vargs) == 0:
            return self.empty_slice(var_arg_typ_.typ.symbol())
        elem_size, _ = self.comp.type_size(var_arg_typ_)
        return ir.Inst(
            ir.InstKind.Call, [
                ir.Name("_R4core5Slice10from_arrayF"),
                ir.ArrayLit(self.ir_type(var_arg_typ_), vargs),
                ir.IntLit(ir.UINT_T, str(elem_size)),
                ir.IntLit(ir.UINT_T, str(len(vargs)))
            ]
        )

    def default_value(self, typ, custom_tmp = None):
        if isinstance(typ, type.Type) and typ.is_boxed:
            return ir.NoneLit(ir.RAWPTR_T)
        if isinstance(typ, (type.Ptr, type.Func, type.Boxedptr)):
            return ir.NoneLit(ir.RAWPTR_T)
        if isinstance(typ, type.Option):
            if typ.is_pointer():
                return ir.NoneLit(ir.RAWPTR_T)
            return self.option_none(typ)
        if typ == self.comp.rune_t:
            return ir.RuneLit("0")
        elif typ in (
            self.comp.bool_t, self.comp.int8_t, self.comp.int16_t,
            self.comp.int32_t, self.comp.int64_t, self.comp.uint8_t,
            self.comp.uint16_t, self.comp.uint32_t, self.comp.uint64_t,
            self.comp.int_t, self.comp.uint_t
        ):
            return ir.IntLit(self.ir_type(typ), "0")
        elif typ in (self.comp.float32_t, self.comp.float64_t):
            return ir.FloatLit(self.ir_type(typ), "0.0")
        elif typ == self.comp.string_t:
            return ir.Ident(ir.STRING_T, "_R4core12empty_string")
        elif isinstance(typ, type.Result):
            if typ.typ == self.comp.void_t:
                return self.result_void(typ)
            return self.result_value(typ, self.default_value(typ.typ))
        typ_sym = typ.symbol()
        if typ_sym.kind == TypeKind.Array:
            return ir.ArrayLit(
                self.ir_type(typ), [self.default_value(typ_sym.info.elem_typ)]
            )
        elif typ_sym.kind == TypeKind.Slice:
            return self.empty_slice()
        elif typ_sym.kind == TypeKind.DynArray:
            return self.empty_dyn_array(typ_sym)
        elif typ_sym.kind == TypeKind.Enum:
            if typ_sym.info.is_tagged and typ_sym.default_value:
                return self.gen_expr_with_cast(typ, typ_sym.default_value)
            return ir.IntLit(self.ir_type(typ_sym.info.underlying_typ), "0")
        elif typ_sym.kind == TypeKind.Tuple:
            tmp = self.stacked_instance(typ)
            for i, typ in enumerate(typ_sym.info.types):
                self.cur_func.store(
                    ir.Selector(self.ir_type(typ), tmp, ir.Name(f"f{i}")),
                    self.default_value(typ)
                )
            return tmp
        elif typ_sym.kind == TypeKind.Struct:
            if custom_tmp:
                tmp = custom_tmp
            else:
                tmp = self.stacked_instance(self.ir_type(typ))
            for f in typ_sym.full_fields():
                if f.typ.symbol().kind == TypeKind.Array:
                    continue
                sltor = ir.Selector(self.ir_type(f.typ), tmp, ir.Name(f.name))
                if f.has_def_expr:
                    val = self.gen_expr_with_cast(f.typ, f.def_expr)
                else:
                    val = self.default_value(f.typ)
                self.cur_func.store(sltor, val)
            return tmp
        elif typ_sym.kind == TypeKind.Trait:
            if typ_sym.default_value:
                return self.gen_expr_with_cast(typ, typ_sym.default_value)
            return ir.NoneLit(ir.RAWPTR_T)
        return None

    def empty_dyn_array(self, typ_sym, cap = None):
        elem_typ = typ_sym.info.elem_typ
        size, _ = self.comp.type_size(elem_typ)
        return ir.Inst(
            ir.InstKind.Call, [
                ir.Name("_R4core8DynArray3newF"),
                ir.IntLit(ir.UINT_T, str(size)), cap
                or ir.IntLit(ir.UINT_T, "0")
            ]
        )

    def empty_slice(self):
        return ir.Inst(
            ir.InstKind.Call, [
                ir.Name("_R4core5Slice3newF"),
                ir.Ident(ir.RAWPTR_T, "NULL"),
                ir.IntLit(ir.UINT_T, "0")
            ]
        )

    def gen_string_literal(self, lit, size = None):
        size = size or utils.bytestr(lit).len
        if size == 0:
            return ir.Ident(ir.STRING_T, "_R4core12empty_string")
        lit_hash = hash(lit)
        if lit_hash in self.generated_string_literals:
            return ir.Ident(
                ir.STRING_T, self.generated_string_literals[lit_hash]
            )
        tmp = self.stacked_instance(
            ir.STRING_T,
            custom_name = f"STRLIT{len(self.generated_string_literals)}"
        )
        self.out_rir.globals.append(
            ir.GlobalVar(False, False, ir.STRING_T, tmp.name)
        )
        self.init_string_lits_fn.store(
            ir.Selector(ir.UINT8_T.ptr(), tmp, ir.Name("ptr")),
            ir.StringLit(lit, size)
        )
        self.init_string_lits_fn.store(
            ir.Selector(ir.UINT_T, tmp, ir.Name("len")),
            ir.IntLit(ir.UINT_T, str(size))
        )
        self.init_string_lits_fn.store(
            ir.Selector(ir.BOOL_T, tmp, ir.Name("is_lit")),
            ir.IntLit(ir.BOOL_T, "1")
        )
        self.generated_string_literals[lit_hash] = tmp.name
        return tmp

    def stacked_instance(self, typ, init_value = None, custom_name = None):
        tmp = ir.Ident(typ, custom_name or self.cur_func.local_name())
        if not custom_name:
            if init_value:
                self.cur_func.alloca(tmp, init_value)
            else:
                self.cur_func.alloca(tmp)
        return tmp

    def boxed_instance(self, typ, size, custom_name = None):
        tmp = ir.Ident(
            typ if isinstance(typ, ir.Ptr) else typ.ptr(True), custom_name
            or self.cur_func.local_name()
        )
        inst = ir.Inst(
            ir.InstKind.Call, [
                ir.Name("_R4core3mem11boxed_allocF"),
                ir.IntLit(ir.UINT_T, str(size)),
                ir.Name("NULL")
            ]
        )
        if custom_name:
            self.cur_func.store(tmp, inst)
        else:
            self.cur_func.alloca(tmp, inst)
        return tmp

    def trait_value(self, value, value_typ, trait_typ):
        if value_typ == trait_typ:
            return value
        value_sym = self.comp.comptime_number_to_type(value_typ).symbol()
        trait_sym = trait_typ.symbol()
        size, _ = self.comp.type_size(value_typ)
        trait_size, _ = self.comp.type_symbol_size(trait_sym, True)
        tmp = self.boxed_instance(self.ir_type(trait_typ), str(trait_size))
        is_ptr = isinstance(value.typ, ir.Ptr)
        for f in trait_sym.fields:
            f_typ = self.ir_type(f.typ)
            value_f = ir.Selector(f_typ, value, ir.Name(f.name))
            if not isinstance(f_typ, ir.Ptr):
                f_typ = f_typ.ptr(True)
                value_f = ir.Inst(ir.InstKind.GetPtr, [value_f], f_typ)
            self.cur_func.store(
                ir.Selector(f_typ, tmp, ir.Name(f.name)), value_f
            )
        if not is_ptr:
            value = ir.Inst(ir.InstKind.GetPtr, [value])
        value = value if is_ptr else ir.Inst(
            ir.InstKind.Call, [
                ir.Name("_R4core3mem7raw_dupF"), value,
                ir.IntLit(ir.UINT_T, str(size))
            ]
        )
        if value_sym.kind == TypeKind.Trait:
            index = ir.Inst(
                ir.InstKind.Call, [
                    ir.Name(
                        f"{cg_utils.mangle_symbol(trait_sym)}17__index_of_vtbl__"
                    ),
                    ir.Selector(ir.UINT_T, value, ir.Name("_idx_"))
                ], ir.UINT_T
            )
            self.cur_func.store(
                ir.Selector(ir.RAWPTR_T, tmp, ir.Name("obj")),
                ir.Selector(ir.RAWPTR_T, value, ir.Name("obj"))
            )
        else:
            vtbl_idx_x = trait_sym.info.indexof(value_sym)
            index = ir.IntLit(ir.UINT_T, str(vtbl_idx_x))
            self.cur_func.store(
                ir.Selector(ir.RAWPTR_T, tmp, ir.Name("obj")), value
            )
        self.cur_func.store(ir.Selector(ir.UINT_T, tmp, ir.Name("_id_")), index)
        self.cur_func.store(
            ir.Selector(ir.UINT_T, tmp, ir.Name("_idx_")),
            ir.IntLit(ir.UINT_T, str(value_sym.id))
        )
        return tmp

    def tagged_enum_value(
        self, enum_sym, variant_name, value, custom_tmp = None
    ):
        if custom_tmp:
            tmp = custom_tmp
        else:
            mangled_name = cg_utils.mangle_symbol(enum_sym)
            if enum_sym.info.is_boxed:
                size, _ = self.comp.type_symbol_size(enum_sym, True)
                tmp = self.boxed_instance(ir.Type(mangled_name), size)
            else:
                tmp = self.stacked_instance(ir.Type(mangled_name))
        uint_t = ir.UINT_T
        variant_info = enum_sym.info.get_variant(variant_name)
        self.cur_func.store(
            ir.Selector(uint_t, tmp, ir.Name("_idx_")),
            ir.IntLit(uint_t, variant_info.value)
        )
        if variant_info.has_typ and value and not isinstance(
            value, ast.EmptyExpr
        ):
            arg0 = self.gen_expr_with_cast(variant_info.typ, value)
            obj_f = ir.Selector(
                ir.Type(f"{cg_utils.mangle_symbol(enum_sym)}6_Union"), tmp,
                ir.Name("obj")
            )
            self.cur_func.store(
                ir.Selector(
                    self.ir_type(variant_info.typ), obj_f,
                    ir.Name(f"v{variant_info.value}")
                ), arg0
            )
        return tmp

    def tagged_enum_variant_with_fields_value(
        self, enum_sym, variant_name, value, custom_tmp = None
    ):
        if custom_tmp:
            tmp = custom_tmp
        else:
            mangled_name = cg_utils.mangle_symbol(enum_sym)
            if enum_sym.info.is_boxed:
                size, _ = self.comp.type_symbol_size(enum_sym, True)
                tmp = self.boxed_instance(ir.Type(mangled_name), size)
            else:
                tmp = self.stacked_instance(ir.Type(mangled_name))
        variant_info = enum_sym.info.get_variant(variant_name)
        self.cur_func.store(
            ir.Selector(ir.UINT_T, tmp, ir.Name("_idx_")),
            ir.IntLit(ir.UINT_T, variant_info.value)
        )
        obj_f = ir.Selector(
            ir.Type(f"{cg_utils.mangle_symbol(enum_sym)}6_Union"), tmp,
            ir.Name("obj")
        )
        self.cur_func.store(
            ir.Selector(
                self.ir_type(variant_info.typ), obj_f,
                ir.Name(f"v{variant_info.value}")
            ), value
        )
        return tmp

    def gen_return_trace_add(self, pos):
        tmp = self.stacked_instance(ir.Type("_R4core9CallTrace"))
        self.cur_func.store(
            ir.Selector(ir.STRING_T, tmp, ir.Name("name")),
            self.gen_string_literal(self.cur_func.name)
        )
        self.cur_func.store(
            ir.Selector(ir.STRING_T, tmp, ir.Name("file")),
            self.gen_string_literal(pos.file)
        )
        self.cur_func.store(
            ir.Selector(ir.UINT_T, tmp, ir.Name("line")),
            ir.IntLit(ir.UINT_T, str(pos.line + 1))
        )
        self.cur_func.add_call(
            "_R4core11ReturnTrace3addM", [
                ir.Inst(
                    ir.InstKind.GetPtr, [
                        ir.Ident(
                            ir.Type("_R4core11ReturnTrace"),
                            "_R4core12return_trace"
                        )
                    ]
                ), tmp
            ]
        )

    def gen_return_trace_clear(self):
        self.cur_func.add_call(
            "_R4core11ReturnTrace5clearM", [
                ir.Inst(
                    ir.InstKind.GetPtr, [
                        ir.Ident(
                            ir.Type("_R4core11ReturnTrace"),
                            "_R4core12return_trace"
                        )
                    ]
                )
            ]
        )

    def gen_guard_expr(self, expr, entry_label, exit_label, gen_cond = True):
        gexpr = self.gen_expr(expr.expr)
        var_name = self.cur_func.unique_name(expr.vars[0].name)
        expr.scope.update_ir_name(expr.vars[0].name, var_name)
        if expr.is_result:
            cond = ir.Inst(
                ir.InstKind.BooleanNot,
                [ir.Selector(ir.BOOL_T, gexpr, ir.Name("is_err"))]
            )
            var_t = self.ir_type(expr.typ)
            self.cur_func.inline_alloca(
                var_t, var_name, ir.Selector(var_t, gexpr, ir.Name("value"))
            )
        elif expr.expr.typ.is_pointer():
            cond = ir.Inst(
                ir.InstKind.Cmp,
                [ir.Name("!="), gexpr,
                 ir.NoneLit(ir.RAWPTR_T)]
            )
            self.cur_func.inline_alloca(self.ir_type(expr.typ), var_name, gexpr)
        else:
            cond = ir.Inst(
                ir.InstKind.BooleanNot,
                [ir.Selector(ir.BOOL_T, gexpr, ir.Name("is_none"))]
            )
            self.cur_func.inline_alloca(
                self.ir_type(expr.typ), var_name,
                ir.Selector(
                    self.ir_type(expr.expr.typ.typ), gexpr, ir.Name("value")
                )
            )
        if expr.has_cond and gen_cond:
            self.cur_func.add_cond_br(
                self.gen_expr(expr.cond), entry_label, exit_label
            )
        return cond

    def ir_type(self, typ, gen_self_arg = False):
        if isinstance(typ, type.Result):
            name = f"_R6Result{cg_utils.mangle_type(typ.typ)}"
            if name not in self.generated_opt_res_types:
                is_void = typ.typ in self.void_types
                self.out_rir.types.append(
                    ir.Struct(
                        False, name, [
                            ir.Field(
                                "value", ir.UINT8_T
                                if is_void else self.ir_type(typ.typ)
                            ),
                            ir.Field("is_err", ir.BOOL_T),
                            ir.Field("err", ir.THROWABLE_T)
                        ]
                    )
                )
                self.generated_opt_res_types.append(name)
            return ir.Type(name)
        elif isinstance(typ, type.Option):
            if typ.is_pointer():
                return self.ir_type(typ.typ)
            name = f"_R6Option{cg_utils.mangle_type(typ.typ)}"
            if name not in self.generated_opt_res_types:
                is_void = typ.typ in self.void_types
                self.out_rir.types.append(
                    ir.Struct(
                        False, name, [
                            ir.Field(
                                "value", ir.UINT8_T
                                if is_void else self.ir_type(typ.typ)
                            ),
                            ir.Field("is_none", ir.BOOL_T)
                        ]
                    )
                )
                self.generated_opt_res_types.append(name)
            return ir.Type(name)
        elif isinstance(typ, type.Func):
            args = []
            if gen_self_arg:
                args.append(ir.RAWPTR_T)
            for arg in typ.args:
                args.append(self.ir_type(arg.typ))
            return ir.Function(args, self.ir_type(typ.ret_typ))
        elif isinstance(typ, type.Slice):
            return ir.SLICE_T
        elif isinstance(typ, type.Array):
            return ir.Array(self.ir_type(typ.typ), typ.size)
        elif isinstance(typ, type.DynArray):
            return ir.DYN_ARRAY_T
        elif isinstance(typ, type.Ptr):
            inner_t = self.ir_type(typ.typ)
            if isinstance(inner_t, ir.Ptr) and inner_t.is_managed:
                return inner_t
            return ir.Ptr(inner_t)
        elif isinstance(typ, type.Boxedptr):
            return ir.RAWPTR_T
        typ_sym = typ.symbol()
        if typ_sym.kind == TypeKind.DynArray:
            return ir.DYN_ARRAY_T
        elif typ_sym.kind == TypeKind.Array:
            return ir.Array(
                self.ir_type(typ_sym.info.elem_typ), typ_sym.info.size
            )
        elif typ_sym.kind == TypeKind.Never:
            return ir.VOID_T
        elif typ_sym.kind == TypeKind.None_:
            return ir.RAWPTR_T
        elif typ_sym.kind == TypeKind.Enum:
            if typ_sym.info.is_tagged:
                typ_ = ir.Type(cg_utils.mangle_symbol(typ_sym))
                if isinstance(typ, type.Type) and typ.is_boxed:
                    typ_ = typ_.ptr(True)
                return typ_
            typ_ = ir.Type(str(typ_sym.info.underlying_typ))
            if isinstance(typ, type.Type) and typ.is_boxed:
                typ_ = typ_.ptr(True)
            return typ_
        elif typ_sym.kind.is_primitive():
            typ_ = None
            if typ_sym.name == "int":
                typ_ = ir.INT_T
            elif typ_sym.name == "uint":
                typ_ = ir.UINT_T
            else:
                typ_ = ir.Type(typ_sym.name)
            if isinstance(typ, type.Type) and typ.is_boxed:
                typ_ = typ_.ptr(True)
            return typ_
        res = ir.Type(cg_utils.mangle_symbol(typ_sym))
        if isinstance(typ, type.Type) and typ.is_boxed:
            return res.ptr(True)
        return res

    def gen_types(self):
        type_symbols = self.sort_type_symbols(
            self.get_type_symbols(self.comp.universe)
        )
        for ts in type_symbols:
            if ts.kind == TypeKind.Tuple:
                mangled_name = cg_utils.mangle_symbol(ts)
                if mangled_name in self.generated_tuple_types:
                    continue
                self.generated_tuple_types.append(mangled_name)
                fields = []
                for i, f in enumerate(ts.info.types):
                    fields.append(ir.Field(f"f{i}", self.ir_type(f)))
                self.out_rir.types.append(
                    ir.Struct(False, mangled_name, fields)
                )
            elif ts.kind == TypeKind.Enum:
                # TODO: in the self-hosted compiler calculate the enum value here
                # not in register nor resolver.
                if ts.info.is_tagged:
                    mangled_name = cg_utils.mangle_symbol(ts)
                    fields = []
                    for v in ts.info.variants:
                        if v.has_typ:
                            fields.append(
                                ir.Field(f"v{v.value}", self.ir_type(v.typ))
                            )
                    union_name = mangled_name + "6_Union"
                    self.out_rir.types.append(ir.Union(union_name, fields))
                    struct_fields = [
                        ir.Field("_idx_", ir.UINT_T),
                        ir.Field("obj", ir.Type(union_name))
                    ]
                    self.out_rir.types.append(
                        ir.Struct(False, mangled_name, struct_fields)
                    )
            elif ts.kind == TypeKind.Trait:
                ts_name = cg_utils.mangle_symbol(ts)
                fields = [
                    ir.Field("_idx_", ir.UINT_T),
                    ir.Field("_id_", ir.UINT_T),
                    ir.Field("obj", ir.RAWPTR_T)
                ]
                for f in ts.fields:
                    f_typ = self.ir_type(f.typ)
                    if not isinstance(f_typ, ir.Ptr):
                        f_typ = f_typ.ptr()
                    fields.append(ir.Field(f.name, f_typ))
                self.out_rir.types.append(ir.Struct(False, ts_name, fields))
                # Virtual table
                vtbl_name = f"{ts_name}4Vtbl"
                static_vtbl_name = f"{ts_name}4VTBL"
                fields = []
                for m in ts.syms:
                    if isinstance(m, sym.Func):
                        proto = m.typ()
                        proto.args.insert(
                            0,
                            sym.Arg(
                                "self", m.self_is_mut,
                                type.Ptr(self.comp.void_t), None, False, NO_POS
                            )
                        )
                        method_name = OVERLOADABLE_OPERATORS_STR[
                            m.name
                        ] if m.name in OVERLOADABLE_OPERATORS_STR else m.name
                        fields.append(
                            ir.Field(method_name, self.ir_type(proto))
                        )
                funcs = []
                index_of_vtbl = []
                for idx, its in enumerate(ts.info.implements):
                    map = {}
                    for m in ts.syms:
                        if isinstance(m, sym.Func):
                            method_name = OVERLOADABLE_OPERATORS_STR[
                                m.name
                            ] if m.name in OVERLOADABLE_OPERATORS_STR else m.name
                            if ts_method := its.find(m.name):
                                map[method_name] = cg_utils.mangle_symbol(
                                    ts_method
                                )
                            else:
                                map[method_name] = cg_utils.mangle_symbol(m)
                    funcs.append(map)
                    index_of_vtbl.append((its.qualname(), its.id, idx))
                if len(funcs) > 0 and ts.info.has_objects:
                    self.out_rir.types.append(
                        ir.Struct(False, vtbl_name, fields)
                    )
                    self.out_rir.decls.append(
                        ir.VTable(
                            vtbl_name, static_vtbl_name, ts_name,
                            len(ts.info.implements), funcs
                        )
                    )
                    index_of_vtbl_fn = ir.FuncDecl(
                        False, ast.Attributes(), False,
                        cg_utils.mangle_symbol(ts) + "17__index_of_vtbl__",
                        [ir.Ident(ir.UINT_T, "self")], False, ir.UINT_T, False
                    )
                    for child_name, child_idx_, child_idx_x in index_of_vtbl:
                        l1 = index_of_vtbl_fn.local_name()
                        l2 = index_of_vtbl_fn.local_name()
                        index_of_vtbl_fn.add_comment(f"for: '{child_name}'")
                        index_of_vtbl_fn.add_cond_br(
                            ir.Inst(
                                ir.InstKind.Cmp, [
                                    "==",
                                    ir.Ident(ir.UINT_T, "self"),
                                    ir.IntLit(ir.UINT_T, str(child_idx_))
                                ]
                            ), l1, l2
                        )
                        index_of_vtbl_fn.add_label(l1)
                        index_of_vtbl_fn.add_ret(
                            ir.IntLit(ir.UINT_T, str(child_idx_x))
                        )
                        index_of_vtbl_fn.add_label(l2)
                    index_of_vtbl_fn.add_ret(ir.IntLit(ir.UINT_T, "0"))
                    self.out_rir.decls.append(index_of_vtbl_fn)
            elif ts.kind in (
                TypeKind.Struct, TypeKind.String, TypeKind.DynArray
            ):
                fields = []
                for f in ts.full_fields():
                    fields.append(ir.Field(f.name, self.ir_type(f.typ)))
                self.out_rir.types.append(
                    ir.Struct(
                        ts.info.is_opaque, cg_utils.mangle_symbol(ts), fields
                    )
                )

    def get_type_symbols(self, root):
        ts = []
        for s in root.syms:
            if isinstance(s, sym.Type):
                if not (
                    s.kind
                    in (TypeKind.DynArray, TypeKind.Alias, TypeKind.Never)
                    or s.kind.is_primitive()
                ):
                    ts.append(s)
            ts += self.get_type_symbols(s)
        return ts

    def sort_type_symbols(self, tss):
        dg = utils.DepGraph()
        typ_names = []
        for ts in tss:
            ts.mangled_name = cg_utils.mangle_symbol(ts)
            typ_names.append(ts.mangled_name)
        for ts in tss:
            field_deps = []
            if ts.kind == TypeKind.Array:
                elem_sym = ts.info.elem_typ.symbol()
                if elem_sym == None:
                    continue
                dep = cg_utils.mangle_symbol(elem_sym)
                if dep in typ_names:
                    field_deps.append(dep)
            elif ts.kind == TypeKind.DynArray:
                elem_sym = ts.info.elem_typ.symbol()
                if elem_sym == None:
                    continue
                dep = cg_utils.mangle_symbol(elem_sym)
                if dep in typ_names:
                    field_deps.append(dep)
            elif ts.kind == TypeKind.Tuple:
                for f in ts.info.types:
                    fsym = f.symbol()
                    if fsym == None:
                        continue
                    dep = cg_utils.mangle_symbol(fsym)
                    if dep not in typ_names or dep in field_deps or isinstance(
                        f, type.Option
                    ) or fsym.is_boxed():
                        continue
                    field_deps.append(dep)
            elif ts.kind == TypeKind.Enum and ts.info.is_tagged:
                for variant in ts.info.variants:
                    if variant.has_typ:
                        variant_sym = variant.typ.symbol()
                        if variant_sym == None:
                            continue
                        if variant_sym.is_boxed(
                        ) or isinstance(variant.typ, type.Option):
                            continue
                        dep = cg_utils.mangle_symbol(variant_sym)
                        if dep not in typ_names or dep in field_deps:
                            continue
                        field_deps.append(dep)
            elif ts.kind == TypeKind.Trait:
                for base in ts.info.bases:
                    dep = cg_utils.mangle_symbol(base)
                    if dep not in typ_names or dep in field_deps:
                        continue
                    field_deps.append(dep)
                for f in ts.fields:
                    fsym = f.typ.symbol()
                    if fsym == None:
                        continue
                    dep = cg_utils.mangle_symbol(fsym)
                    if dep not in typ_names or dep in field_deps or isinstance(
                        f.typ, type.Option
                    ) or fsym.is_boxed():
                        continue
                    field_deps.append(dep)
            elif ts.kind == TypeKind.Struct:
                for base in ts.info.bases:
                    dep = cg_utils.mangle_symbol(base)
                    if dep not in typ_names or dep in field_deps or base.is_boxed(
                    ):
                        continue
                    field_deps.append(dep)
                for f in ts.fields:
                    fsym = f.typ.symbol()
                    if fsym == None:
                        continue
                    dep = cg_utils.mangle_symbol(fsym)
                    if dep not in typ_names or dep in field_deps or isinstance(
                        f.typ, type.Option
                    ) or fsym.is_boxed():
                        continue
                    field_deps.append(dep)
            dg.add(ts.mangled_name, field_deps)
        dg_sorted = dg.resolve()
        if not dg_sorted.acyclic:
            utils.error(
                "rivetc.codegen: the following types form a dependency cycle:\n"
                + dg_sorted.display_cycles()
            )
        types_sorted = []
        for node in dg_sorted.nodes:
            for ts in tss:
                if ts.mangled_name == node.name:
                    types_sorted.append(ts)
        return types_sorted

    def generate_contains_method(
        self, left_sym, right_sym, right_is_dyn_array, expr_left_typ,
        expr_right_typ, full_name
    ):
        elem_typ = right_sym.info.elem_typ
        right_sym.info.has_contains_method = True
        if right_is_dyn_array:
            self_idx_ = ir.Ident(ir.DYN_ARRAY_T, "self")
            elem_idx_ = ir.Ident(self.ir_type(expr_left_typ), "_elem_")
            contains_decl = ir.FuncDecl(
                False, ast.Attributes(), False, full_name,
                [self_idx_, elem_idx_], False, ir.BOOL_T, False
            )
        else:
            self_idx_ = ir.Ident(self.ir_type(expr_right_typ), "self")
            elem_idx_ = ir.Ident(self.ir_type(expr_left_typ), "_elem_")
            contains_decl = ir.FuncDecl(
                False, ast.Attributes(), False, full_name,
                [self_idx_, ir.Ident(ir.UINT_T, "_len_"), elem_idx_], False,
                ir.BOOL_T, False
            )
        inc_v = ir.Ident(ir.UINT_T, contains_decl.local_name())
        contains_decl.alloca(inc_v, ir.IntLit(ir.UINT_T, "0"))
        cond_l = contains_decl.local_name()
        body_l = contains_decl.local_name()
        ret_l = contains_decl.local_name()
        continue_l = contains_decl.local_name()
        exit_l = contains_decl.local_name()
        contains_decl.add_label(cond_l)
        contains_decl.add_cond_br(
            ir.Inst(
                ir.InstKind.Cmp, [
                    ir.Name("<"), inc_v,
                    ir.Selector(ir.UINT_T, self_idx_, ir.Name("len"))
                    if right_is_dyn_array else ir.Ident(ir.UINT_T, "_len_")
                ]
            ), body_l, exit_l
        )
        contains_decl.add_label(body_l)
        right_elem_typ_sym = right_sym.info.elem_typ.symbol()
        is_primitive = right_elem_typ_sym.kind.is_primitive() or (
            right_elem_typ_sym.kind == TypeKind.Enum
            and not right_elem_typ_sym.info.is_tagged
        )
        if right_is_dyn_array:
            cur_elem = ir.Inst(
                ir.InstKind.Cast, [
                    ir.Inst(
                        ir.InstKind.Call, [
                            ir.Name("_R4core8DynArray7raw_getM"),
                            ir.Inst(ir.InstKind.GetPtr, [self_idx_]), inc_v
                        ]
                    ),
                    self.ir_type(expr_left_typ).ptr()
                ]
            )
            if is_primitive or (
                isinstance(elem_typ, type.Type) and elem_typ.is_boxed
            ):
                cur_elem = ir.Inst(
                    ir.InstKind.LoadPtr, [cur_elem], cur_elem.typ
                )
        else:
            cur_elem = ir.Inst(
                ir.InstKind.GetElementPtr, [self_idx_, inc_v],
                self.ir_type(expr_left_typ)
            )
            if is_primitive or (
                isinstance(elem_typ, type.Type) and elem_typ.is_boxed
            ):
                cur_elem = ir.Inst(
                    ir.InstKind.LoadPtr, [cur_elem], cur_elem.typ
                )
        if is_primitive:
            cond = ir.Inst(
                ir.InstKind.Cmp, [ir.Name("=="), cur_elem, elem_idx_]
            )
        else:
            if not isinstance(elem_idx_.typ, ir.Ptr):
                elem_idx_ = ir.Inst(ir.InstKind.GetPtr, [elem_idx_])
            cond = ir.Inst(
                ir.InstKind.Call, [
                    ir.Name(f"{cg_utils.mangle_symbol(left_sym)}4_eq_M"),
                    cur_elem, elem_idx_
                ]
            )
        contains_decl.add_cond_br(cond, ret_l, continue_l)
        contains_decl.add_label(ret_l)
        contains_decl.add_ret(ir.IntLit(ir.BOOL_T, "1"))
        contains_decl.add_label(continue_l)
        contains_decl.add_inst(ir.Inst(ir.InstKind.Inc, [inc_v]))
        contains_decl.add_br(cond_l)
        contains_decl.add_label(exit_l)
        contains_decl.add_ret(ir.IntLit(ir.BOOL_T, "0"))
        self.out_rir.decls.append(contains_decl)
