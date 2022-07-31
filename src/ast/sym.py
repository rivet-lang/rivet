# Copyright (C) 2022 The Rivet Team. All rights reserved.
# Use of this source code is governed by an MIT license
# that can be found in the LICENSE file.

import copy
from enum import IntEnum as Enum, auto as auto_enum

from ..ast import Visibility
from ..utils import CompilerError

class Object:
	def __init__(self, is_mut, name, typ, is_arg):
		self.name = name
		self.is_mut = is_mut
		self.is_changed = False
		self.is_used = False
		self.is_arg = is_arg
		self.typ = typ

class Label:
	def __init__(self, name):
		self.name = name

class Scope:
	def __init__(self, start, parent = None):
		self.parent = parent
		self.detached_from_parent = False
		self.objects = []
		self.start = start
		self.end = 0

	def add(self, obj):
		if obj.name == "_":
			return # ignore special var
		if self.exists(obj.name):
			raise CompilerError(f"duplicate object `{obj.name}`")
		self.objects.append(obj)

	def exists(self, name):
		if _ := self.lookup(name):
			return True
		return False

	def lookup(self, name):
		sc = self
		while True:
			for obj in sc.objects:
				if obj.name == name:
					return obj
			if sc.dont_lookup_parent():
				break
			sc = sc.parent
		return None

	def dont_lookup_parent(self):
		return self.detached_from_parent or self.parent == None

	def update_typ(self, name, typ):
		if obj := self.lookup(name):
			obj.typ = typ

class ABI(Enum):
	Rivet = auto_enum()
	C = auto_enum()

	@staticmethod
	def from_string(abi):
		if abi == "C":
			return ABI.C
		elif abi == "Rivet":
			return ABI.Rivet
		return None

	def __repr__(self):
		if self == ABI.Rivet:
			return "Rivet"
		return "C"

	def __str__(self):
		return self.__repr__()

SYMBOL_COUNT = 0

def symbol_count():
	global SYMBOL_COUNT
	ret = SYMBOL_COUNT
	SYMBOL_COUNT += 1
	return ret

