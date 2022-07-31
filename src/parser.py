# Copyright (C) 2022 The Rivet Team. All rights reserved.
# Use of this source code is governed by an MIT license
# that can be found in the LICENSE file.

from .token import Kind
from .lexer import Lexer
from .ast import sym, type
from . import report, token, ast, utils

class Parser:
	def __init__(self, comp):
		self.comp = comp
		self.lexer = None

		self.prev_tok = None
		self.tok = None
		self.peek_tok = None

		self.scope = None

		# This field is `true` when we are in a root module, that is,
		# a package.
		self.is_pkg_level = False

		self.inside_extern = False
		self.extern_is_trusted = False
		self.extern_abi = sym.ABI.Rivet
		self.inside_struct_decl = False
		self.inside_trait = False
		self.inside_block = False

	def parse_pkg(self):
		self.is_pkg_level = True
		return self.parse_module_files()

	def parse_module_files(self):
		source_files = []
		for input in self.comp.prefs.inputs:
			source_files.append(self.parse_file(input))
		return source_files

	def parse_extern_module_files(self, files):
		for file in files:
			self.comp.source_files.append(self.parse_file(file))

	def parse_file(self, file):
		self.lexer = Lexer.from_file(file)
		if report.ERRORS > 0:
			return ast.SourceFile(file, [], None)
		self.advance(2)
		return ast.SourceFile(file, self.parse_decls(), self.comp.mod_sym)

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
		kstr = str(kind)
		if token.is_key(kstr) or (len(kstr) > 0 and not kstr[0].isalpha()):
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
		self.scope = self.scope.parent

	def parse_abi(self):
		self.expect(Kind.Lparen)
		abi_pos = self.tok.pos
		abi = self.parse_name()
		self.expect(Kind.Rparen)
		if abi_f := sym.ABI.from_string(abi):
			return abi_f
		report.error(f"unknown ABI: `{abi}`", abi_pos)
		return sym.ABI.Rivet

	# ---- declarations --------------
	def parse_decls(self):
		decls = []
		if self.tok.kind == Kind.Hash and self.peek_tok.kind == Kind.Bang and self.is_pkg_level:
			self.comp.pkg_attrs = self.parse_attrs(True)
		while self.tok.kind != Kind.EOF:
			decls.append(self.parse_decl())
		return decls

	def parse_doc_comment(self):
		pos = self.tok.pos
		lines = []
		while self.accept(Kind.DocComment):
			lines.append(self.prev_tok.lit)
		return ast.DocComment(lines, pos)

	def parse_attrs(self, parse_pkg_attrs = False):
		attrs = ast.Attrs()
		while self.accept(Kind.Hash):
			if parse_pkg_attrs:
				self.expect(Kind.Bang)
			self.expect(Kind.Lbracket)
			while True:
				args = []
				pos = self.tok.pos
				attr_name = self.parse_name()
				if self.accept(Kind.Lparen):
					while True:
						if self.tok.kind == Kind.Name and self.peek_tok.kind == Kind.Colon:
							name = self.parse_name()
							self.expect(Kind.Colon)
						else:
							name = ""
						expr = self.parse_expr()
						args.append(ast.AttrArg(name, expr))
						if not self.accept(Kind.Comma):
							break
					self.expect(Kind.Rparen)
				attrs.add(ast.Attr(attr_name, args, pos))
				if not self.accept(Kind.Semicolon):
					break
			self.expect(Kind.Rbracket)
		return attrs

	def parse_vis(self):
		if self.accept(Kind.KeyPub):
			if self.accept(Kind.Lparen):
				self.expect(Kind.KeyPkg)
				self.expect(Kind.Rparen)
				return ast.Visibility.PublicInPkg
			return ast.Visibility.Public
		return ast.Visibility.Private

	def parse_comptime_if_decl(self):
		branches = []
		pos = self.tok.pos
		while self.tok.kind in (Kind.KeyIf, Kind.KeyElif, Kind.KeyElse):
			if self.accept(Kind.KeyElse):
				self.expect(Kind.Lbrace)
				decls = []
				while self.tok.kind != Kind.Rbrace:
					decls.append(self.parse_decl())
				self.expect(Kind.Rbrace)
				branches.append(
				    ast.ComptimeIfBranch(
				        self.empty_expr(), decls, True, Kind.KeyElse
				    )
				)
				break
			else:
				op = self.tok.kind
				self.next()
				self.expect(Kind.Lparen)
				cond = self.parse_expr()
				self.expect(Kind.Rparen)
				self.expect(Kind.Lbrace)
				decls = []
				while self.tok.kind != Kind.Rbrace:
					decls.append(self.parse_decl())
				self.expect(Kind.Rbrace)
				branches.append(ast.ComptimeIfBranch(cond, decls, False, op))
				if self.tok.kind not in (
				    Kind.Dollar, Kind.KeyElif, Kind.KeyElse
				):
					break
				self.expect(Kind.Dollar)
		return ast.ComptimeIfDecl(branches, pos)

	def parse_decl(self):
		doc_comment = self.parse_doc_comment()
		attrs = self.parse_attrs()
		vis = self.parse_vis()
		is_unsafe = self.accept(Kind.KeyUnsafe)
		pos = self.tok.pos
		if self.accept(Kind.Dollar):
			return self.parse_comptime_if_decl()
		elif self.accept(Kind.KeyUsing):
			path = self.parse_expr()
			if isinstance(path, ast.Ident):
				alias = path.name
			elif isinstance(path, ast.PkgExpr):
				alias = self.comp.prefs.pkg_name
			elif isinstance(path, ast.PathExpr):
				alias = path.field_name
			else:
				report.error("expected name or path", path.pos)
				alias = ""
			symbols = list()
			if self.accept(Kind.KeyAs):
				alias = self.parse_name()
			elif self.accept(Kind.Colon):
				while True:
					pos = self.tok.pos
					if self.accept(Kind.KeySelf):
						if self.accept(Kind.KeyAs):
							alias = self.parse_name()
						symbols.append(ast.UsingSymbol("", alias, True))
					else:
						name = self.parse_name()
						alias = name
						if self.accept(Kind.KeyAs):
							alias = self.parse_name()
						symbols.append(ast.UsingSymbol(name, alias, False, pos))
					if not self.accept(Kind.Comma):
						break
			self.expect(Kind.Semicolon)
			return ast.UsingDecl(attrs, vis, path, alias, symbols)
		elif self.accept(Kind.KeyExtern):
			if self.tok.kind == Kind.KeyPkg and not self.is_pkg_level:
				report.error(
				    "external packages can only be declared at the package level",
				    pos,
				)
			self.inside_extern = True
			if self.accept(Kind.KeyPkg):
				# extern package
				if vis.is_pub():
					report.error(
					    "`extern pkg` declarations cannot be declared public",
					    pos
					)
				elif is_unsafe:
					report.error(
					    "`extern pkg` declarations cannot be declared unsafe",
					    pos
					)
				extern_pkg = self.parse_name()
				self.expect(Kind.Semicolon)
				decl = ast.ExternPkg(extern_pkg, pos)
				self.comp.extern_packages.append(ast.ExternPkgInfo(extern_pkg))
			else:
				# extern function or static
				abi = self.parse_abi()
				protos = []
				if self.accept(Kind.Lbrace):
					if vis.is_pub():
						report.error(
						    "`extern` blocks cannot be declared public", pos
						)
					elif is_unsafe:
						report.error(
						    "`extern` blocks cannot be declared unsafe", pos
						)
					self.extern_abi = abi
					self.extern_is_trusted = attrs.has("trusted")
					while True:
						protos.append(self.parse_decl())
						if self.tok.kind == Kind.Rbrace:
							break
					self.expect(Kind.Rbrace)
				elif self.accept(Kind.KeyFn):
					protos.append(
					    self.parse_fn_decl(
					        doc_comment, attrs, vis, is_unsafe
					        or abi != sym.ABI.Rivet, abi
					    )
					)
				else:
					report.error("invalid external declaration", pos)
				decl = ast.ExternDecl(attrs, abi, protos, pos)
			self.inside_extern = False
			return decl
		elif self.accept(Kind.KeyConst):
			pos = self.tok.pos
			if is_unsafe:
				report.error("constants cannot be declared unsafe", pos)
			name = self.parse_name()
			self.expect(Kind.Colon)
			typ = self.parse_type()
			self.expect(Kind.Assign)
			expr = self.parse_expr()
			self.expect(Kind.Semicolon)
			return ast.ConstDecl(doc_comment, attrs, vis, name, typ, expr, pos)
		elif self.accept(Kind.KeyStatic):
			if is_unsafe:
				report.error(
				    "static values cannot be declared unsafe", self.tok.pos
				)
			return self.parse_static_decl(
			    doc_comment, attrs, vis, self.inside_extern
			)
		elif self.accept(Kind.KeyMod):
			pos = self.tok.pos
			if is_unsafe:
				report.error("modules cannot be declared unsafe", pos)
			name = self.parse_name()
			decls = []
			is_unloaded = self.accept(Kind.Semicolon)
			if not is_unloaded:
				old_is_pkg_level = self.is_pkg_level
				self.is_pkg_level = False

				self.expect(Kind.Lbrace)
				while not self.accept(Kind.Rbrace):
					decls.append(self.parse_decl())

				self.is_pkg_level = old_is_pkg_level
			return ast.ModDecl(
			    doc_comment, attrs, name, vis, decls, is_unloaded, pos
			)
		elif self.accept(Kind.KeyType):
			pos = self.tok.pos
			if is_unsafe:
				report.error("type aliases cannot be declared unsafe", pos)
			name = self.parse_name()
			self.expect(Kind.Assign)
			parent = self.parse_type()
			self.expect(Kind.Semicolon)
			return ast.TypeDecl(doc_comment, attrs, vis, name, parent, pos)
		elif self.accept(Kind.KeyErrType):
			pos = self.tok.pos
			if is_unsafe:
				report.error("error types cannot be declared unsafe", pos)
			name = self.parse_name()
			self.expect(Kind.Semicolon)
			return ast.ErrTypeDecl(doc_comment, attrs, vis, name, pos)
		elif self.accept(Kind.KeyTrait):
			pos = self.tok.pos
			if is_unsafe:
				report.error("traits cannot be declared unsafe", pos)
			name = self.parse_name()
			decls = []
			old_inside_trait = self.inside_trait
			self.inside_trait = True
			self.expect(Kind.Lbrace)
			while not self.accept(Kind.Rbrace):
				doc_comment = self.parse_doc_comment()
				attrs_pos = self.tok.pos
				attrs = self.parse_attrs()
				if attrs.has_attrs():
					report.error(
					    "attributes should be applied to a function or method",
					    attrs_pos
					)
				if self.accept(Kind.KeyPub):
					report.error(
					    "unnecessary visibility qualifier", self.prev_tok.pos
					)
				is_unsafe = self.accept(Kind.KeyUnsafe)
				self.expect(Kind.KeyFn)
				decls.append(
				    self.parse_fn_decl(
				        doc_comment, attrs, ast.Visibility.Public, is_unsafe,
				        sym.ABI.Rivet
				    )
				)
			self.inside_trait = old_inside_trait
			return ast.TraitDecl(doc_comment, attrs, vis, name, decls, pos)
		elif self.accept(Kind.KeyUnion):
			pos = self.tok.pos
			if is_unsafe:
				report.error("unions cannot be declared unsafe", pos)
			name = self.parse_name()
			self.expect(Kind.Lbrace)
			variants = []
			decls = []
			while True:
				variants.append(self.parse_type())
				if not self.accept(Kind.Comma):
					break
			if self.accept(Kind.Semicolon):
				# declarations: methods, consts, etc.
				while self.tok.kind != Kind.Rbrace:
					decls.append(self.parse_decl())
			self.expect(Kind.Rbrace)
			return ast.UnionDecl(
			    doc_comment, attrs, vis, name, variants, decls, pos
			)
		elif self.accept(Kind.KeyStruct):
			old_inside_struct_decl = self.inside_struct_decl
			self.inside_struct_decl = True
			pos = self.tok.pos
			if is_unsafe:
				report.error("structs cannot be declared unsafe", pos)
			name = self.parse_name()
			is_opaque = self.accept(Kind.Semicolon)
			decls = []
			if not is_opaque:
				self.expect(Kind.Lbrace)
				if self.tok.kind != Kind.Rbrace:
					while self.tok.kind != Kind.Rbrace:
						if self.accept(Kind.BitNot):
							# destructor
							pos = self.prev_tok.pos
							self.expect(Kind.KeySelf)
							self.expect(Kind.Lbrace)
							self.open_scope()
							sc = self.scope
							stmts = []
							while not self.accept(Kind.Rbrace):
								stmts.append(self.parse_stmt())
							self.close_scope()
							decls.append(ast.DestructorDecl(sc, stmts, pos))
						else:
							# declaration: methods, consts, etc.
							decls.append(self.parse_decl())
				self.expect(Kind.Rbrace)
			self.inside_struct_decl = old_inside_struct_decl
			return ast.StructDecl(
			    doc_comment, attrs, vis, name, decls, is_opaque, pos
			)
		elif self.inside_struct_decl and self.tok.kind in (
		    Kind.KeyMut, Kind.Name
		):
			# struct fields
			is_mut = self.accept(Kind.KeyMut)
			name = self.parse_name()
			self.expect(Kind.Colon)
			typ = self.parse_type()
			has_def_expr = self.accept(Kind.Assign)
			def_expr = None
			if has_def_expr:
				def_expr = self.parse_expr()
			self.expect(Kind.Semicolon)
			return ast.StructField(
			    attrs, doc_comment, vis, is_mut, name, typ, def_expr,
			    has_def_expr, pos
			)
		elif self.accept(Kind.KeyEnum):
			pos = self.tok.pos
			if is_unsafe:
				report.error("enums cannot be declared unsafe", pos)
			name = self.parse_name()
			underlying_typ = self.comp.int32_t
			if self.accept(Kind.Colon):
				underlying_typ = self.parse_type()
			self.expect(Kind.Lbrace)
			variants = []
			decls = []
			while True:
				variants.append(self.parse_name())
				if not self.accept(Kind.Comma):
					break
			if self.accept(Kind.Semicolon):
				# declarations: methods, consts, etc.
				while self.tok.kind != Kind.Rbrace:
					decls.append(self.parse_decl())
			self.expect(Kind.Rbrace)
			return ast.EnumDecl(
			    doc_comment, attrs, vis, name, underlying_typ, variants, decls,
			    pos
			)
		elif self.accept(Kind.KeyExtend):
			pos = self.prev_tok.pos
			if is_unsafe:
				report.error("`extend`s cannot be unsafe", pos)
			typ = self.parse_type()
			is_for_trait = self.accept(Kind.KeyFor)
			if is_for_trait:
				for_trait = self.parse_type()
			else:
				for_trait = None
			decls = []
			self.expect(Kind.Lbrace)
			while not self.accept(Kind.Rbrace):
				decl = self.parse_decl()
				if not isinstance(decl, ast.FnDecl):
					report.error(
					    "expected associated function or method", decl.pos
					)
				decls.append(decl)
			return ast.ExtendDecl(
			    attrs, typ, is_for_trait, for_trait, decls, pos
			)
		elif self.accept(Kind.KeyFn):
			return self.parse_fn_decl(
			    doc_comment, attrs, vis, not self.extern_is_trusted and (
			        is_unsafe or
			        (self.inside_extern and self.extern_abi != sym.ABI.Rivet)
			    ), self.extern_abi if self.inside_extern else sym.ABI.Rivet
			)
		elif self.accept(Kind.KeyTest):
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

	def parse_static_decl(self, doc_comment, attrs, vis, is_extern):
		pos = self.tok.pos
		is_mut = self.accept(Kind.KeyMut)
		name = self.parse_name()
		self.expect(Kind.Colon)
		typ = self.parse_type()
		if is_extern:
			expr = self.empty_expr()
		else:
			self.expect(Kind.Assign)
			expr = self.parse_expr()
		self.expect(Kind.Semicolon)
		return ast.StaticDecl(
		    doc_comment, attrs, vis, is_extern, is_mut, name, typ, expr, pos
		)

	def parse_fn_decl(self, doc_comment, attrs, vis, is_unsafe, abi):
		pos = self.tok.pos
		if self.tok.kind.is_overloadable_op():
			name = str(self.tok.kind)
			self.next()
		else:
			name = self.parse_name()

		args = []
		is_method = False
		is_variadic = False
		self_is_ref = False
		self_is_mut = False
		has_named_args = False

		# parse type-arguments
		g_idx = 0
		type_arguments = []
		if self.accept(Kind.Lt):
			while True:
				generic_pos = self.tok.pos
				generic_name = self.parse_name()
				type_arguments.append(
				    type.Generic(generic_name, g_idx, generic_pos)
				)
				g_idx += 1
				if not self.accept(Kind.Comma):
					break
			self.expect(Kind.Gt)

		self.open_scope()
		sc = self.scope
		self.expect(Kind.Lparen)
		if self.tok.kind != Kind.Rparen:
			# receiver (`self`|`&self`|`&mut self`)
			if self.tok.kind == Kind.KeySelf or (
			    self.tok.kind == Kind.Amp and self.peek_tok.kind == Kind.KeySelf
			) or (
			    self.tok.kind == Kind.Amp and self.peek_tok.kind == Kind.KeyMut
			    and self.peek_token(2).kind == Kind.KeySelf
			):
				is_method = True
				self_is_ref = self.accept(Kind.Amp)
				self_is_mut = self.accept(Kind.KeyMut)
				self.expect(Kind.KeySelf)
				if self.tok.kind != Kind.Rparen:
					self.expect(Kind.Comma)
			# arguments
			while self.tok.kind != Kind.Rparen:
				if self.inside_extern and self.accept(Kind.Ellipsis):
					is_variadic = True
					break
				else:
					arg_pos = self.tok.pos
					arg_name = self.parse_name()
					self.expect(Kind.Colon)
					arg_typ = self.parse_type()
					is_variadic = isinstance(arg_typ, type.Variadic)
					arg_expr = self.empty_expr()
					if self.accept(Kind.Assign):
						has_named_args = True
						arg_expr = self.parse_expr()
					args.append(
					    sym.Arg(
					        arg_name, arg_typ, arg_expr,
					        not isinstance(arg_expr, ast.EmptyExpr), arg_pos
					    )
					)
				if not self.accept(Kind.Comma):
					break
		self.expect(Kind.Rparen)

		ret_typ = self.comp.void_t
		is_result = self.accept(Kind.Bang)
		if self.tok.kind not in (Kind.Lbrace, Kind.Semicolon):
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
		return ast.FnDecl(
		    doc_comment, attrs, vis, self.inside_extern, is_unsafe, name, pos,
		    args, ret_typ, stmts, sc, has_body, is_method, self_is_ref,
		    self_is_mut, has_named_args, self.is_pkg_level and name == "main",
		    is_variadic, abi, type_arguments
		)

	# ---- statements --------------------------
	def parse_stmt(self):
		if self.accept(Kind.KeyLet):
			# variable declarations
			pos = self.prev_tok.pos
			lefts = []
			if self.accept(Kind.Lparen):
				# multiple variables
				while True:
					lefts.append(self.parse_var_decl())
					if not self.accept(Kind.Comma):
						break
				self.expect(Kind.Rparen)
			else:
				lefts.append(self.parse_var_decl())
			self.expect(Kind.Assign)
			right = self.parse_expr()
			self.expect(Kind.Semicolon)
			return ast.LetStmt(self.scope, lefts, right, pos)
		elif self.tok.kind == Kind.Name and self.peek_tok.kind == Kind.Colon:
			pos = self.tok.pos
			label = self.parse_name()
			self.expect(Kind.Colon)
			return ast.LabelStmt(label, pos)
		elif self.accept(Kind.KeyWhile):
			pos = self.prev_tok.pos
			is_inf = False
			if self.accept(Kind.Lparen):
				if self.tok.kind == Kind.KeyLet:
					self.open_scope()
					cond = self.parse_guard_expr()
				else:
					cond = self.parse_expr()
				self.expect(Kind.Rparen)
			else:
				cond = ast.BoolLiteral(True, self.tok.pos)
				is_inf = True
			stmt = self.parse_stmt()
			if isinstance(cond, ast.GuardExpr):
				self.close_scope()
			return ast.WhileStmt(cond, stmt, is_inf, pos)
		elif self.accept(Kind.KeyFor):
			pos = self.prev_tok.pos
			self.expect(Kind.Lparen)
			self.open_scope()
			sc = self.scope
			vars = []
			# single or multiple variables
			while True:
				vars.append(self.parse_name())
				if not self.accept(Kind.Comma):
					break
			self.expect(Kind.KeyIn)
			iterable = self.parse_expr()
			if self.accept(Kind.DotDot): # range
				is_inclusive = self.accept(Kind.Assign)
				max = self.parse_expr()
				iterable = ast.RangeExpr(
				    iterable, max, is_inclusive, iterable.pos
				)
			self.expect(Kind.Rparen)
			stmt = self.parse_stmt()
			self.close_scope()
			return ast.ForInStmt(sc, vars, iterable, stmt, pos)
		elif self.accept(Kind.KeyGoto):
			pos = self.tok.pos
			label = self.parse_name()
			self.expect(Kind.Semicolon)
			return ast.GotoStmt(label, pos)

		expr = self.parse_expr()
		if self.tok.kind.is_assign():
			# assignment
			op = self.tok.kind
			self.next()
			right = self.parse_expr()
			self.expect(Kind.Semicolon)
			return ast.AssignStmt(expr, op, right, expr.pos)
		elif not ((self.inside_block and self.tok.kind == Kind.Rbrace)
		          or expr.__class__ in (ast.IfExpr, ast.MatchExpr, ast.Block)):
			self.expect(Kind.Semicolon)
		return ast.ExprStmt(expr, expr.pos)

	def parse_var_decl(self, support_ref = False, support_typ = True):
		is_ref = support_ref and self.accept(Kind.Amp)
		is_mut = self.accept(Kind.KeyMut)
		pos = self.tok.pos
		name = self.parse_name()
		has_typ = False
		typ = self.comp.void_t
		if support_typ and self.accept(Kind.Colon):
			typ = self.parse_type()
			has_typ = True
		return ast.VarDecl(is_mut, is_ref, name, has_typ, typ, pos)

	# ---- expressions -------------------------
	def parse_expr(self):
		return self.parse_or_expr()

	def parse_or_expr(self):
		left = self.parse_and_expr()
		while self.accept(Kind.KeyOr):
			right = self.parse_and_expr()
			left = ast.BinaryExpr(left, Kind.KeyOr, right, left.pos)
		return left

	def parse_and_expr(self):
		left = self.parse_equality_expr()
		while self.accept(Kind.KeyAnd):
			right = self.parse_equality_expr()
			left = ast.BinaryExpr(left, Kind.KeyAnd, right, left.pos)
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
			    Kind.Gt, Kind.Lt, Kind.Ge, Kind.Le, Kind.KeyOrElse
			]:
				op = self.tok.kind
				self.next()
				right = self.parse_shift_expr()
				left = ast.BinaryExpr(left, op, right, left.pos)
			elif self.tok.kind in [Kind.KeyIs, Kind.KeyNotIs]:
				op = self.tok.kind
				self.next()
				pos = self.tok.pos
				right = ast.TypeNode(self.parse_type(), pos)
				left = ast.BinaryExpr(left, op, right, left.pos)
			else:
				break
		return left

	def parse_shift_expr(self):
		left = self.parse_additive_expr()
		while True:
			if self.tok.kind in [Kind.Lt, Kind.Gt]:
				op = Kind.Lshift if self.tok.kind == Kind.Lt else Kind.Rshift
				if self.tok.pos.pos + 1 == self.peek_tok.pos.pos:
					self.next()
					self.next()
					right = self.parse_additive_expr()
					left = ast.BinaryExpr(left, op, right, left.pos)
				else:
					break
			elif self.tok.kind in [Kind.Amp, Kind.Pipe, Kind.Xor]:
				op = self.tok.kind
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
			if self.tok.kind in [Kind.Mult, Kind.Div, Kind.Mod]:
				op = self.tok.kind
				self.next()
				right = self.parse_unary_expr()
				left = ast.BinaryExpr(left, op, right, left.pos)
			else:
				break
		return left

	def parse_unary_expr(self):
		expr = self.empty_expr()
		if (self.tok.kind in [Kind.Amp, Kind.Bang, Kind.BitNot, Kind.Minus]):
			op = self.tok.kind
			pos = self.tok.pos
			self.next()
			is_ref_mut = op == Kind.Amp and self.accept(Kind.KeyMut)
			right = self.parse_unary_expr()
			expr = ast.UnaryExpr(right, op, is_ref_mut, pos)
		else:
			expr = self.parse_primary_expr()
		return expr

	def parse_primary_expr(self):
		expr = self.empty_expr()
		if self.tok.kind in [
		    Kind.KeyTrue, Kind.KeyFalse, Kind.Char, Kind.Number, Kind.String,
		    Kind.KeyNone, Kind.KeySelf, Kind.KeySuper, Kind.KeySelfTy
		]:
			expr = self.parse_literal()
		elif self.accept(Kind.Dollar):
			# comptime expressions
			if self.tok.kind == Kind.KeyIf:
				expr = self.parse_if_expr(True)
			else:
				expr = self.parse_ident(True)
		elif self.tok.kind == Kind.Dot and self.peek_tok.kind == Kind.Name:
			pos = self.tok.pos
			self.next()
			expr = ast.EnumVariantExpr(self.parse_name(), pos)
		elif self.accept(Kind.DoubleColon):
			pos = self.prev_tok.pos
			field_pos = self.tok.pos
			field_name = self.parse_name()
			expr = ast.PathExpr(True, None, field_name, pos, field_pos)
		elif self.tok.kind in (Kind.KeyContinue, Kind.KeyBreak):
			op = self.tok.kind
			pos = self.tok.pos
			self.next()
			expr = ast.BranchExpr(op, pos)
		elif self.accept(Kind.KeyReturn):
			pos = self.prev_tok.pos
			has_expr = self.tok.kind not in (
			    Kind.Comma, Kind.Semicolon, Kind.Rbrace
			)
			if has_expr:
				expr = self.parse_expr()
			else:
				expr = self.empty_expr()
			expr = ast.ReturnExpr(expr, has_expr, pos)
		elif self.accept(Kind.KeyRaise):
			pos = self.prev_tok.pos
			expr = self.parse_expr()
			expr = ast.RaiseExpr(expr, pos)
		elif self.tok.kind == Kind.KeyIf:
			expr = self.parse_if_expr(False)
		elif self.accept(Kind.KeyMatch):
			expr = self.parse_match_expr()
		elif self.accept(Kind.Lparen):
			pos = self.prev_tok.pos
			if self.accept(Kind.Rparen):
				expr = self.empty_expr()
			else:
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
		elif self.tok.kind in (Kind.KeyUnsafe, Kind.Lbrace):
			# block expression
			pos = self.tok.pos
			is_unsafe = self.accept(Kind.KeyUnsafe)
			self.expect(Kind.Lbrace)
			old_inside_block = self.inside_block
			self.inside_block = True
			stmts = []
			has_expr = False
			self.open_scope()
			sc = self.scope
			while not self.accept(Kind.Rbrace):
				stmt = self.parse_stmt()
				has_expr = isinstance(
				    stmt, ast.ExprStmt
				) and self.prev_tok.kind != Kind.Semicolon
				stmts.append(stmt)
			self.close_scope()
			if has_expr:
				expr = ast.Block(
				    sc, is_unsafe, stmts[:-1], stmts[-1].expr, True, pos
				)
			else:
				expr = ast.Block(sc, is_unsafe, stmts, None, False, pos)
			self.inside_block = old_inside_block
		elif self.accept(Kind.KeyAs):
			self.expect(Kind.Lparen)
			typ = self.parse_type()
			self.expect(Kind.Comma)
			expr = self.parse_expr()
			self.expect(Kind.Rparen)
			expr = ast.CastExpr(expr, typ, expr.pos)
		elif self.tok.kind == Kind.Lbracket:
			elems = []
			pos = self.tok.pos
			self.next()
			if self.tok.kind != Kind.Rbracket:
				while True:
					elems.append(self.parse_expr())
					if not self.accept(Kind.Comma):
						break
			self.expect(Kind.Rbracket)
			expr = ast.ArrayLiteral(elems, pos)
		elif self.tok.kind == Kind.KeyPkg:
			expr = self.parse_pkg_expr()
		elif self.tok.kind == Kind.Name and self.peek_tok.kind == Kind.Char:
			if self.tok.lit != "b":
				report.error(
				    "only `b` is recognized as a valid prefix for a character literal",
				    self.tok.pos,
				)
				self.next()
			else:
				expr = self.parse_character_literal()
		elif self.tok.kind == Kind.Name and self.peek_tok.kind == Kind.String:
			if self.tok.lit not in ("c", "b", "r"):
				report.error(
				    "only `c`, `b` and `r` are recognized as valid prefixes for a string literal",
				    self.tok.pos,
				)
				self.next()
			else:
				expr = self.parse_string_literal()
		elif self.tok.kind == Kind.Name and self.peek_tok.kind == Kind.Bang: # builtin call
			name = self.parse_name()
			self.expect(Kind.Bang)
			self.expect(Kind.Lparen)
			args = []
			if name in ("size_of", "align_of"):
				pos = self.tok.pos
				args.append(ast.TypeNode(self.parse_type(), pos))
			elif self.tok.kind != Kind.Rparen:
				while True:
					args.append(self.parse_expr())
					if not self.accept(Kind.Comma):
						break
			self.expect(Kind.Rparen)
			expr = ast.BuiltinCallExpr(name, args, expr.pos)
		else:
			expr = self.parse_ident()

		while True:
			if self.accept(Kind.Lbrace):
				fields = []
				if self.tok.kind != Kind.Rbrace:
					while True:
						fpos = self.tok.pos
						name = self.parse_name()
						self.expect(Kind.Colon)
						value = self.parse_expr()
						fields.append(ast.StructLiteralField(name, value, fpos))
						if not self.accept(Kind.Comma):
							break
				self.expect(Kind.Rbrace)
				expr = ast.StructLiteral(expr, fields, expr.pos)
			elif self.tok.kind in [Kind.Inc, Kind.Dec]:
				op = self.tok.kind
				self.next()
				expr = ast.PostfixExpr(expr, op, expr.pos)
			elif self.accept(Kind.Lparen):
				args = []
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
				if self.tok.kind == Kind.Dot and self.peek_tok.kind == Kind.Bang:
					# check result value, if error propagate
					err_handler_pos = self.peek_tok.pos
					self.advance(2)
					is_propagate = True
				elif self.accept(Kind.KeyCatch):
					if self.accept(Kind.Pipe):
						varname_pos = self.tok.pos
						varname = self.parse_name()
						self.expect(Kind.Pipe)
					err_expr = self.parse_expr()
					has_err_expr = True
				expr = ast.CallExpr(
				    expr, args,
				    ast.CallErrorHandler(
				        is_propagate, varname, err_expr, has_err_expr,
				        varname_pos, self.scope, err_handler_pos
				    ), expr.pos
				)
			elif self.accept(Kind.Lbracket):
				is_mut = self.accept(Kind.KeyMut)
				index = self.empty_expr()
				if self.accept(Kind.DotDot):
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
					if self.accept(Kind.DotDot):
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
				if is_mut and not isinstance(index, ast.RangeExpr):
					report.error(
					    "only slices can be marked as mutable", expr.pos
					)
				expr = ast.IndexExpr(expr, index, is_mut, expr.pos)
			elif self.accept(Kind.Dot):
				if self.accept(Kind.Mult):
					expr = ast.SelectorExpr(
					    expr, "", expr.pos, self.prev_tok.pos,
					    is_indirect = True
					)
				elif self.accept(Kind.Question):
					# check optional value, if none panic
					expr = ast.SelectorExpr(
					    expr, "", expr.pos, self.prev_tok.pos,
					    is_nonecheck = True
					)
				else:
					field_pos = self.tok.pos
					if self.tok.kind == Kind.Number:
						name = self.tok.lit
						self.next()
					elif self.tok.kind.is_overloadable_op():
						name = str(self.tok.kind)
						self.next()
					else:
						name = self.parse_name()
					expr = ast.SelectorExpr(expr, name, expr.pos, field_pos)
			elif self.tok.kind == Kind.DoubleColon:
				expr = self.parse_path_expr(expr)
			else:
				break
		return expr

	def parse_if_expr(self, is_comptime):
		branches = []
		has_else = False
		pos = self.tok.pos
		while self.tok.kind in (Kind.KeyIf, Kind.KeyElif, Kind.KeyElse):
			if self.accept(Kind.KeyElse):
				branches.append(
				    ast.IfBranch(
				        is_comptime, self.empty_expr(), self.parse_expr(), True,
				        Kind.KeyElse
				    )
				)
				has_else = True
				break
			else:
				op = self.tok.kind
				self.next()
				self.expect(Kind.Lparen)
				if self.tok.kind == Kind.KeyLet:
					self.open_scope()
					cond = self.parse_guard_expr()
				else:
					cond = self.parse_expr()
				self.expect(Kind.Rparen)
				branches.append(
				    ast.IfBranch(
				        is_comptime, cond, self.parse_expr(), False, op
				    )
				)
				if isinstance(cond, ast.GuardExpr):
					self.close_scope()
				if self.tok.kind not in (
				    Kind.Dollar, Kind.KeyElif, Kind.KeyElse
				):
					break
				if is_comptime:
					self.expect(Kind.Dollar)
		return ast.IfExpr(is_comptime, branches, has_else, pos)

	def parse_match_expr(self):
		branches = []
		pos = self.prev_tok.pos
		is_typematch = False
		if self.accept(Kind.Lparen):
			if self.tok.kind == Kind.KeyLet:
				self.open_scope()
				expr = self.parse_guard_expr()
			else:
				expr = self.parse_expr()
			self.expect(Kind.Rparen)
			is_typematch = self.accept(Kind.KeyIs)
		else:
			expr = ast.BoolLiteral(True, pos)
		self.expect(Kind.Lbrace)
		while True:
			pats = []
			has_var = False
			var_is_ref = False
			var_is_mut = False
			var_name = ""
			is_else = self.accept(Kind.KeyElse)
			if not is_else:
				while True:
					if is_typematch:
						pos = self.tok.pos
						pats.append(ast.TypeNode(self.parse_type(), pos))
						if is_typematch and len(pats) == 1 and self.accept(
						    Kind.KeyAs
						):
							var_is_ref = self.accept(Kind.Amp)
							var_is_mut = var_is_ref and self.accept(Kind.KeyMut)
							var_name = self.parse_name()
							has_var = True
					else:
						pats.append(self.parse_expr())
					if not self.accept(Kind.Comma):
						break
			self.expect(Kind.Arrow)
			branches.append(
			    ast.MatchBranch(
			        pats, has_var, var_is_ref, var_is_mut, var_name,
			        self.parse_expr(), is_else
			    )
			)
			if not self.accept(Kind.Comma):
				break
		self.expect(Kind.Rbrace)
		if isinstance(expr, ast.GuardExpr): self.close_scope()
		return ast.MatchExpr(expr, branches, is_typematch, self.scope, pos)

	def parse_guard_expr(self):
		self.expect(Kind.KeyLet)
		pos = self.prev_tok.pos
		vars = []
		while True:
			vars.append(self.parse_name())
			if not self.accept(Kind.Comma):
				break
		self.expect(Kind.Assign)
		e = self.parse_expr()
		if self.accept(Kind.Semicolon):
			has_cond = True
			cond = self.parse_expr()
		else:
			has_cond = False
			cond = self.empty_expr()
		return ast.GuardExpr(vars, e, has_cond, cond, self.scope, pos)

	def parse_path_expr(self, left):
		self.expect(Kind.DoubleColon)
		pos = self.tok.pos
		name = self.parse_name()
		expr = ast.PathExpr(False, left, name, left.pos, pos)
		expr.is_last = self.tok.kind != Kind.DoubleColon
		return expr

	def parse_literal(self):
		if self.tok.kind in [Kind.KeyTrue, Kind.KeyFalse]:
			pos = self.tok.pos
			lit = self.tok.kind == Kind.KeyTrue
			self.next()
			return ast.BoolLiteral(lit, pos)
		elif self.tok.kind == Kind.Char:
			return self.parse_character_literal()
		elif self.tok.kind == Kind.Number:
			return self.parse_integer_literal()
		elif self.tok.kind == Kind.String:
			return self.parse_string_literal()
		elif self.accept(Kind.KeySelf):
			return ast.SelfExpr(self.scope, self.prev_tok.pos)
		elif self.accept(Kind.KeySuper):
			return ast.SuperExpr(self.scope, self.prev_tok.pos)
		elif self.accept(Kind.KeyNone):
			return ast.NoneLiteral(self.prev_tok.pos)
		elif self.accept(Kind.KeySelfTy):
			return ast.SelfTyExpr(self.scope, self.prev_tok.pos)
		else:
			report.error(f"expected literal, found {self.tok}", self.tok.pos)
		return self.empty_expr()

	def parse_integer_literal(self):
		pos = self.tok.pos
		lit = self.tok.lit
		node = ast.FloatLiteral(lit, pos) if lit[:2] not in [
		    '0x', '0o', '0b'
		] and utils.index_any(lit,
		                      ".eE") >= 0 else ast.IntegerLiteral(lit, pos)
		self.next()
		return node

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
		type_args = list()
		if self.tok.kind == Kind.DoubleColon and self.peek_tok.kind == Kind.Lt:
			self.advance(2)
			while True:
				type_args.append(self.parse_type())
				if not self.accept(Kind.Comma):
					break
			self.expect(Kind.Gt)
		sc = self.scope
		if sc == None:
			sc = sym.Scope(sc)
		return ast.Ident(name, pos, sc, is_comptime, type_args)

	def parse_pkg_expr(self):
		pos = self.tok.pos
		self.next()
		return ast.PkgExpr(pos)

	def parse_super_expr(self):
		self.next()
		return ast.SuperExpr(self.scope, self.prev_tok.pos)

	def empty_expr(self):
		return ast.EmptyExpr(self.tok.pos)

	# ---- types -------------------------------
	def parse_type(self):
		pos = self.tok.pos
		if self.accept(Kind.Question):
			# optional
			typ = self.parse_type()
			if isinstance(typ, type.Ptr):
				report.error("pointers cannot be optional", pos)
				report.note("by default pointers can contain the value `none`")
			elif isinstance(typ, type.Optional):
				report.error("optional multi-level types are not allowed", pos)
			return type.Optional(typ)
		elif self.tok.kind in (Kind.KeyUnsafe, Kind.KeyExtern, Kind.KeyFn):
			# function types
			is_unsafe = self.accept(Kind.KeyUnsafe)
			is_extern = self.accept(Kind.KeyExtern)
			abi = self.parse_abi() if is_extern else sym.ABI.Rivet
			if is_extern and not self.inside_extern: self.inside_extern = True
			args = []
			is_variadic = False
			self.expect(Kind.KeyFn)
			self.expect(Kind.Lparen)
			if self.tok.kind != Kind.Rparen:
				while True:
					if is_extern and self.accept(Kind.Ellipsis):
						is_variadic = True
						break
					args.append(self.parse_type())
					if not self.accept(Kind.Comma): break
			self.expect(Kind.Rparen)
			ret_typ = self.comp.void_t
			if self.tok.kind.is_start_of_type():
				ret_typ = self.parse_type()
			if is_extern and self.inside_extern:
				self.inside_extern = False
			return type.Fn(
			    is_unsafe, is_extern, abi, False, args, is_variadic, ret_typ,
			    False, False
			)
		elif self.accept(Kind.Amp):
			# references
			is_mut = self.accept(Kind.KeyMut)
			typ = self.parse_type()
			if self.inside_extern:
				k = "mut " if is_mut else "const "
				report.error(
				    "cannot use references inside `extern` blocks", pos
				)
				report.help(f"use pointers instead: `*{k}{typ}`")
			elif isinstance(typ, type.Ref):
				report.error("multi-level references are not allowed", pos)
			elif typ == self.comp.void_t:
				k = "mut " if is_mut else "const "
				report.error("invalid use of `void` type", pos)
				report.help("use `*{} void` instead")
			return type.Ref(typ, is_mut)
		elif self.accept(Kind.Mult):
			# pointers
			is_mut = self.accept(Kind.KeyMut)
			typ = self.parse_type()
			if isinstance(typ, type.Ref):
				report.error("cannot use pointers with references", pos)
			return type.Ptr(typ, is_mut)
		elif self.accept(Kind.Lbracket):
			# arrays or slices
			mut_pos = self.tok.pos
			is_mut = self.accept(Kind.KeyMut)
			typ = self.parse_type()
			if self.accept(Kind.Semicolon):
				if is_mut:
					report.error(
					    "the element type of an array cannot be declared mutable",
					    mut_pos
					)
					report.note("this is only valid with slices")
				size = self.parse_expr()
				self.expect(Kind.Rbracket)
				return type.Array(typ, size)
			self.expect(Kind.Rbracket)
			return type.Slice(typ, is_mut)
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
		elif self.accept(Kind.KeySelfTy):
			return type.Type.unresolved(
			    ast.SelfTyExpr(self.scope, self.prev_tok.pos)
			)
		elif (self.comp.prefs.pkg_name == "core"
		      or self.comp.pkg_sym.is_core) and self.accept(Kind.KeyNone):
			return self.comp.none_t
		elif self.tok.kind in (Kind.KeyPkg, Kind.KeySuper, Kind.Name):
			# normal type
			if self.peek_tok.kind == Kind.DoubleColon:
				path_expr = self.parse_path_expr(
				    self.parse_pkg_expr() if self.tok.kind ==
				    Kind.KeyPkg else self.parse_super_expr() if self.tok.kind ==
				    Kind.KeySuper else self.parse_ident()
				)
				if self.tok.kind == Kind.DoubleColon:
					while True:
						path_expr = self.parse_path_expr(path_expr)
						if self.tok.kind != Kind.DoubleColon:
							break
				return type.Type.unresolved(path_expr)
			elif self.tok.kind == Kind.Name:
				prev_tok_kind = self.prev_tok.kind
				expr = self.parse_ident()
				lit = expr.name
				if lit == "void":
					if prev_tok_kind not in (Kind.Mult, Kind.KeyMut, Kind.Amp):
						# valid only as pointer
						report.error("invalid use of `void` type", pos)
					return self.comp.void_t
				elif lit == "no_return":
					if prev_tok_kind != Kind.Rparen and self.tok.kind != Kind.Lbrace:
						report.error("invalid use of `no_return` type", pos)
					return self.comp.no_return_t
				elif lit == "bool":
					return self.comp.bool_t
				elif lit == "rune":
					return self.comp.rune_t
				elif lit == "i8":
					return self.comp.int8_t
				elif lit == "i16":
					return self.comp.int16_t
				elif lit == "i32":
					return self.comp.int32_t
				elif lit == "i64":
					return self.comp.int64_t
				elif lit == "isize":
					return self.comp.isize_t
				elif lit == "u8":
					return self.comp.uint8_t
				elif lit == "u16":
					return self.comp.uint16_t
				elif lit == "u32":
					return self.comp.uint32_t
				elif lit == "u64":
					return self.comp.uint64_t
				elif lit == "usize":
					return self.comp.usize_t
				elif lit == "f32":
					return self.comp.float32_t
				elif lit == "f64":
					return self.comp.float64_t
				elif lit == "str":
					return self.comp.str_t
				elif lit == "untyped_int" and (
				    self.comp.prefs.pkg_name == "core"
				    or self.comp.pkg_sym.is_core
				):
					return self.comp.untyped_int_t
				elif lit == "untyped_float" and (
				    self.comp.prefs.pkg_name == "core"
				    or self.comp.pkg_sym.is_core
				):
					return self.comp.untyped_float_t
				elif lit == "error" and (
				    self.comp.prefs.pkg_name == "core"
				    or self.comp.pkg_sym.is_core
				):
					return self.comp.error_t
				else:
					return type.Type.unresolved(expr)
			else:
				report.error("expected type, found keyword `pkg`", pos)
				self.next()
		else:
			report.error(f"expected type, found {self.tok}", pos)
			self.next()
		return type.Type.unresolved(self.empty_expr())
