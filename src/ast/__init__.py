# Copyright (C) 2022 The Rivet Team. All rights reserved.
# Use of this source code is governed by an MIT license
# that can be found in the LICENSE file.

from enum import IntEnum as Enum, auto as auto_enum

COMPTIME_CONSTANTS = [
    "_FILE_", "_LINE_", "_COLUMN_", "_FUNCTION_", "_RIVET_VERSION_",
    "_RIVET_COMMIT_"
]

def is_comptime_constant(name):
	return name in COMPTIME_CONSTANTS

class ExternPkgInfo:
	def __init__(self, name, deps = list()):
		self.name = name
		self.deps = deps

	def add_dep(self, dep):
		self.deps.append(dep)

class SourceFile:
	def __init__(self, file, decls, mod_sym):
		self.file = file
		self.mod_sym = mod_sym
		self.decls = decls
		self.imported_symbols = {}

	def find_imported_symbol(self, name):
		if name in self.imported_symbols:
			return self.imported_symbols[name]
		return None

class Visibility(Enum):
	Private = auto_enum()
	Public = auto_enum() # Public outside current module
	PublicInPkg = auto_enum() # Public inside current package

	def is_pub(self):
		return self != Visibility.Private

	def __repr__(self):
		if self == Visibility.Public:
			return "pub"
		elif self == Visibility.PublicInPkg:
			return "pub(pkg)"
		return "" # private

	def __str__(self):
		return self.__repr__()

# Used in `let` stmts and guard exprs
class VarDecl:
	def __init__(self, is_mut, is_ref, name, has_typ, typ, pos):
		self.is_mut = is_mut
		self.is_ref = is_ref
		self.name = name
		self.has_typ = has_typ
		self.typ = typ
		self.pos = pos

	def __repr__(self):
		res = ""
		if self.is_mut:
			res += "mut "
		if self.is_ref:
			res += "&"
		res += self.name
		if self.has_typ:
			res += f": {self.typ}"
		return res

	def __str__(self):
		return self.__repr__()

# ---- Declarations ----
class EmptyDecl:
	def __init__(self):
		self.attrs = Attrs()

class DocComment:
	def __init__(self, lines, pos):
		self.lines = lines
		self.pos = pos

	def has_doc(self):
		return len(self.lines) > 0

	def merge(self):
		res = ""
		for l in self.lines:
			res += l
			if len(l) == 0 or l.endswith("."):
				res += "\n"
			else:
				res += " "
		return res

class AttrArg:
	def __init__(self, name, expr):
		self.name = name
		self.expr = expr
		self.is_named = name != ""

class Attr:
	def __init__(self, name, args, pos):
		self.name = name
		self.args = args
		self.pos = pos

	def find_arg(self, name):
		for arg in self.args:
			if arg.name == name:
				return arg
		return None

class Attrs:
	def __init__(self):
		self.attrs = []
		self.if_check = True

	def add(self, attr):
		self.attrs.append(attr)

	def find(self, name):
		for attr in self.attrs:
			if attr.name == name:
				return attr
		return None

	def has(self, name):
		if _ := self.find(name):
			return True
		return False

	def has_attrs(self):
		return len(self.attrs) > 0

class ExternPkg:
	def __init__(self, pkg_name, pos):
		self.attrs = Attrs()
		self.pkg_name = pkg_name
		self.pos = pos

class UsingDecl:
	def __init__(self, attrs, vis, path, alias, symbols):
		self.attrs = attrs
		self.vis = vis
		self.path = path
		self.alias = alias
		self.symbols = symbols

class UsingSymbol:
	def __init__(self, name, alias, is_self, pos):
		self.name = name
		self.alias = alias
		self.is_self = is_self
		self.pos = pos

class ComptimeIfDecl:
	def __init__(self, branches, pos):
		self.branches = branches
		self.pos = pos
		self.branch_idx = -1

class ComptimeIfBranch:
	def __init__(self, cond, decls, is_else, kind):
		self.cond = cond
		self.decls = decls
		self.is_else = is_else
		self.kind = kind

class ExternDecl:
	def __init__(self, attrs, abi, protos, pos):
		self.attrs = attrs
		self.abi = abi
		self.protos = protos
		self.pos = pos