class Sym:
	def __init__(self, vis, name, type_arguments = list()):
		self.vis = vis
		self.name = name
		self.mangled_name = ""
		self.qualified_name = ""
		self.parent = None
		self.syms = []
		self.index = symbol_count()
		self.is_universe = isinstance(self, Pkg) and self.index == 0
		self.is_core = isinstance(self, Pkg) and self.index == 22
		self.is_generic = len(type_arguments) > 0
		self.is_generic_instance = False
		self.type_arguments = type_arguments
		self.uses = 0

	def add(self, sym):
		if asym := self.find(sym.name):
			if isinstance(asym, Type) and asym.kind == TypeKind.Placeholder:
				# update placeholder
				asym.vis = sym.vis
				asym.kind = sym.kind
				asym.fields = sym.fields
				for ss in sym.syms:
					if asym.exists(ss.name):
						raise CompilerError(
						    f"type `{asym.name}` has duplicate symbol: `{ss.name}`"
						)
					asym.syms.append(ss)
				asym.info = sym.info
				return
			else:
				raise CompilerError(
				    f"another symbol with this name already exists: `{sym.name}`"
				)
		sym.parent = self
		self.syms.append(sym)

	def add_and_return(self, sym):
		idx = len(self.syms)
		self.syms.append(sym)
		return self.syms[idx]

	def add_or_extend_mod(self, sym):
		if m := self.find(sym.name):
			return m
		nm = self.add_and_return(sym)
		nm.parent = self
		return nm

	def add_or_get_result(self, elem_typ):
		from ..codegen import mangle_type
		unique_name = f"Result_{mangle_type(elem_typ)}"
		if sym := self.find(unique_name):
			return sym

		from ..ast import type
		fields = []
		if elem_typ != type.Type(self[0]):
			fields.append(Field("value", False, Visibility.Private, elem_typ))
		fields.append(
		    Field("is_err", False, Visibility.Private, type.Type(self[2]))
		)
		fields.append(
		    Field("err", False, Visibility.Private, type.Type(self[19]))
		)
		return self.add_and_return(
		    Type(
		        Visibility.Public, unique_name, TypeKind.Struct, fields,
		        StructInfo(False)
		    )
		)

	def add_or_get_optional(self, elem_typ):
		from ..codegen import mangle_type
		unique_name = f"Optional_{mangle_type(elem_typ)}"
		if sym := self.find(unique_name):
			return sym

		from ..ast import type
		return self.add_and_return(
		    Type(
		        Visibility.Public, unique_name, TypeKind.Struct, [
		            Field("value", False, Visibility.Private, elem_typ),
		            Field(
		                "is_none", False, Visibility.Private,
		                type.Type(self[2])
		            )
		        ], StructInfo(False)
		    )
		)

	def add_or_get_array(self, elem_typ, size):
		unique_name = f"[{elem_typ.qualstr()}; {size}]"
		if sym := self.find(unique_name):
			return sym
		return self.add_and_return(
		    Type(
		        Visibility.Public, unique_name, TypeKind.Array,
		        info = ArrayInfo(elem_typ, size)
		    )
		)

	def add_or_get_slice(self, elem_typ, is_mut):
		unique_name = f"[{elem_typ.qualstr()}]"
		if sym := self.find(unique_name):
			return sym
		from ..ast.type import Ptr, Type as type_Type
		return self.add_and_return(
		    Type(
		        Visibility.Public, unique_name, TypeKind.Slice, [
		            Field(
		                "ptr", False, Visibility.Public,
		                Ptr(type_Type(self[0]))
		            )
		        ], SliceInfo(elem_typ, is_mut)
		    )
		)

	def add_or_get_tuple(self, types):
		unique_name = f"({', '.join([t.qualstr() for t in types])})"
		if sym := self.find(unique_name):
			return sym
		return self.add_and_return(
		    Type(
		        Visibility.Public, unique_name, TypeKind.Tuple,
		        info = TupleInfo(types)
		    )
		)

	def get_public_syms(self):
		syms = []
		for s in self.syms:
			if s.vis.is_pub():
				syms.append(s)
		return syms

	def find_type_arg(self, name):
		for i, type_arg in enumerate(self.syms):
			if type_arg.kind == TypeKind.TypeArg and type_arg.name == name:
				return (type_arg, i)
		return None

	def find(self, name):
		for sym in self.syms:
			if sym.name == name:
				return sym
		return None

	def exists(self, name):
		if _ := self.find(name):
			return True
		return False

	def super_(self):
		# package or module
		p = self
		while True:
			if isinstance(p, (Pkg, Mod)):
				break
			p = p.parent
			if p == None:
				break
		return p

	def has_access_to(self, other):
		self_super = self.super_()
		other_super = other.super_()
		return (
		    self_super == other or self_super == other_super
		    or self_super == other_super.parent
		    or self_super.parent == other.parent
		)

	def is_used(self):
		return self.vis.is_pub() or self.uses > 0

	def sym_kind(self):
		if isinstance(self, Pkg):
			return "package"
		elif isinstance(self, Mod):
			return "module"
		elif isinstance(self, Const):
			return "constant"
		elif isinstance(self, Static):
			return "static"
		elif isinstance(self, Type):
			return "type"
		elif isinstance(self, Fn):
			if self.is_method:
				return "method"
			return "function"
		return "unknown symbol kind"

	def qualname(self):
		if len(self.qualified_name) > 0:
			return self.qualified_name
		if self.parent == None or self.parent.is_universe:
			self.qualified_name = self.name
			if self.is_generic:
				self.qualified_name += "::<>"
			return self.qualified_name
		self.qualified_name = f"{self.parent.qualname()}::{self.name}"
		if self.is_generic:
			self.qualified_name += "::<>"
		return self.qualified_name

	def inst_generic(self, type_args):
		from ..ast.type import resolve_generic
		from ..codegen import mangle_symbol, mangle_type

		new_name = f"{self.name}<{', '.join([t.qualstr() for t in type_args])}>"
		if generic_sym := self.find(new_name):
			return generic_sym

		type_args_mangled = f"Lt_{'__'.join([mangle_type(t) for t in type_args])}_Gt"
		new_inst = copy.copy(self)
		new_inst.name = new_name
		new_inst.mangled_name = f"{mangle_symbol(self)}{len(type_args_mangled)}{type_args_mangled}"
		new_inst.type_arguments = type_args
		new_inst.is_generic = False
		new_inst.is_generic_instance = True
		new_inst.parent = self
		if isinstance(self, Fn):
			for typ_arg in self.type_arguments:
				concrete_type = type_args[typ_arg.idx]
				new_args = []
				for arg in new_inst.args:
					new_arg = copy.copy(arg)
					new_arg.typ = resolve_generic(
					    new_arg.typ, typ_arg, concrete_type
					)
					new_args.append(new_arg)
				new_inst.args = new_args
				new_inst.ret_typ = resolve_generic(
				    new_inst.ret_typ, typ_arg, concrete_type
				)
		self.syms.append(new_inst)
		return new_inst

	def __getitem__(self, idx):
		if isinstance(idx, str):
			return self.find(idx)
		return self.syms[idx]

class Pkg(Sym):
	pass

class Mod(Sym):
	pass

class Const(Sym):
	def __init__(self, vis, name, typ, expr):
		Sym.__init__(self, vis, name)
		self.expr = expr
		self.evaled_expr = None
		self.has_evaled_expr = False
		self.ir_expr = None
		self.has_ir_expr = False
		self.typ = typ

