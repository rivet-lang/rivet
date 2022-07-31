# Copyright (C) 2022 The Rivet Team. All rights reserved.
# Use of this source code is governed by an MIT license
# that can be found in the LICENSE file.

import copy

from .. import token
from . import Visibility
from .sym import TypeKind, Fn as FnInfo, Arg

def resolve_generic(typ, generic_type, concrete_type):
	if isinstance(typ, Fn):
		final_typ = copy.copy(typ)
		typ_args = []
		for arg in typ.args:
			typ_args.append(resolve_generic(arg, generic_type, concrete_type))
		final_typ.args = typ_args
		final_typ.ret_typ = resolve_generic(
		    typ.ret_typ, generic_type, concrete_type
		)
		return final_typ
	elif isinstance(typ, Tuple):
		final_types = []
		for t in typ.types:
			final_types.append(resolve_generic(t, generic_type, concrete_type))
		return Tuple(final_types)
	elif isinstance(typ, (Result, Optional, Array, Slice, Ptr, Ref)):
		final_typ = resolve_generic(typ.typ, generic_type, concrete_type)
		if isinstance(typ, Result):
			return Result(final_typ)
		elif isinstance(typ, Optional):
			return Optional(final_typ)
		elif isinstance(typ, Slice):
			return Slice(final_typ, typ.is_mut)
		elif isinstance(typ, Ptr):
			return Ptr(final_typ, typ.is_mut)
		elif isinstance(typ, Ref):
			return Ref(final_typ, typ.is_mut)
		return Array(final_typ, typ.size)
	elif isinstance(typ, Type):
		if typ.is_resolved() and typ.sym.kind == TypeKind.TypeArg:
			if (
			    isinstance(generic_type, Generic)
			    and typ.sym.name == generic_type.name
			) or typ.sym.name == generic_type.sym.name:
				return concrete_type
		return typ
	return typ

class _Ptr: # ugly hack =/
	def __init__(self, val):
		self.val = val

	def store(self, val):
		self.val.__class__ = val.__class__
		self.val.__dict__ = val.__dict__

class TBase:
	def get_sym(self):
		if isinstance(self, (Type, Slice, Array, Tuple, Variadic)):
			return self.sym
		elif isinstance(self, Fn):
			return self.info()
		return self.typ.get_sym()

	def unalias(self):
		if isinstance(self, (Result, Optional)):
			self.typ.unalias()
		elif isinstance(self, Fn):
			for i in range(len(self.args)):
				self.args[i].unalias()
			self.ret_typ.unalias()
		elif isinstance(self, Tuple):
			for t in self.types:
				t.unalias()
		elif isinstance(self, (Array, Slice, Ptr, Ref)):
			self.typ.unalias()
		elif isinstance(self, Type):
			if self.is_resolved() and self.sym.kind == TypeKind.Alias:
				self.sym.info.parent.unalias()
				_Ptr(self).store(self.sym.info.parent)

class Generic(TBase):
	def __init__(self, name, idx, pos):
		self.name = name
		self.idx = idx
		self.pos = pos

	def qualstr(self):
		return self.name

	def __eq__(self, other):
		if not isinstance(other, Generic):
			return False
		return self.name == other.name

	def __str__(self):
		return self.name

class Type(TBase):
	def __init__(self, sym):
		self.sym = sym
		self.expr = None
		self._unresolved = False
		self.is_generic = False

	@staticmethod
	def unresolved(expr):
		typ = Type(None)
		typ.expr = expr
		typ._unresolved = True
		return typ

	def resolve(self, sym):
		self.sym = sym
		self._unresolved = False

	def is_resolved(self):
		return not self._unresolved

	def qualstr(self):
		return self.sym.qualname()

	def __eq__(self, other):
		if not isinstance(other, Type):
			return False
		return self.sym == other.sym

	def __str__(self):
		if self._unresolved:
			return str(self.expr)
		return str(self.sym.name)

class Ref(TBase):
	def __init__(self, typ, is_mut = False):
		self.typ = typ
		self.is_mut = is_mut

	def qualstr(self):
		kmut = "mut " if self.is_mut else ""
		return f"&{kmut}{self.typ.qualstr()}"

	def nr_level(self):
		return 1

	def __eq__(self, other):
		if not isinstance(other, Ref):
			return False
		elif self.is_mut and not other.is_mut:
			return False
		return self.typ == other.typ

	def __str__(self):
		kmut = "mut " if self.is_mut else ""
		return f"&{kmut}{self.typ}"

class Ptr(TBase):
	def __init__(self, typ, is_mut = False):
		self.typ = typ
		self.is_mut = is_mut

	def qualstr(self):
		kmut = "mut " if self.is_mut else ""
		return f"*{kmut}{self.typ.qualstr()}"

	def nr_level(self):
		nr = 0
		ptr = self
		while isinstance(ptr, Ptr):
			ptr = ptr.typ
			nr += 1
		return nr

	def __eq__(self, other):
		if not isinstance(other, Ptr):
			return False
		elif self.is_mut and not other.is_mut:
			return False
		return self.typ == other.typ

	def __str__(self):
		kmut = "mut " if self.is_mut else ""
		return f"*{kmut}{self.typ}"