class ConstDecl:
	def __init__(self, doc_comment, attrs, vis, name, typ, expr, pos):
		self.doc_comment = doc_comment
		self.attrs = attrs
		self.vis = vis
		self.name = name
		self.typ = typ
		self.expr = expr
		self.sym = None
		self.pos = pos

class StaticDecl:
	def __init__(
	    self, doc_comment, attrs, vis, is_extern, is_mut, name, typ, expr, pos
	):
		self.doc_comment = doc_comment
		self.attrs = attrs
		self.vis = vis
		self.is_extern = is_extern
		self.is_mut = is_mut
		self.name = name
		self.typ = typ
		self.expr = expr
		self.sym = None
		self.pos = pos

class ModDecl:
	def __init__(self, doc_comment, attrs, name, vis, decls, is_unloaded, pos):
		self.doc_comment = doc_comment
		self.attrs = attrs
		self.name = name
		self.vis = vis
		self.decls = decls
		self.sym = None
		self.is_unloaded = is_unloaded
		self.pos = pos

class TypeDecl:
	def __init__(self, doc_comment, attrs, vis, name, parent, pos):
		self.doc_comment = doc_comment
		self.attrs = attrs
		self.vis = vis
		self.name = name
		self.parent = parent
		self.pos = pos

class ErrTypeDecl:
	def __init__(self, doc_comment, attrs, vis, name, pos):
		self.doc_comment = doc_comment
		self.attrs = attrs
		self.vis = vis
		self.name = name
		self.pos = pos

class TraitDecl:
	def __init__(self, doc_comment, attrs, vis, name, decls, pos):
		self.doc_comment = doc_comment
		self.attrs = attrs
		self.vis = vis
		self.name = name
		self.decls = decls
		self.pos = pos

class UnionDecl:
	def __init__(self, doc_comment, attrs, vis, name, variants, decls, pos):
		self.doc_comment = doc_comment
		self.attrs = attrs
		self.vis = vis
		self.name = name
		self.variants = variants
		self.decls = decls
		self.sym = None
		self.pos = pos

class StructField:
	def __init__(
	    self, attrs, doc_comment, vis, is_mut, name, typ, def_expr,
	    has_def_expr, pos
	):
		self.doc_comment = doc_comment
		self.attrs = attrs
		self.vis = vis
		self.is_mut = is_mut
		self.name = name
		self.typ = typ
		self.def_expr = def_expr
		self.has_def_expr = has_def_expr
		self.pos = pos

class StructDecl:
	def __init__(self, doc_comment, attrs, vis, name, decls, is_opaque, pos):
		self.doc_comment = doc_comment
		self.attrs = attrs
		self.vis = vis
		self.name = name
		self.decls = decls
		self.is_opaque = is_opaque
		self.sym = None
		self.pos = pos

class EnumDecl:
	def __init__(
	    self, doc_comment, attrs, vis, name, underlying_typ, variants, decls,
	    pos
	):
		self.doc_comment = doc_comment
		self.attrs = attrs
		self.vis = vis
		self.name = name
		self.underlying_typ = underlying_typ
		self.variants = variants
		self.decls = decls
		self.sym = None
		self.pos = pos

class ExtendDecl:
	def __init__(self, attrs, typ, is_for_trait, for_trait, decls, pos):
		self.attrs = attrs
		self.typ = typ
		self.is_for_trait = is_for_trait
		self.for_trait = for_trait
		self.decls = decls
		self.pos = pos

class FnDecl:
	def __init__(
	    self, doc_comment, attrs, vis, is_extern, is_unsafe, name, name_pos,
	    args, ret_typ, stmts, scope, has_body = False, is_method = False,
	    self_is_ref = False, self_is_mut = False, has_named_args = False,
	    is_main = False, is_variadic = False, abi = None,
	    type_arguments = list()
	):
		self.doc_comment = doc_comment
		self.attrs = attrs
		self.vis = vis
		self.abi = abi
		self.name = name
		self.name_pos = name_pos
		self.args = args
		self.self_is_ref = self_is_ref
		self.self_is_mut = self_is_mut
		self.self_typ = None
		self.is_main = is_main
		self.is_extern = is_extern
		self.is_unsafe = is_unsafe
		self.is_method = is_method
		self.is_variadic = is_variadic
		self.is_generic = len(type_arguments) > 0
		self.type_arguments = type_arguments
		self.ret_typ = ret_typ
		self.has_named_args = has_named_args
		self.has_body = has_body
		self.sym = None
		self.scope = scope
		self.stmts = stmts