class Static(Sym):
	def __init__(self, vis, is_mut, is_extern, name, typ):
		Sym.__init__(self, vis, name)
		self.is_extern = is_extern
		self.is_mut = is_mut
		self.typ = typ

class Field:
	def __init__(
	    self, name, is_mut, vis, typ, has_def_expr = False, def_expr = None
	):
		self.name = name
		self.is_mut = is_mut
		self.vis = vis
		self.typ = typ
		self.has_def_expr = has_def_expr
		self.def_expr = def_expr

class TypeKind(Enum):
	Placeholder = auto_enum()
	Void = auto_enum()
	TypeArg = auto_enum()
	None_ = auto_enum()
	Bool = auto_enum()
	Rune = auto_enum()
	Int8 = auto_enum()
	Int16 = auto_enum()
	Int32 = auto_enum()
	Int64 = auto_enum()
	Uint8 = auto_enum()
	Uint16 = auto_enum()
	Uint32 = auto_enum()
	Uint64 = auto_enum()
	Isize = auto_enum()
	Usize = auto_enum()
	UntypedInt = auto_enum()
	UntypedFloat = auto_enum()
	Float32 = auto_enum()
	Float64 = auto_enum()
	Str = auto_enum()
	Alias = auto_enum()
	ErrType = auto_enum()
	Array = auto_enum()
	Slice = auto_enum()
	Tuple = auto_enum()
	Enum = auto_enum()
	Struct = auto_enum()
	Union = auto_enum()
	Trait = auto_enum()
	NoReturn = auto_enum()

	def is_primitive(self):
		if self in (
		    TypeKind.Void, TypeKind.None_, TypeKind.Bool, TypeKind.Rune,
		    TypeKind.Int8, TypeKind.Int16, TypeKind.Int32, TypeKind.Int64,
		    TypeKind.Isize, TypeKind.Uint8, TypeKind.Uint16, TypeKind.Uint32,
		    TypeKind.Uint64, TypeKind.Usize, TypeKind.UntypedInt,
		    TypeKind.UntypedFloat, TypeKind.Float32, TypeKind.Float64
		):
			return True
		return False

	def __repr__(self):
		if self == TypeKind.Void:
			return "void"
		elif self == TypeKind.TypeArg:
			return "type argument"
		elif self == TypeKind.None_:
			return "none"
		elif self == TypeKind.Bool:
			return "bool"
		elif self == TypeKind.Rune:
			return "rune"
		elif self == TypeKind.Int8:
			return "i8"
		elif self == TypeKind.Int16:
			return "i16"
		elif self == TypeKind.Int32:
			return "i32"
		elif self == TypeKind.Int64:
			return "i64"
		elif self == TypeKind.Isize:
			return "isize"
		elif self == TypeKind.Uint8:
			return "u8"
		elif self == TypeKind.Uint16:
			return "u16"
		elif self == TypeKind.Uint32:
			return "u32"
		elif self == TypeKind.Uint64:
			return "u64"
		elif self == TypeKind.Usize:
			return "usize"
		elif self == TypeKind.UntypedInt:
			return "untyped_int"
		elif self == TypeKind.UntypedFloat:
			return "untyped_float"
		elif self == TypeKind.Float32:
			return "f32"
		elif self == TypeKind.Float64:
			return "f64"
		elif self == TypeKind.Str:
			return "str"
		elif self == TypeKind.Alias:
			return "alias"
		elif self == TypeKind.ErrType:
			return "errtype"
		elif self == TypeKind.Array:
			return "array"
		elif self == TypeKind.Slice:
			return "slice"
		elif self == TypeKind.Tuple:
			return "tuple"
		elif self == TypeKind.Enum:
			return "enum"
		elif self == TypeKind.Struct:
			return "struct"
		elif self == TypeKind.Union:
			return "union"
		elif self == TypeKind.Trait:
			return "trait"
		elif self == TypeKind.NoReturn:
			return "no_return"
		return "placeholder"

	def __str__(self):
		return self.__repr__()

# Type infos

class AliasInfo:
	def __init__(self, parent):
		self.parent = parent

class ErrTypeInfo:
	def __init__(self, nr):
		self.nr = nr

class ArrayInfo:
	def __init__(self, elem_typ, size):
		self.elem_typ = elem_typ
		self.size = size
		self.has_wrapper = False # for return values in C backend

class SliceInfo:
	def __init__(self, elem_typ, is_mut):
		self.elem_typ = elem_typ
		self.is_mut = is_mut

class TupleInfo:
	def __init__(self, types):
		self.types = types

class EnumVariant:
	def __init__(self, name):
		self.name = name
		self.value = 0