class Slice(TBase):
	def __init__(self, typ, is_mut = False):
		self.typ = typ
		self.is_mut = is_mut
		self.sym = None

	def resolve(self, sym):
		self.sym = sym

	def qualstr(self):
		kw = "mut " if self.is_mut else ""
		return f"[{kw}{self.typ.qualstr()}]"

	def __eq__(self, other):
		if not isinstance(other, Slice):
			return False
		return self.is_mut == other.is_mut and self.typ == other.typ

	def __str__(self):
		kw = "mut " if self.is_mut else ""
		return f"[{kw}{self.typ}]"

class Variadic(TBase):
	def __init__(self, typ):
		self.typ = typ
		self.sym = None

	def resolve(self, sym):
		self.sym = sym

	def qualstr(self):
		return f"...{self.typ.qualstr()}"

	def __eq__(self, other):
		if not isinstance(other, Variadic):
			return False
		return self.typ == other.typ

	def __str__(self):
		return f"...{self.typ}"

class Array(TBase):
	def __init__(self, typ, size):
		self.typ = typ
		self.size = size
		self.sym = None

	def resolve(self, sym):
		self.sym = sym

	def qualstr(self):
		return f"[{self.typ.qualstr()}; {self.size}]"

	def __eq__(self, other):
		if not isinstance(other, Array):
			return False
		return self.typ == other.typ and self.size == other.size

	def __str__(self):
		return f"[{self.typ}; {self.size}]"

class Tuple(TBase):
	def __init__(self, types):
		self.types = types
		self.sym = None

	def resolve(self, sym):
		self.sym = sym

	def qualstr(self):
		return f"({', '.join([t.qualstr() for t in self.types])})"

	def __str__(self):
		return f"({', '.join([str(t) for t in self.types])})"

class Fn(TBase):
	def __init__(
	    self, is_unsafe, is_extern, abi, is_method, args, is_variadic, ret_typ,
	    rec_is_mut, rec_is_ref
	):
		self.is_unsafe = is_unsafe
		self.is_extern = is_extern
		self.abi = abi
		self.is_method = is_method
		self.rec_is_ref = rec_is_ref
		self.rec_is_mut = rec_is_mut
		self.args = args
		self.is_variadic = is_variadic
		self.ret_typ = ret_typ

	def info(self):
		args = []
		for i, arg in enumerate(self.args):
			args.append(
			    Arg(f"arg{i+1}", arg, None, False, token.Pos("", 0, 0, 0))
			)
		return FnInfo(
		    self.abi, Visibility.Public, self.is_extern,
		    self.is_unsafe, self.is_method, self.is_variadic,
		    self.stringify(False), args, self.ret_typ, False,
		    not self.is_extern, token.Pos("", 0, 0, 0), self.rec_is_mut,
		    self.rec_is_ref, []
		)

	def stringify(self, qual):
		res = ""
		if self.is_unsafe:
			res += "unsafe "
		if self.is_extern:
			res += f'extern ({self.abi}) '
		res += "fn("
		if self.is_method:
			if self.rec_is_ref:
				res += "&"
			if self.rec_is_mut:
				res += "mut "
			res += "self"
			if len(self.args) > 0:
				res += ", "
		for i, arg in enumerate(self.args):
			if qual:
				res += arg.qualstr()
			else:
				res += str(arg)
			if i < len(self.args) - 1:
				res += ", "
		if self.is_extern and self.is_variadic:
			res += ", ..."
		res += ") "
		if qual:
			res += self.ret_typ.qualstr()
		else:
			res += str(self.ret_typ)
		return res

	def __eq__(self, got):
		if not isinstance(got, Fn): return False
		if self.is_unsafe != got.is_unsafe:
			return False
		elif self.is_extern != got.is_extern:
			return False
		elif self.abi != got.abi:
			return False
		elif self.is_method != got.is_method:
			return False
		elif self.rec_is_ref != got.rec_is_ref:
			return False
		elif self.rec_is_mut != got.rec_is_mut:
			return False
		elif len(self.args) != len(got.args):
			return False
		for i, arg in enumerate(self.args):
			if arg != got.args[i]:
				return False
		return self.ret_typ == got.ret_typ

	def __str__(self):
		return self.stringify(False)

class Optional(TBase):
	def __init__(self, typ):
		self.typ = typ
		self.sym = None

	def qualstr(self):
		return f"?{self.typ.qualstr()}"

	def __eq__(self, other):
		if not isinstance(other, Optional):
			return False
		return self.typ == other.typ

	def __str__(self):
		return f"?{self.typ}"

class Result(TBase):
	def __init__(self, typ):
		self.typ = typ
		self.sym = None

	def qualstr(self):
		return f"!{self.typ.qualstr()}"

	def __eq__(self, other):
		if not isinstance(other, Result):
			return False
		return self.typ == other.typ

	def __str__(self):
		return f"!{self.typ}"