class TestDecl:
	def __init__(self, scope, name, stmts, pos):
		self.name = name
		self.stmts = stmts
		self.scope = scope
		self.pos = pos

class DestructorDecl:
	def __init__(self, scope, stmts, pos):
		self.stmts = stmts
		self.scope = scope
		self.self_typ = None
		self.pos = pos

# ------ Statements --------
class AssignStmt:
	def __init__(self, left, op, right, pos):
		self.left = left
		self.op = op
		self.right = right
		self.pos = pos

class LetStmt:
	def __init__(self, scope, lefts, right, pos):
		self.lefts = lefts
		self.right = right
		self.scope = scope
		self.pos = pos

class LabelStmt:
	def __init__(self, label, pos):
		self.label = label
		self.pos = pos

class WhileStmt:
	def __init__(self, cond, stmt, is_inf, pos):
		self.cond = cond
		self.stmt = stmt
		self.is_inf = is_inf
		self.pos = pos

class ForInStmt:
	def __init__(self, scope, vars, iterable, stmt, pos):
		self.vars = vars
		self.iterable = iterable
		self.scope = scope
		self.stmt = stmt
		self.pos = pos

class GotoStmt:
	def __init__(self, label, pos):
		self.label = label
		self.pos = pos

class ExprStmt:
	def __init__(self, expr, pos):
		self.expr = expr
		self.pos = pos

	def __repr__(self):
		return str(self.expr)

	def __str__(self):
		return self.__repr__()

# ------ Expressions -------
class EmptyExpr:
	def __init__(self, pos):
		self.pos = pos

	def __repr__(self):
		return f'rivetc.EmptyExpr(pos: "{self.pos}")'

	def __str__(self):
		return self.__repr__()

class TypeNode:
	def __init__(self, typ, pos):
		self.typ = typ
		self.pos = pos

	def __repr__(self):
		return str(self.typ)

	def __str__(self):
		return self.__repr__()

class PkgExpr:
	def __init__(self, pos):
		self.pos = pos

	def __repr__(self):
		return "pkg"

	def __str__(self):
		return self.__repr__()

class Ident:
	def __init__(self, name, pos, scope, is_comptime, type_args = list()):
		self.name = name
		self.obj = None
		self.sym = None
		self.is_obj = False
		self.is_comptime = is_comptime
		self.type_arg_idx = -1
		self.type_args = type_args
		self.has_type_args = len(type_args) > 0
		self.scope = scope
		self.pos = pos
		self.typ = None

	def __repr__(self):
		if self.is_comptime:
			return f"${self.name}"
		elif self.has_type_args:
			return f"{self.name}::<{', '.join([str(t) for t in self.type_args])}>"
		return self.name

	def __str__(self):
		return self.__repr__()

class SelfExpr:
	def __init__(self, scope, pos):
		self.scope = scope
		self.pos = pos
		self.typ = None

	def __repr__(self):
		return "self"

	def __str__(self):
		return self.__repr__()

class SuperExpr:
	def __init__(self, scope, pos):
		self.scope = scope
		self.pos = pos
		self.typ = None

	def __repr__(self):
		return "super"

	def __str__(self):
		return self.__repr__()

class SelfTyExpr:
	def __init__(self, scope, pos):
		self.scope = scope
		self.pos = pos

	def __repr__(self):
		return "Self"

	def __str__(self):
		return self.__repr__()

class NoneLiteral:
	def __init__(self, pos):
		self.pos = pos
		self.typ = None

	def __repr__(self):
		return "none"

	def __str__(self):
		return self.__repr__()

class BoolLiteral:
	def __init__(self, lit, pos):
		self.lit = lit
		self.pos = pos
		self.typ = None

	def __repr__(self):
		return "true" if self.lit else "false"

	def __str__(self):
		return self.__repr__()

class CharLiteral:
	def __init__(self, lit, pos, is_byte):
		self.lit = lit
		self.pos = pos
		self.is_byte = is_byte
		self.typ = None

	def __repr__(self):
		p = "b" if self.is_byte else ""
		return f"{p}'{self.lit}'"

	def __str__(self):
		return self.__repr__()