class EnumInfo:
	def __init__(self, underlying_typ, variants):
		self.underlying_typ = underlying_typ
		self.variants = variants

	def get_variant(self, name):
		for v in self.variants:
			if v.name == name:
				return v
		return None

	def has_variant(self, name):
		if _ := self.get_variant(name):
			return True
		return False

class TraitInfo:
	def __init__(self):
		self.implements = []
		self.has_objects = False

	def indexof(self, impl):
		for idx, i in enumerate(self.implements):
			if i == impl: return idx
		return -1

class UnionInfo:
	def __init__(self, variants, is_c_union):
		self.variants = variants
		self.is_c_union = is_c_union # C-like union

class StructInfo:
	def __init__(self, is_opaque):
		self.is_opaque = is_opaque

class Type(Sym):
	def __init__(self, vis, name, kind, fields = [], info = None):
		Sym.__init__(self, vis, name)
		self.kind = kind
		self.fields = fields
		self.info = info
		self.size = -1
		self.align = -1

	def lookup_field(self, name):
		for f in self.fields:
			if f.name == name:
				return f
		return None

	def has_field(self, name):
		if _ := self.lookup_field(name):
			return True
		return False

class Arg:
	def __init__(self, name, typ, def_expr, has_def_expr, pos):
		self.name = name
		self.is_self = name == "self"
		self.typ = typ
		self.def_expr = def_expr
		self.has_def_expr = has_def_expr
		self.pos = pos

class Fn(Sym):
	def __init__(
	    self, abi, vis, is_extern, is_unsafe, is_method, is_variadic, name,
	    args, ret_typ, has_named_args, has_body, name_pos, rec_is_mut,
	    rec_is_ref, type_arguments
	):
		Sym.__init__(self, vis, name, type_arguments)
		self.is_main = False
		self.abi = abi
		self.is_extern = is_extern
		self.is_unsafe = is_unsafe
		self.is_method = is_method
		self.is_variadic = is_variadic
		self.self_typ = None
		self.rec_is_mut = rec_is_mut
		self.rec_is_ref = rec_is_ref
		self.args = args
		self.ret_typ = ret_typ
		self.has_named_args = has_named_args
		self.has_body = has_body
		self.name_pos = name_pos

	def args_len(self):
		from .type import Variadic
		len_ = 0
		for arg in self.args:
			if not (arg.is_self or isinstance(arg.typ, Variadic)):
				len_ += 1
		return len_

	def kind(self):
		if self.is_method:
			return "method"
		return "function"

	def typ(self):
		from .type import Fn
		args = []
		for arg in self.args:
			args.append(arg.typ)
		return Fn(
		    self.is_unsafe, self.is_extern, self.abi, self.is_method, args,
		    self.is_variadic, self.ret_typ, self.rec_is_mut, self.rec_is_ref
		)

def universe():
	uni = Pkg(Visibility.Private, "universe")
	uni.add(Type(Visibility.Public, "void", TypeKind.Void))
	uni.add(Type(Visibility.Public, "none", TypeKind.None_))
	uni.add(Type(Visibility.Public, "bool", TypeKind.Bool))
	uni.add(Type(Visibility.Public, "rune", TypeKind.Rune))
	uni.add(Type(Visibility.Public, "i8", TypeKind.Int8))
	uni.add(Type(Visibility.Public, "i16", TypeKind.Int16))
	uni.add(Type(Visibility.Public, "i32", TypeKind.Int32))
	uni.add(Type(Visibility.Public, "i64", TypeKind.Int64))
	uni.add(Type(Visibility.Public, "isize", TypeKind.Isize))
	uni.add(Type(Visibility.Public, "u8", TypeKind.Uint8))
	uni.add(Type(Visibility.Public, "u16", TypeKind.Uint16))
	uni.add(Type(Visibility.Public, "u32", TypeKind.Uint32))
	uni.add(Type(Visibility.Public, "u64", TypeKind.Uint64))
	uni.add(Type(Visibility.Public, "usize", TypeKind.Usize))
	uni.add(Type(Visibility.Public, "untyped_int", TypeKind.UntypedInt))
	uni.add(Type(Visibility.Public, "untyped_float", TypeKind.UntypedFloat))
	uni.add(Type(Visibility.Public, "f32", TypeKind.Float32))
	uni.add(Type(Visibility.Public, "f64", TypeKind.Float64))
	from ..ast.type import Ptr, Type as type_Type
	uni.add(
	    Type(
	        Visibility.Public, "str", TypeKind.Str, fields = [
	            Field("ptr", False, Visibility.Public, Ptr(type_Type(uni[9]))),
	            Field("len", False, Visibility.Public, type_Type(uni[13]))
	        ]
	    )
	)
	uni.add(Type(Visibility.Public, "error", TypeKind.Struct))
	uni.add(Type(Visibility.Public, "no_return", TypeKind.NoReturn))
	return uni
