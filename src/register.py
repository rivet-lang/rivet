# Copyright (C) 2022 The Rivet Team. All rights reserved.
# Use of this source code is governed by an MIT license
# that can be found in the LICENSE file.

import os, glob

from .ast import sym, type
from . import ast, parser, report, utils

class Register:
	def __init__(self, comp):
		self.comp = comp
		self.sf = None
		self.cur_sym = None
		self.errtype_nr = 1

	def visit_files(self, source_files):
		self.comp.pkg_sym = self.add_pkg(self.comp.prefs.pkg_name)
		self.cur_sym = self.comp.pkg_sym
		for sf in source_files:
			self.visit_file(sf)

	def visit_file(self, sf):
		self.sf = sf
		old_cur_sym = self.cur_sym
		if sf.mod_sym:
			self.cur_sym = sf.mod_sym
		self.visit_decls(sf.decls)
		if sf.mod_sym:
			self.cur_sym = old_cur_sym

	def add_pkg(self, name):
		idx = len(self.comp.universe.syms)
		self.comp.universe.add(sym.Pkg(ast.Visibility.Public, name))
		return self.comp.universe.syms[idx]

	def add_mod(self, vis, name):
		return self.cur_sym.add_or_extend_mod(sym.Mod(vis, name))

	def add_sym(self, sym, pos):
		try:
			self.cur_sym.add(sym)
		except utils.CompilerError as e:
			report.error(e.args[0], pos)

	def visit_decls(self, decls):
		for decl in decls:
			if isinstance(decl, ast.ComptimeIfDecl):
				# evalue comptime if declaration
				branch_idx = -1
				for idx, b in enumerate(decl.branches):
					cond_val = False
					if not b.is_else:
						cond_val = self.comp.evalue_comptime_condition(b.cond)
					if branch_idx == -1:
						if cond_val or b.is_else:
							branch_idx = idx
							break
				decl.branch_idx = branch_idx
				if decl.branch_idx > -1:
					self.visit_decls(decl.branches[decl.branch_idx].decls)
			elif isinstance(decl, ast.ExternPkg):
				continue
			elif isinstance(decl, ast.ExternDecl):
				self.visit_decls(decl.protos)
			elif isinstance(decl, ast.ModDecl):
				old_sym = self.cur_sym
				self.cur_sym = self.add_mod(decl.vis, decl.name)
				decl.sym = self.cur_sym
				if decl.is_unloaded:
					path = os.path.join(
					    os.path.dirname(self.sf.file), decl.name
					)
					if os.path.exists(path):
						if os.path.isdir(path):
							files = self.comp.prefs.filter_files_list(
							    glob.glob(os.path.join(path, "*.ri"))
							)
							if len(files) == 0:
								report.error(
								    f"cannot import module `{decl.name}` (.ri files not found)",
								    decl.pos
								)
							else:
								self.comp.mod_sym = self.cur_sym
								parser.Parser(
								    self.comp
								).parse_extern_module_files(files)
								if report.ERRORS > 0:
									self.comp.abort()
								self.comp.mod_sym = None
						else:
							report.error(
							    f"cannot import module `{decl.name}` (is a file)",
							    decl.pos
							)
					else:
						report.error(
						    f"cannot import module `{decl.name}` (not found)",
						    decl.pos
						)
				else:
					self.visit_decls(decl.decls)
				self.cur_sym = old_sym
			elif isinstance(decl, ast.ConstDecl):
				const_sym = sym.Const(decl.vis, decl.name, decl.typ, decl.expr)
				self.add_sym(const_sym, decl.pos)
				decl.sym = const_sym
			elif isinstance(decl, ast.StaticDecl):
				static_sym = sym.Static(
				    decl.vis, decl.is_mut, decl.is_extern, decl.name, decl.typ
				)
				self.add_sym(static_sym, decl.pos)
				decl.sym = static_sym
			elif isinstance(decl, ast.TypeDecl):
				self.add_sym(
				    sym.Type(
				        decl.vis, decl.name, sym.TypeKind.Alias,
				        info = sym.AliasInfo(decl.parent)
				    ), decl.pos
				)
			elif isinstance(decl, ast.ErrTypeDecl):
				self.add_sym(
				    sym.Type(
				        decl.vis, decl.name, sym.TypeKind.ErrType,
				        info = sym.ErrTypeInfo(self.errtype_nr)
				    ), decl.pos
				)
				self.errtype_nr += 1
			elif isinstance(decl, ast.TraitDecl):
				ts = sym.Type(
				    decl.vis, decl.name, sym.TypeKind.Trait,
				    info = sym.TraitInfo()
				)
				old_cur_sym = self.cur_sym
				self.cur_sym = ts
				self.visit_decls(decl.decls)
				self.cur_sym = old_cur_sym
				self.add_sym(ts, decl.pos)
			elif isinstance(decl, ast.UnionDecl):
				variants = []
				for v in decl.variants:
					if v in variants:
						report.error(
						    f"union `{decl.name}` has duplicate variant type `{v}`",
						    decl.pos
						)
					else:
						variants.append(v)
				decl.sym = sym.Type(
				    decl.vis, decl.name, sym.TypeKind.Union,
				    info = sym.UnionInfo(variants, decl.attrs.has("c_union"))
				)
				old_cur_sym = self.cur_sym
				self.cur_sym = decl.sym
				self.visit_decls(decl.decls)
				self.cur_sym = old_cur_sym
				self.add_sym(decl.sym, decl.pos)
			elif isinstance(decl, ast.StructDecl):
				decl.sym = sym.Type(
				    decl.vis, decl.name, sym.TypeKind.Struct, list(),
				    sym.StructInfo(decl.is_opaque)
				)
				old_cur_sym = self.cur_sym
				self.cur_sym = decl.sym
				self.visit_decls(decl.decls)
				self.cur_sym = old_cur_sym
				self.add_sym(decl.sym, decl.pos)
			elif isinstance(decl, ast.StructField):
				if self.cur_sym.has_field(decl.name):
					report.error(
					    f"field `{decl.name}` is already declared", decl.pos
					)
				else:
					self.cur_sym.fields.append(
					    sym.Field(
					        decl.name, decl.is_mut, decl.vis, decl.typ,
					        decl.has_def_expr, decl.def_expr
					    )
					)
			elif isinstance(decl, ast.EnumDecl):
				variants = []
				for v in decl.variants:
					if v in variants:
						report.error(
						    f"enum `{decl.name}` has duplicate variant `{v}`",
						    decl.pos
						)
					else:
						variants.append(v)
				decl.sym = sym.Type(
				    decl.vis, decl.name, sym.TypeKind.Enum, info = sym.EnumInfo(
				        decl.underlying_typ,
				        [sym.EnumVariant(v) for v in variants]
				    )
				)
				old_cur_sym = self.cur_sym
				self.cur_sym = decl.sym
				self.visit_decls(decl.decls)
				self.cur_sym = old_cur_sym
				self.add_sym(decl.sym, decl.pos)
			elif isinstance(decl, ast.ExtendDecl):
				old_sym = self.cur_sym
				if isinstance(decl.typ, type.Type):
					if decl.typ._unresolved:
						if isinstance(decl.typ.expr, ast.Ident):
							if s := self.cur_sym.find(decl.typ.expr.name):
								if s.kind == sym.TypeKind.Alias and (
								    isinstance(s.info.parent, type.Type)
								    and s.info.parent.is_resolved()
								):
									self.cur_sym = s.info.parent.sym
								else:
									self.cur_sym = s
							else:
								# placeholder
								self.cur_sym = sym.Type(
								    ast.Visibility.Private, decl.typ.expr.name,
								    sym.TypeKind.Placeholder
								)
								old_sym.add(self.cur_sym)
							self.visit_decls(decl.decls)
						else:
							report.error(
							    "cannot extend non-local types",
							    decl.typ.expr.pos
							)
					else:
						self.cur_sym = decl.typ.sym
						self.visit_decls(decl.decls)
				self.cur_sym = old_sym
			elif isinstance(decl, ast.DestructorDecl):
				self_typ = type.Ref(type.Type(self.cur_sym), True)
				decl.self_typ = self_typ
				decl.scope.add(sym.Object(True, "self", self_typ, True))
				sym_fn = sym.Fn(
				    sym.ABI.Rivet, ast.Visibility.Public, False, False, True,
				    False, "_dtor", [], self.comp.void_t, False, True, decl.pos,
				    True, True, []
				)
				sym_fn.rec_typ = self_typ
				self.add_sym(sym_fn, decl.pos)
			elif isinstance(decl, ast.FnDecl):
				decl.sym = sym.Fn(
				    decl.abi, decl.vis, decl.is_extern, decl.is_unsafe,
				    decl.is_method, decl.is_variadic, decl.name, decl.args,
				    decl.ret_typ, decl.has_named_args, decl.has_body,
				    decl.name_pos, decl.self_is_mut, decl.self_is_ref,
				    decl.type_arguments
				)
				if decl.is_generic:
					for type_arg in decl.type_arguments:
						try:
							decl.sym.add(
							    sym.Type(
							        ast.Visibility.Private, type_arg.name,
							        sym.TypeKind.TypeArg
							    )
							)
						except utils.CompilerError as e:
							report.error(e.args[0], type_arg.pos)
				decl.sym.is_main = decl.is_main
				if decl.is_method:
					self_typ = type.Type(self.cur_sym)
					if decl.self_is_ref:
						self_typ = type.Ref(self_typ, decl.self_is_mut)
					decl.self_typ = self_typ
					decl.sym.self_typ = self_typ
					decl.scope.add(sym.Object(False, "self", self_typ, True))
				self.add_sym(decl.sym, decl.name_pos)
				for arg in decl.args:
					try:
						decl.scope.add(
						    sym.Object(False, arg.name, arg.typ, True)
						)
					except utils.CompilerError as e:
						report.error(e.args[0], arg.pos)