class IntegerLiteral:
	def __init__(self, lit, pos):
		self.lit = lit
		self.pos = pos
		self.typ = None

	def __repr__(self):
		return self.lit

	def __str__(self):
		return self.__repr__()

class FloatLiteral:
	def __init__(self, lit, pos):
		self.lit = lit
		self.pos = pos
		self.typ = None

	def __repr__(self):
		return self.lit

	def __str__(self):
		return self.__repr__()

class StringLiteral:
	def __init__(self, lit, is_raw, is_bytestr, is_cstr, pos):
		self.lit = lit
		self.is_raw = is_raw
		self.is_bytestr = is_bytestr
		self.is_cstr = is_cstr
		self.pos = pos
		self.typ = None

	def __repr__(self):
		p = "c" if self.is_cstr else "b" if self.is_bytestr else "r" if self.is_raw else ""
		return f'{p}"{self.lit}"'

	def __str__(self):
		return self.__repr__()

class EnumVariantExpr:
	def __init__(self, variant, pos):
		self.variant = variant
		self.info = None
		self.pos = pos
		self.typ = None

	def __repr__(self):
		return f".{self.variant}"

	def __str__(self):
		return self.__repr__()

class StructLiteralField:
	def __init__(self, name, expr, pos):
		self.name = name
		self.expr = expr
		self.pos = pos
		self.typ = None

	def __repr__(self):
		return f"{self.name}: {self.expr}"

	def __str__(self):
		return self.__repr__()

class StructLiteral:
	def __init__(self, expr, fields, pos):
		self.expr = expr
		self.fields = fields
		self.pos = pos
		self.typ = None

	def __repr__(self):
		return f"{self.expr}{{ {', '.join([str(f) for f in self.fields])} }}"

	def __str__(self):
		return self.__repr__()

class TupleLiteral:
	def __init__(self, exprs, pos):
		self.exprs = exprs
		self.pos = pos
		self.typ = None

	def __repr__(self):
		return f"({', '.join([str(e) for e in self.exprs])})"

	def __str__(self):
		return self.__repr__()

class ArrayLiteral:
	def __init__(self, elems, pos):
		self.elems = elems
		self.pos = pos
		self.typ = None

	def __repr__(self):
		if len(self.elems) == 0:
			return "[]"
		return f"[{', '.join([str(e) for e in self.elems])}]"

	def __str__(self):
		return self.__repr__()

class CastExpr:
	def __init__(self, expr, typ, pos):
		self.expr = expr
		self.pos = pos
		self.typ = typ

	def __repr__(self):
		return f"as({self.typ}, {self.expr})"

	def __str__(self):
		return self.__repr__()

class GuardExpr:
	# Examples:
	# if (let x = optional_or_result_fn()) { ... }
	# while (let byte = reader.read()) { ... }
	def __init__(self, vars, expr, has_cond, cond, scope, pos):
		self.vars = vars
		self.expr = expr
		self.has_cond = has_cond
		self.cond = cond
		self.is_result = False
		self.scope = scope
		self.pos = pos

	def __repr__(self):
		vars_str = f"{', '.join([str(v) for v in self.vars])}"
		res = f"let {vars_str} = {self.expr}"
		if self.has_cond:
			res += f"; {self.cond}"
		return res

	def __str__(self):
		return self.__repr__()

class UnaryExpr:
	def __init__(self, right, op, is_ref_mut, pos):
		self.op = op
		self.right = right
		self.right_typ = None
		self.pos = pos
		self.is_ref_mut = is_ref_mut
		self.typ = None

	def __repr__(self):
		if self.is_ref_mut:
			return f"&mut {self.right}"
		return f"{self.op}{self.right}"

	def __str__(self):
		return self.__repr__()

class BinaryExpr:
	def __init__(self, left, op, right, pos):
		self.left = left
		self.op = op
		self.right = right
		self.pos = pos
		self.typ = None

	def __repr__(self):
		return f"{self.left} {self.op} {self.right}"

	def __str__(self):
		return self.__repr__()

