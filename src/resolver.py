# Copyright (C) 2022 The Rivet Team. All rights reserved.
# Use of this source code is governed by an MIT license
# that can be found in the LICENSE file.

from .token import Kind
from .ast import sym, type
from .ast.sym import Visibility
from . import ast, report, register, utils

class Resolver:
	def __init__(self, comp):
		self.comp = comp
		self.sf = None
		self.cur_sym = None
		self.core_prelude = []
		self.cur_fn = None
		self.cur_fn_scope = None

		self.inside_is_comparation = False

		self.self_sym = None

	def resolve_files(self, source_files):
		register.Register(self.comp).visit_files(source_files)
		if report.ERRORS > 0:
			return

		self.cur_sym = self.comp.pkg_sym
		for sf in source_files:
			self.resolve_file(sf)

	def resolve_file(self, sf):
		self.sf = sf
		old_cur_sym = self.cur_sym
		if sf.mod_sym:
			self.cur_sym = sf.mod_sym
		self.import_core_prelude()
		self.resolve_decls(sf.decls)
		if sf.mod_sym:
			self.cur_sym = old_cur_sym

	def resolve_decls(self, decls):
		for decl in decls:
			self.resolve_decl(decl)

	def resolve_decl(self, decl):
		if isinstance(decl, ast.ComptimeIfDecl):
			if decl.branch_idx != -1:
				self.resolve_decls(decl.branches[decl.branch_idx].decls)
		elif isinstance(decl, ast.UsingDecl):
			if isinstance(decl.path, (ast.Ident, ast.PkgExpr)):
				name = decl.path.name if isinstance(
				    decl.path, ast.Ident
				) else self.comp.prefs.pkg_name
				if len(decl.symbols) == 0:
					if isinstance(decl.path, ast.PkgExpr):
						report.error(
						    "invalid `using` declaration", decl.path.pos
						)
					elif _ := self.comp.pkg_sym.find(name):
						report.error(
						    f"use of undeclared external package `{name}`",
						    decl.path.pos
						)
						report.help(f"use `pkg::{name}` instead")
					else:
						report.error(
						    "expected symbol list after name", decl.path.pos
						)
				elif sym_info := self.comp.universe.find(name):
					self.resolve_selective_using_symbols(decl.symbols, sym_info)
				else:
					report.error(
					    f"use of undeclared external package `{name}`",
					    decl.path.pos
					)
			elif isinstance(decl.path, ast.PathExpr):
				self.resolve_expr(decl.path)
				if not decl.path.has_error:
					if len(decl.symbols) == 0:
						self.sf.imported_symbols[decl.alias
						                         ] = decl.path.field_info
					else:
						self.resolve_selective_using_symbols(
						    decl.symbols, decl.path.field_info
						)
		if isinstance(decl, ast.ExternDecl):
			self.resolve_decls(decl.protos)
		elif isinstance(decl, ast.ConstDecl):
			self.resolve_type(decl.typ)
			self.resolve_expr(decl.expr)
		elif isinstance(decl, ast.StaticDecl):
			self.resolve_type(decl.typ)
			self.resolve_expr(decl.expr)
		elif isinstance(decl, ast.ModDecl):
			old_sym = self.cur_sym
			self.cur_sym = decl.sym
			self.resolve_decls(decl.decls)
			self.cur_sym = old_sym
		elif isinstance(decl, ast.TypeDecl):
			self.resolve_type(decl.parent)
		elif isinstance(decl, ast.TraitDecl):
			self.resolve_decls(decl.decls)
		elif isinstance(decl, ast.UnionDecl):
			self.self_sym = decl.sym
			for v in decl.variants:
				self.resolve_type(v)
			self.resolve_decls(decl.decls)
			self.self_sym = None
		elif isinstance(decl, ast.EnumDecl):
			self.self_sym = decl.sym
			self.resolve_decls(decl.decls)
			self.self_sym = None
		elif isinstance(decl, ast.StructDecl):
			self.self_sym = decl.sym
			self.resolve_decls(decl.decls)
			self.self_sym = None
		elif isinstance(decl, ast.StructField):
			self.resolve_type(decl.typ)
			if decl.has_def_expr:
				self.resolve_expr(decl.def_expr)
		elif isinstance(decl, ast.ExtendDecl):
			if self.resolve_type(decl.typ):
				self.self_sym = decl.typ.get_sym()
				if decl.is_for_trait:
					if self.resolve_type(decl.for_trait):
						trait_sym = decl.for_trait.get_sym()
						if trait_sym.kind == sym.TypeKind.Trait:
							typ_sym = decl.typ.get_sym()
							trait_sym.info.implements.append(typ_sym)
							not_implemented = []
							for proto in trait_sym.syms:
								if d := typ_sym.find(proto.name):
									d.uses += 1
									# check signature
									ptyp = proto.typ()
									dtyp = d.typ()
									if self.resolve_type(
									    ptyp
									) and self.resolve_type(
									    dtyp
									) and ptyp != dtyp:
										report.error(
										    f"type `{typ_sym.name}` incorrectly implements {d.kind()} `{d.name}` of trait `{trait_sym.name}`",
										    d.name_pos
										)
										report.note(f"expected `{ptyp}`")
										report.note(f"found `{dtyp}`")
								elif not proto.has_body: # trait implementation
									not_implemented.append(proto.name)
							if len(not_implemented) > 0:
								word = "method" if len(
								    not_implemented
								) == 1 else "methods"
								report.error(
								    f"type `{typ_sym.name}` does not implement trait `{trait_sym.name}`",
								    decl.pos
								)
								report.note(
								    f"missing {word}: `{'`, `'.join(not_implemented)}`"
								)
						else:
							report.error(
							    f"`{ft_sym.name}` is not a trait", decl.pos
							)
				elif isinstance(decl.typ, (type.Array, type.Slice, type.Tuple)):
					s = decl.typ.get_sym()
					for d in decl.decls:
						if isinstance(d, ast.FnDecl):
							if d.is_method:
								self_typ = type.Type(self.self_sym)
								if d.self_is_ref:
									self_typ = type.Ref(self_typ, d.self_is_mut)
								d.self_typ = self_typ
								if not d.scope.exists("self"):
									d.scope.add(
									    sym.Object(
									        False, "self", self_typ, True
									    )
									)
								try:
									d.sym = sym.Fn(
									    sym.ABI.Rivet, d.vis, d.is_extern,
									    d.is_unsafe, d.is_method, False, d.name,
									    d.args, d.ret_typ, d.has_named_args,
									    d.has_body, d.name_pos, d.self_is_mut,
									    d.self_is_ref
									)
									d.sym.self_typ = self_typ
									s.add(d.sym)
								except utils.CompilerError as e:
									report.error(e.args[0], d.name_pos)
							else:
								report.error(
								    f"{s.kind}s can only have methods",
								    d.name_pos
								)
						else:
							report.error(
							    f"{s.kind}s can only have methods", d.pos
							)
				self.resolve_decls(decl.decls)
				self.self_sym = None
		elif isinstance(decl, ast.TestDecl):
			self.cur_fn_scope = decl.scope
			self.resolve_stmts(decl.stmts)
			self.cur_fn_scope = None
		elif isinstance(decl, ast.FnDecl):
			self.cur_fn = decl.sym
			self.cur_fn_scope = decl.scope
			for arg in decl.args:
				self.resolve_type(arg.typ)
				if arg.has_def_expr: self.resolve_expr(arg.def_expr)
			self.resolve_type(decl.ret_typ)
			self.resolve_stmts(decl.stmts)
			self.cur_fn = None
			self.cur_fn_scope = None
		elif isinstance(decl, ast.DestructorDecl):
			self.resolve_stmts(decl.stmts)

	def resolve_stmts(self, stmts):
		for stmt in stmts:
			self.resolve_stmt(stmt)

	def resolve_stmt(self, stmt):
		if isinstance(stmt, ast.LetStmt):
			self.register_variables(stmt.scope, stmt.lefts)
			for l in stmt.lefts:
				self.resolve_type(l.typ)
			self.resolve_expr(stmt.right)
		elif isinstance(stmt, ast.AssignStmt):
			self.resolve_expr(stmt.left)
			self.resolve_expr(stmt.right)
		elif isinstance(stmt, ast.LabelStmt):
			if self.cur_fn_scope != None:
				try:
					self.cur_fn_scope.add(sym.Label(stmt.label))
				except utils.CompilerError as e:
					report.error(e.args[0], stmt.pos)
		elif isinstance(stmt, ast.ExprStmt):
			self.resolve_expr(stmt.expr)
		elif isinstance(stmt, ast.WhileStmt):
			self.resolve_expr(stmt.cond)
			self.resolve_stmt(stmt.stmt)
		elif isinstance(stmt, ast.ForInStmt):
			for v in stmt.vars:
				try:
					stmt.scope.add(
					    sym.Object(False, v, self.comp.void_t, False)
					)
				except utils.CompilerError as e:
					report.error(e.args[0], stmt.pos)
			self.resolve_expr(stmt.iterable)
			self.resolve_stmt(stmt.stmt)

	def register_variables(self, scope, var_decls):
		for vd in var_decls:
			try:
				scope.add(sym.Object(vd.is_mut, vd.name, vd.typ, False))
			except utils.CompilerError as e:
				report.error(e.args[0], vd.pos)

	def resolve_expr(self, expr):
		if isinstance(expr, ast.ParExpr):
			self.resolve_expr(expr.expr)
		elif isinstance(expr, ast.Ident):
			self.resolve_ident(expr)
		elif isinstance(expr, ast.SelfExpr):
			if self_ := expr.scope.lookup("self"):
				expr.typ = self_.typ
			else:
				report.error("cannot find `self` in this scope", expr.pos)
		elif isinstance(expr, ast.SelfTyExpr):
			if self.self_sym != None:
				expr.typ = type.Type(self.self_sym)
			else:
				report.error("cannot resolve type for `Self`", expr.pos)
		elif isinstance(expr, ast.TypeNode):
			self.resolve_type(expr.typ)
		elif isinstance(expr, ast.TupleLiteral):
			for e in expr.exprs:
				self.resolve_expr(e)
		elif isinstance(expr, ast.ArrayLiteral):
			for e in expr.elems:
				self.resolve_expr(e)
		elif isinstance(expr, ast.StructLiteral):
			self.resolve_expr(expr.expr)
			for f in expr.fields:
				self.resolve_expr(f.expr)
		elif isinstance(expr, ast.UnaryExpr):
			self.resolve_expr(expr.right)
		elif isinstance(expr, ast.BinaryExpr):
			self.inside_is_comparation = expr.op in (Kind.KeyNotIs, Kind.KeyIs)
			self.resolve_expr(expr.left)
			self.resolve_expr(expr.right)
		elif isinstance(expr, ast.PostfixExpr):
			self.resolve_expr(expr.left)
		elif isinstance(expr, ast.CastExpr):
			self.resolve_type(expr.typ)
			self.resolve_expr(expr.expr)
		elif isinstance(expr, ast.IndexExpr):
			self.resolve_expr(expr.left)
			self.resolve_expr(expr.index)
		elif isinstance(expr, ast.RangeExpr):
			if expr.has_start: self.resolve_expr(expr.start)
			if expr.has_end: self.resolve_expr(expr.end)
		elif isinstance(expr, ast.SelectorExpr):
			self.resolve_expr(expr.left)
		elif isinstance(expr, ast.PathExpr):
			self.resolve_path_expr(expr)
		elif isinstance(expr, ast.BuiltinCallExpr):
			for a in expr.args:
				self.resolve_expr(a)
		elif isinstance(expr, ast.CallExpr):
			self.resolve_expr(expr.left)
			for a in expr.args:
				self.resolve_expr(a.expr)
			if expr.has_err_handler():
				if expr.err_handler.has_varname():
					# register error value
					try:
						expr.err_handler.scope.add(
						    sym.Object(
						        False, expr.err_handler.varname,
						        self.comp.error_t, False
						    )
						)
					except utils.CompilerError as e:
						report.error(e.args[0], expr.err_handler.varname_pos)
				self.resolve_expr(expr.err_handler.expr)
		elif isinstance(expr, ast.ReturnExpr):
			self.resolve_expr(expr.expr)
		elif isinstance(expr, ast.RaiseExpr):
			self.resolve_expr(expr.expr)
		elif isinstance(expr, ast.Block):
			for stmt in expr.stmts:
				self.resolve_stmt(stmt)
			if expr.is_expr: self.resolve_expr(expr.expr)
		elif isinstance(expr, ast.IfExpr):
			if expr.is_comptime:
				# evalue comptime if expression
				branch_idx = -1
				for idx, b in enumerate(expr.branches):
					cond_val = False
					if not b.is_else:
						cond_val = self.comp.evalue_comptime_condition(b.cond)
					if branch_idx == -1:
						if cond_val or b.is_else:
							branch_idx = idx
							if isinstance(b.expr, ast.Block):
								for stmt in b.expr.stmts:
									self.resolve_stmt(stmt)
							break
				expr.branch_idx = branch_idx
				if expr.branch_idx > -1:
					self.resolve_expr(expr.branches[expr.branch_idx].expr)
			else:
				for b in expr.branches:
					if not b.is_else: self.resolve_expr(b.cond)
					self.resolve_expr(b.expr)
		elif isinstance(expr, ast.MatchExpr):
			self.resolve_expr(expr.expr)
			for b in expr.branches:
				for p in b.pats:
					self.resolve_expr(p)
				if b.has_var:
					b.var_type = b.pats[0].typ
					if b.var_is_ref:
						b.var_type = type.Ref(b.var_type, b.var_is_mut)
					try:
						expr.scope.add(
						    sym.Object(False, b.var_name, b.var_type, False)
						)
					except utils.CompilerError as e:
						report.error(e.args[0], b.pats[0].pos)
				self.resolve_expr(b.expr)
		elif isinstance(expr, ast.GuardExpr):
			for v in expr.vars:
				try:
					expr.scope.add(
					    sym.Object(False, v, self.comp.void_t, False)
					)
				except utils.CompilerError as e:
					report.error(e.args[0], expr.pos)
			self.resolve_expr(expr.expr)
			if expr.has_cond:
				self.resolve_expr(expr.cond)

	def find_symbol(self, symbol, name, pos):
		if s := symbol.find(name):
			self.check_visibility(s, pos)
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
		    f"could not find `{name}` in {symbol.sym_kind()} `{symbol.name}`",
		    pos
		)
		return None

	def resolve_ident(self, ident):
		if ident.name == "_":
			return # ignore special var
		elif ident.is_comptime:
			if not ast.is_comptime_constant(ident.name):
				report.error(
				    f"unknown comptime constant `{ident.name}`", ident.pos
				)
			return
		elif self.cur_fn and self.cur_fn.is_generic:
			if tup := self.cur_fn.find_type_arg(ident.name):
				ident.sym = tup[0]
				ident.type_arg_idx = tup[1]
				return

		if obj := ident.scope.lookup(ident.name):
			if isinstance(obj, sym.Label):
				report.error("expected value, found label", ident.pos)
			else:
				ident.is_obj = True
				ident.obj = obj
				ident.typ = obj.typ
		elif s := self.cur_sym.find(ident.name):
			s.uses += 1
			ident.sym = s
		elif s := self.sf.find_imported_symbol(ident.name):
			s.uses += 1
			ident.sym = s
		else:
			report.error(f"cannot find `{ident.name}` in this scope", ident.pos)

		# resolve generic
		if ident.sym:
			if ident.has_type_args:
				if ident.is_obj:
					report.error(
					    "objects cannot have type arguments", ident.pos
					)
				elif ident.sym.is_generic:
					len_i_ta = len(ident.type_args)
					len_sym_ta = len(ident.sym.type_arguments)
					errs = 0
					for i in range(len_i_ta):
						if not self.resolve_type(ident.type_args[i]):
							errs += 1
					if len_i_ta != len_sym_ta:
						kw = "few" if len_i_ta < len_sym_ta else "many"
						report.error(
						    f"too {kw} type arguments to {ident.sym.sym_kind()} `{ident.name}`",
						    ident.pos
						)
						report.note(
						    f"expected {len_sym_ta} type argument(s) found {len_i_ta}"
						)
					elif errs == 0:
						ident.sym = ident.sym.inst_generic(ident.type_args)
				else:
					report.error(
					    f"{ident.sym.sym_kind()} `{ident.name}` is not generic",
					    ident.pos
					)
			elif ident.sym.is_generic:
				report.error(
				    f"too few type arguments to {ident.sym.sym_kind()} `{ident.name}`",
				    ident.pos
				)
				report.note(
				    f"expected {len(ident.sym.type_arguments)} type argument(s), found 0"
				)

	def resolve_path_expr(self, path):
		if path.is_global:
			path.left_info = self.comp.universe
			if field_info := self.find_symbol(
			    self.comp.universe, path.field_name, path.field_pos
			):
				field_info.uses += 1
				path.field_info = field_info
			else:
				path.has_error = True
		elif isinstance(path.left, ast.PkgExpr):
			path.left_info = self.comp.pkg_sym
			if field_info := self.find_symbol(
			    self.comp.pkg_sym, path.field_name, path.field_pos
			):
				field_info.uses += 1
				path.field_info = field_info
			else:
				path.has_error = True
		elif isinstance(path.left, ast.SuperExpr):
			if self.cur_sym.parent != None and not self.cur_sym.parent.is_universe:
				path.left_info = self.cur_sym.parent
				if field_info := self.find_symbol(
				    self.cur_sym.parent, path.field_name, path.field_pos
				):
					field_info.uses += 1
					path.field_info = field_info
				else:
					path.has_error = True
			else:
				report.error("current module has no parent", path.left.pos)
		elif isinstance(path.left, ast.SelfExpr):
			path.left_info = self.cur_sym
			if field_info := self.find_symbol(
			    self.cur_sym, path.field_name, path.field_pos
			):
				field_info.uses += 1
				path.field_info = field_info
			else:
				path.has_error = True
		elif isinstance(path.left, ast.Ident):
			if local_sym := self.cur_sym.find(path.left.name):
				path.left_info = local_sym
				if field_info := self.find_symbol(
				    local_sym, path.field_name, path.field_pos
				):
					field_info.uses += 1
					path.field_info = field_info
				else:
					path.has_error = True
			elif imported_sym := self.sf.find_imported_symbol(path.left.name):
				path.left_info = imported_sym
				if field_info := self.find_symbol(
				    imported_sym, path.field_name, path.field_pos
				):
					field_info.uses += 1
					path.field_info = field_info
				else:
					path.has_error = True
			elif package := self.comp.universe.find(path.left.name):
				path.left_info = package
				if field_info := self.find_symbol(
				    package, path.field_name, path.field_pos
				):
					field_info.uses += 1
					path.field_info = field_info
				else:
					path.has_error = True
			else:
				report.error(
				    f"use of undeclared external package `{path.left.name}`",
				    path.left.pos
				)
				path.has_error = True
		elif isinstance(path.left, ast.SelfTyExpr):
			if self.self_sym != None:
				path.left_info = self.self_sym
				if field_info := self.find_symbol(
				    self.self_sym, path.field_name, path.field_pos
				):
					field_info.uses += 1
					path.field_info = field_info
				else:
					path.has_error = True
			else:
				report.error("cannot resolve `Self`", path.left.pos)
		elif isinstance(path.left, ast.PathExpr):
			self.resolve_expr(path.left)
			if not path.left.has_error:
				path.left_info = path.left.field_info
				if field_info := self.find_symbol(
				    path.left.field_info, path.field_name, path.field_pos
				):
					field_info.uses += 1
					path.field_info = field_info
				else:
					path.has_error = True
		else:
			report.error("bad use of path expression", path.pos)
			path.has_error = True

	def check_visibility(self, sym, pos):
		if sym.vis == Visibility.Private and not self.cur_sym.has_access_to(
		    sym
		):
			report.error(f"{sym.sym_kind()} `{sym.name}` is private", pos)

	def disallow_errtype_use(self, kind, pos):
		if (not self.inside_is_comparation) and kind == sym.TypeKind.ErrType:
			report.error("cannot use error type as a normal type", pos)
			report.note(
			    "only inside `raise` statement or `is` comparation can be used"
			)

	def resolve_type(self, typ):
		if isinstance(typ, type.Ref):
			return self.resolve_type(typ.typ)
		elif isinstance(typ, type.Ptr):
			return self.resolve_type(typ.typ)
		elif isinstance(typ, type.Variadic):
			if self.resolve_type(typ.typ):
				elem_sym = typ.typ.get_sym()
				if elem_sym.kind == type.TypeKind.Trait:
					elem_sym.info.has_objects = True
				typ.resolve(self.comp.universe.add_or_get_slice(typ.typ, False))
				return True
		elif isinstance(typ, type.Slice):
			if self.resolve_type(typ.typ):
				typ.resolve(
				    self.comp.universe.add_or_get_slice(typ.typ, typ.is_mut)
				)
				return True
		elif isinstance(typ, type.Array):
			if self.resolve_type(typ.typ):
				if typ_size := self.eval_size_expr(typ.size):
					if int(typ_size.lit) <= 0:
						report.error(
						    f"array size cannot be zero or negative (size: {typ_size.lit})",
						    typ.size.pos
						)
					typ.size = typ_size
					typ.resolve(
					    self.comp.universe.add_or_get_array(typ.typ, typ_size)
					)
					return True
				report.error(
				    "array size cannot use non-constant value", typ.size.pos
				)
		elif isinstance(typ, type.Tuple):
			res = False
			for t in typ.types:
				res = self.resolve_type(t)
			typ.resolve(self.comp.universe.add_or_get_tuple(typ.types))
			return res
		elif isinstance(typ, type.Fn):
			res = False
			for i in range(len(typ.args)):
				res = self.resolve_type(typ.args[i])
			res = self.resolve_type(typ.ret_typ)
			return res
		elif isinstance(typ, type.Optional):
			if self.resolve_type(typ.typ):
				if not isinstance(typ.typ, (type.Ptr, type.Ref)):
					typ.sym = self.comp.universe.add_or_get_optional(typ.typ)
				return True
			return False
		elif isinstance(typ, type.Result):
			if self.resolve_type(typ.typ):
				typ.sym = self.comp.universe.add_or_get_result(typ.typ)
				return True
			return False
		elif isinstance(typ, type.Type):
			if typ.is_resolved():
				return True # resolved
			if isinstance(typ.expr, ast.Ident):
				self.resolve_ident(typ.expr)
				if s := typ.expr.sym:
					if isinstance(s, sym.Type):
						pos = typ.expr.pos
						typ.resolve(s)
						if s.kind == sym.TypeKind.Alias: # unalias
							if self.resolve_type(s.info.parent):
								typ.unalias()
						s.uses += 1
						self.disallow_errtype_use(s.kind, pos)
						return True
					else:
						report.error(
						    f"expected type, found {s.sym_kind()}", typ.expr.pos
						)
				elif typ.expr.is_obj:
					report.error(
					    f"cannot find type `{typ.expr.name}` in this scope",
					    typ.expr.pos
					)
			elif isinstance(typ.expr, ast.PathExpr):
				self.resolve_path_expr(typ.expr)
				if not typ.expr.has_error:
					if isinstance(typ.expr.field_info, sym.Type):
						pos = typ.expr.pos
						typ.resolve(typ.expr.field_info)
						if typ.expr.field_info.kind == sym.TypeKind.Alias: # unalias
							if self.resolve_type(
							    typ.expr.field_info.info.parent
							):
								typ.unalias()
						typ.sym.uses += 1
						self.disallow_errtype_use(typ.sym, pos)
						return True
					else:
						report.error(
						    f"expected type, found {typ.expr.field_info.sym_kind()}",
						    typ.expr.pos
						)
			elif isinstance(typ.expr, ast.SelfTyExpr):
				if self.self_sym != None:
					self.self_sym.uses += 1
					typ.resolve(self.self_sym)
					return True
				else:
					report.error("cannot resolve type for `Self`", typ.expr.pos)
			else:
				report.error(f"expected type, found {typ.expr}", typ.expr.pos)
		return False

	def eval_size_expr(self, expr):
		if isinstance(expr, ast.IntegerLiteral):
			return expr
		elif isinstance(expr, ast.ParExpr):
			return self.eval_size_expr(expr.expr)
		elif isinstance(expr, ast.BinaryExpr):
			if left := self.eval_size_expr(expr.left):
				if right := self.eval_size_expr(expr.right):
					il = int(left.lit, 0)
					ir = int(right.lit, 0)
					if expr.op == Kind.Plus:
						return ast.IntegerLiteral(str(il + ir), expr.pos)
					elif expr.op == Kind.Minus:
						return ast.IntegerLiteral(str(il - ir), expr.pos)
					elif expr.op == Kind.Mult:
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
			if s := self.cur_sym.find(expr.name):
				if isinstance(s, sym.Const):
					if s.has_evaled_expr:
						return s.evaled_expr
					if evaled_expr := self.eval_size_expr(s.expr):
						s.evaled_expr = evaled_expr
						s.has_evaled_expr = True
						return s.evaled_expr
			else:
				report.error(
				    f"cannot find `{expr.name}` in this scope", expr.pos
				)
		elif isinstance(expr, ast.PathExpr):
			self.resolve_path_expr(expr)
			if not expr.has_error:
				if isinstance(expr.field_info, sym.Const):
					if expr.field_info.has_evaled_expr:
						return expr.field_info.evaled_expr
					if evaled_expr := self.eval_size_expr(expr.field_info.expr):
						expr.field_info.evaled_expr = evaled_expr
						expr.field_info.has_evaled_expr = True
						return expr.field_info.evaled_expr
		elif isinstance(expr, ast.BuiltinCallExpr):
			if expr.name in ("sizeof", "alignof"):
				size, align = self.comp.type_size(expr.args[0].typ)
				if expr.name == "sizeof":
					return ast.IntegerLiteral(str(size), expr.pos)
				else:
					return ast.IntegerLiteral(str(align), expr.pos)
		return None

	def check_imported_symbol(self, s, pos):
		if s.name in self.sf.imported_symbols:
			report.error(f"{s.sym_kind()} `{s.name}` is already imported", pos)
		elif self.cur_sym.find(s.name):
			report.error(
			    f"another symbol with the name `{s.name}` already exists", pos
			)
			report.help("you can use `as` to change the name of the import")

	def resolve_selective_using_symbols(self, symbols, path_sym):
		for isym in symbols:
			if isym.is_self:
				self.sf.imported_symbols[decl.alias] = path_sym
			else:
				if isym_ := path_sym.find(isym.name):
					self.check_visibility(isym_, isym.pos)
					self.check_imported_symbol(isym_, isym.pos)
					self.sf.imported_symbols[isym.alias] = isym_
				else:
					report.error(
					    f"could not find `{isym.name}` in {path_sym.sym_kind()} `{path_sym.name}`",
					    isym.pos
					)

	def import_core_prelude(self):
		if len(self.core_prelude) == 0:
			if core_pkg := self.comp.universe.find("core"):
				self.core_prelude = core_pkg.get_public_syms()
		for ps in self.core_prelude:
			self.sf.imported_symbols[ps.name] = ps