class PostfixExpr:
	def __init__(self, left, op, pos):
		self.left = left
		self.op = op
		self.pos = pos
		self.typ = None

	def __repr__(self):
		return f"{self.left}{self.op}"

	def __str__(self):
		return self.__repr__()

class ParExpr:
	def __init__(self, expr, pos):
		self.expr = expr
		self.pos = pos
		self.typ = None

	def __repr__(self):
		return f"({self.expr})"

class IndexExpr:
	def __init__(self, left, index, is_mut, pos):
		self.left = left
		self.index = index
		self.is_mut = is_mut
		self.left_typ = None
		self.pos = pos
		self.typ = None

	def __repr__(self):
		kw = "mut " if self.is_mut else ""
		return f"{self.left}[{kw}{self.index}]"

	def __str__(self):
		return self.__repr__()

class CallExpr:
	def __init__(self, left, args, err_handler, pos):
		self.left = left
		self.args = args
		self.err_handler = err_handler
		self.info = None
		self.is_ctor = False # Trait_or_Union_or_Errtype(value)
		self.is_closure = False
		self.pos = pos
		self.typ = None

	def get_named_arg(self, name):
		for arg in self.args:
			if arg.is_named and arg.name == name:
				return arg
		return None

	# Returns the number of pure arguments, that is, not named, that
	# this call has.
	def pure_args_count(self):
		l = 0
		for arg in self.args:
			if not arg.is_named:
				l += 1
		return l

	def has_err_handler(self):
		return self.err_handler.has_expr or self.err_handler.is_propagate

	def __repr__(self):
		res = f"{self.left}({', '.join([str(a) for a in self.args])})"
		if self.has_err_handler():
			res += str(self.err_handler)
		return res

	def __str__(self):
		return self.__repr__()

class CallArg:
	def __init__(self, expr, pos, name = ""):
		self.expr = expr
		self.typ = None
		self.pos = pos
		self.name = name
		self.is_named = name != ""

	def __repr__(self):
		if self.is_named:
			return f"{self.name}: {self.expr}"
		return str(self.expr)

	def __str__(self):
		return self.__repr__()

class CallErrorHandler:
	def __init__(
	    self, is_propagate, varname, expr, has_expr, varname_pos, scope, pos
	):
		self.is_propagate = is_propagate
		self.varname = varname
		self.varname_pos = varname_pos
		self.expr = expr
		self.has_expr = has_expr
		self.scope = scope
		self.pos = pos

	def has_varname(self):
		return len(self.varname) > 0

	def __repr__(self):
		if self.is_propagate:
			return ".!"
		elif len(self.varname) == 0:
			return f" catch {self.expr}"
		return f" catch |{self.varname}| {self.expr}"

	def __str__(self):
		return self.__repr__()

class RangeExpr:
	def __init__(
	    self, start, end, is_inclusive, pos, has_start = True, has_end = True
	):
		self.start = start
		self.end = end
		self.is_inclusive = is_inclusive
		self.has_start = has_start
		self.has_end = has_end
		self.pos = pos
		self.typ = None

	def __repr__(self):
		sep = "..=" if self.is_inclusive else ".."
		if self.has_start and not self.has_end:
			return f"{self.start}{sep}"
		if not self.has_start and self.has_end:
			return f"{sep}{self.end}"
		return f"{self.start}{sep}{self.end}"

	def __str__(self):
		return self.__repr__()

class BuiltinCallExpr:
	def __init__(self, name, args, pos):
		self.name = name
		self.args = args
		self.pos = pos
		self.typ = None

	def __repr__(self):
		return f"{self.name}!({', '.join([str(a) for a in self.args])})"

	def __str__(self):
		return self.__repr__()

class SelectorExpr:
	def __init__(
	    self, left, field_name, pos, field_pos, is_indirect = False,
	    is_nonecheck = False
	):
		self.left = left
		self.field_name = field_name
		self.field_is_mut = False
		self.field_pos = field_pos
		self.left_typ = None
		self.is_indirect = is_indirect
		self.is_nonecheck = is_nonecheck
		self.pos = pos
		self.typ = None

	def __repr__(self):
		if self.is_indirect:
			return f"{self.left}.*"
		elif self.is_nonecheck:
			return f"{self.left}.?"
		return f"{self.left}.{self.field_name}"

	def __str__(self):
		return self.__repr__()

class PathExpr:
	def __init__(self, is_global, left, field_name, pos, field_pos):
		self.is_global = is_global
		self.left = left
		self.left_info = None
		self.field_name = field_name
		self.field_info = None
		self.field_pos = field_pos
		self.is_last = False
		self.has_error = False
		self.pos = pos
		self.typ = None

	def __repr__(self):
		return f"{self.left}::{self.field_name}"

	def __str__(self):
		return self.__repr__()

class BranchExpr:
	def __init__(self, op, pos):
		self.op = op
		self.pos = pos
		self.typ = None

	def __repr__(self):
		return str(self.op)

	def __str__(self):
		return self.__repr__()

class ReturnExpr:
	def __init__(self, expr, has_expr, pos):
		self.expr = expr
		self.has_expr = has_expr
		self.pos = pos
		self.typ = None

	def __repr__(self):
		if not self.has_expr:
			return "return"
		return f"return {self.expr}"

	def __str__(self):
		return self.__repr__()

class RaiseExpr:
	def __init__(self, expr, pos):
		self.expr = expr
		self.pos = pos
		self.typ = None

	def __repr__(self):
		return f"raise {self.expr}"

	def __str__(self):
		return self.__repr__()

class Block:
	def __init__(self, scope, is_unsafe, stmts, expr, is_expr, pos):
		self.is_unsafe = is_unsafe
		self.stmts = stmts
		self.expr = expr
		self.is_expr = is_expr
		self.typ = None
		self.scope = scope
		self.pos = pos

	def __repr__(self):
		prefix = "unsafe " if self.is_unsafe else ""
		if len(self.stmts) == 0:
			if self.is_expr:
				return f"{prefix}{{ {self.expr} }}"
			else:
				return f"{prefix}{{}}"
		if self.is_expr:
			return f"{prefix}{{ {'; '.join([str(s) for s in self.stmts])}; {self.expr} }}"
		if len(self.stmts) == 1:
			return f"{prefix}{{ {self.stmts[0]}; }}"
		return f"{prefix}{{ {'; '.join([str(s) for s in self.stmts])}; }}"

	def __str__(self):
		return self.__repr__()

class IfBranch:
	def __init__(self, is_comptime, cond, expr, is_else, op):
		self.is_comptime = is_comptime
		self.cond = cond
		self.expr = expr
		self.is_else = is_else
		self.op = op

	def __repr__(self):
		prefix = "$" if self.is_comptime else ""
		if self.is_else:
			return f"{prefix}else {self.expr}"
		return f"{prefix}{self.op} ({self.cond}) {self.expr}"

	def __str__(self):
		return self.__repr__()

class IfExpr:
	def __init__(self, is_comptime, branches, has_else, pos):
		self.is_comptime = is_comptime
		self.branches = branches
		self.branch_idx = -1 # for comptime
		self.has_else = has_else
		self.pos = pos
		self.typ = None

	def __repr__(self):
		return " ".join([str(b) for b in self.branches])

	def __str__(self):
		return self.__repr__()

class MatchBranch:
	def __init__(
	    self, pats, has_var, var_is_ref, var_is_mut, var_name, expr, is_else
	):
		self.pats = pats
		self.has_var = has_var
		self.var_is_ref = var_is_ref
		self.var_is_mut = var_is_mut
		self.var_name = var_name
		self.var_type = None
		self.expr = expr
		self.is_else = is_else

	def __repr__(self):
		if self.is_else:
			return f"else => {self.expr}"
		res = f"{', '.join([str(p) for p in self.pats])}"
		if self.has_var:
			res += f" as "
			if self.var_is_ref:
				res += "&"
				if self.var_is_mut:
					res += "mut "
			res += "{self.var_name}"
		res += f" => {self.expr}"
		return res

	def __str__(self):
		return self.__repr__()

class MatchExpr:
	def __init__(self, expr, branches, is_typematch, scope, pos):
		self.expr = expr
		self.branches = branches
		self.is_typematch = is_typematch
		self.scope = scope
		self.pos = pos
		self.typ = None

	def __repr__(self):
		kis = " is " if self.is_typematch else " "
		return f"match ({self.expr}){kis}{{ " + ", ".join([
		    str(b) for b in self.branches
		]) + " }"

	def __str__(self):
		return self.__repr__()
