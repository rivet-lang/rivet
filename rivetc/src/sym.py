# Copyright (C) 2023 Jose Mendoza. All rights reserved.
# Use of this source code is governed by an MIT license that can
# be found in the LICENSE file.

from enum import IntEnum as Enum, auto as auto_enum

from .token import NO_POS
from .utils import CompilerError

SYMBOL_COUNT = 0

def new_symbol_id():
    global SYMBOL_COUNT
    ret = SYMBOL_COUNT
    SYMBOL_COUNT += 1
    return ret

class ObjLevel(Enum):
    Rec = auto_enum()
    Arg = auto_enum()
    Local = auto_enum()

class Obj:
    def __init__(self, is_mut, name, typ, level, pos):
        self.name = name
        self.ir_name = name
        self.is_mut = is_mut
        self.is_used = False
        self.is_changed = False
        self.level = level
        self.pos = pos
        self.typ = typ

class Scope:
    def __init__(self, start, parent = None):
        self.parent = parent
        self.detached_from_parent = False
        self.objects = []
        self.childrens = []
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

    def update_type(self, name, typ):
        if obj := self.lookup(name):
            obj.typ = typ

    def update_ir_name(self, name, ir_name):
        if obj := self.lookup(name):
            obj.ir_name = ir_name

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

class Sym:
    def __init__(self, is_public, name, abi = ABI.Rivet):
        self.attributes = None
        self.id = new_symbol_id()
        self.abi = abi
        self.is_public = is_public
        self.name = name
        self.mangled_name = ""
        self.qualified_name = ""
        self.parent = None
        self.syms = []
        self.is_universe = isinstance(self, Mod) and self.id == 0
        self.is_root = False

    def add(self, sym):
        if asym := self.find(sym.name):
            if isinstance(asym, Type) and asym.kind == TypeKind.Placeholder:
                # update placeholder
                asym.update(sym)
                return
            raise CompilerError(
                f"{self.typeof()} `{self.name}` has duplicate symbol `{sym.name}`"
            )
        sym.parent = self
        self.syms.append(sym)

    def add_and_return(self, sym):
        idx = len(self.syms)
        for i, asym in enumerate(self.syms):
            if asym.name == sym.name:
                if isinstance(asym, Type) and asym.kind == TypeKind.Placeholder:
                    # update placeholder
                    asym.update(sym)
                    return self.syms[i]
                raise CompilerError(
                    f"{self.typeof()} `{self.name}` has duplicate symbol `{sym.name}`"
                )
        sym.parent = self
        self.syms.append(sym)
        return self.syms[idx]

    def add_or_get_mod(self, sym):
        if m := self.find(sym.name):
            return m
        return self.add_and_return(sym)

    def get_public_syms(self):
        syms = []
        for s in self.syms:
            if s.vis.is_public():
                syms.append(s)
        return syms

    def find(self, name):
        for sym in self.syms:
            if sym.name == name:
                return sym
        return None

    def exists(self, name):
        if _ := self.find(name):
            return True
        return False

    def mod(self):
        p = self
        while True:
            if isinstance(p, Mod):
                break
            p = p.parent
            if p == None:
                break
        return p

    def has_access_to(self, other):
        self_mod = self.mod()
        other_mod = other.mod()
        return (
            other_mod.is_universe or self_mod == other or self_mod == other_mod
            or self_mod == other_mod.parent or self_mod.parent == other.parent
        )

    def typeof(self):
        if isinstance(self, Mod):
            return "module"
        elif isinstance(self, Const):
            return "constant"
        elif isinstance(self, Var):
            return "variable"
        elif isinstance(self, Type):
            return "type"
        elif isinstance(self, Func):
            if self.is_method:
                return "method"
            return "function"
        return "unknown symbol kind"

    def qualname(self):
        if len(self.qualified_name) > 0:
            return self.qualified_name
        if self.parent == None or self.parent.is_universe:
            self.qualified_name = self.name
            return self.qualified_name
        self.qualified_name = f"{self.parent.qualname()}.{self.name}"
        return self.qualified_name

    def is_core_mod(self):
        return isinstance(self, Mod) and self.name == "core"

    def __getitem__(self, idx):
        if isinstance(idx, str):
            if s := self.find(idx):
                return s
            raise Exception(f"cannot find symbol `{idx}` in `{self.name}`")
        return self.syms[idx]

    def __eq__(self, other):
        if other == None:
            return False
        return self.id == other.id

class SymRef(Sym):
    def __init__(self, is_public, name, ref):
        Sym.__init__(self, is_public, name)
        self.ref = ref
        self.ref_resolved = False

    def typeof(self):
        return self.ref.typeof()

    def is_core_mod(self):
        return self.ref.is_core_mod()

class Mod(Sym):
    def add_or_get_slice(self, elem_typ, is_mut = False):
        if is_mut:
            unique_name = f"[:]mut {elem_typ.qualstr()}"
        else:
            unique_name = f"[:]{elem_typ.qualstr()}"
        if sym := self.find(unique_name):
            return sym
        from .type import Type as type_Type
        slice_sym = Type(
            True, unique_name, TypeKind.Slice,
            info = SliceInfo(elem_typ, is_mut),
            fields = [Field("len", False, True, type_Type(self[14]))]
        )
        slice_sym.add(
            Func(
                ABI.Rivet, True, False, False, True, False,
                "to_dynamic_array", [],
                type_Type(self.add_or_get_dyn_array(elem_typ, is_mut)), False,
                True, NO_POS, False, True, type_Type(slice_sym)
            )
        )
        if core_slice_sym := self.find("core").find("Slice"):
            if is_empty_m := core_slice_sym.find("is_empty"):
                slice_sym.add(is_empty_m)
        return self.add_and_return(slice_sym)

    def add_or_get_array(self, elem_typ, size, is_mut = False):
        if is_mut:
            unique_name = f"[{size}]mut {elem_typ.qualstr()}"
        else:
            unique_name = f"[{size}]{elem_typ.qualstr()}"
        if sym := self.find(unique_name):
            return sym
        from .type import Type as type_Type
        return self.add_and_return(
            Type(
                True, unique_name, TypeKind.Array,
                info = ArrayInfo(elem_typ, size, is_mut)
            )
        )

    def add_or_get_dyn_array(self, elem_typ, is_mut = False):
        if is_mut:
            unique_name = f"[]mut {elem_typ.qualstr()}"
        else:
            unique_name = f"[]{elem_typ.qualstr()}"
        if sym := self.find(unique_name):
            return sym
        from .type import Type as type_Type
        dyn_array_sym = Type(
            True, unique_name, TypeKind.DynArray,
            info = DynArrayInfo(elem_typ, is_mut), fields = [
                Field("len", False, True, type_Type(self[14])),
                Field("cap", False, True, type_Type(self[14]))
            ]
        )
        dyn_array_sym.add(
            Func(
                ABI.Rivet, True, False, False, True, False, "push",
                [Arg("value", False, elem_typ, None, False, NO_POS)],
                type_Type(self[0]), False, True, NO_POS, True, False,
                type_Type(dyn_array_sym)
            )
        )
        dyn_array_sym.add(
            Func(
                ABI.Rivet, True, False, False, True, False, "pop", [], elem_typ,
                False, True, NO_POS, True, False, type_Type(dyn_array_sym)
            )
        )
        dyn_array_sym.add(
            Func(
                ABI.Rivet, True, False, False, True, False, "clone", [],
                type_Type(dyn_array_sym), False, True, NO_POS, False, False,
                type_Type(dyn_array_sym)
            )
        )
        if core_dyn_array_sym := self.find("core").find("DynArray"):
            if is_empty_m := core_dyn_array_sym.find("is_empty"):
                dyn_array_sym.add(is_empty_m)
            if delete_m := core_dyn_array_sym.find("delete"):
                dyn_array_sym.add(delete_m)
            if trim_m := core_dyn_array_sym.find("trim"):
                dyn_array_sym.add(trim_m)
            if clear_m := core_dyn_array_sym.find("clear"):
                dyn_array_sym.add(clear_m)
        return self.add_and_return(dyn_array_sym)

    def add_or_get_tuple(self, types):
        unique_name = f"({', '.join([t.qualstr() for t in types])})"
        if sym := self.find(unique_name):
            return sym
        return self.add_and_return(
            Type(True, unique_name, TypeKind.Tuple, info = TupleInfo(types))
        )

class Const(Sym):
    def __init__(self, is_public, name, typ, expr):
        Sym.__init__(self, is_public, name)
        self.expr = expr
        self.evaled_expr = None
        self.has_evaled_expr = False
        self.ir_expr = None
        self.has_ir_expr = False
        self.typ = typ

class Var(Sym):
    def __init__(self, is_public, is_mut, is_extern, abi, name, typ):
        Sym.__init__(self, is_public, name, abi)
        self.is_extern = is_extern
        self.is_mut = is_mut
        self.is_changed = False
        self.typ = typ
        self.pos = None

class Field:
    def __init__(
        self, name, is_mut, is_public, typ, has_def_expr = False,
        def_expr = None, attrs = None
    ):
        self.name = name
        self.is_mut = is_mut
        self.is_public = is_public
        self.typ = typ
        self.has_def_expr = has_def_expr
        self.def_expr = def_expr
        self.attrs = None

class TypeKind(Enum):
    Placeholder = auto_enum()
    Never = auto_enum()
    Void = auto_enum()
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
    Int = auto_enum()
    Uint = auto_enum()
    ComptimeInt = auto_enum()
    ComptimeFloat = auto_enum()
    Float32 = auto_enum()
    Float64 = auto_enum()
    String = auto_enum()
    Alias = auto_enum()
    Slice = auto_enum()
    Array = auto_enum()
    DynArray = auto_enum()
    Tuple = auto_enum()
    Enum = auto_enum()
    Trait = auto_enum()
    Struct = auto_enum()

    def is_primitive(self):
        if self in (
            TypeKind.Void, TypeKind.None_, TypeKind.Bool, TypeKind.Rune,
            TypeKind.Int8, TypeKind.Int16, TypeKind.Int32, TypeKind.Int64,
            TypeKind.Int, TypeKind.Uint8, TypeKind.Uint16, TypeKind.Uint32,
            TypeKind.Uint64, TypeKind.Uint, TypeKind.ComptimeInt,
            TypeKind.ComptimeFloat, TypeKind.Float32, TypeKind.Float64,
            TypeKind.Never
        ):
            return True
        return False

    def __repr__(self):
        if self == TypeKind.Void:
            return "void"
        elif self == TypeKind.None_:
            return "none"
        elif self == TypeKind.Bool:
            return "bool"
        elif self == TypeKind.Rune:
            return "rune"
        elif self == TypeKind.Int8:
            return "int8"
        elif self == TypeKind.Int16:
            return "int16"
        elif self == TypeKind.Int32:
            return "int32"
        elif self == TypeKind.Int64:
            return "int64"
        elif self == TypeKind.Int:
            return "int"
        elif self == TypeKind.Uint8:
            return "uint8"
        elif self == TypeKind.Uint16:
            return "uint16"
        elif self == TypeKind.Uint32:
            return "uint32"
        elif self == TypeKind.Uint64:
            return "uint64"
        elif self == TypeKind.Uint:
            return "uint"
        elif self == TypeKind.ComptimeInt:
            return "comptime_int"
        elif self == TypeKind.ComptimeFloat:
            return "comptime_float"
        elif self == TypeKind.Float32:
            return "float32"
        elif self == TypeKind.Float64:
            return "float64"
        elif self == TypeKind.String:
            return "string"
        elif self == TypeKind.Alias:
            return "alias"
        elif self == TypeKind.Slice:
            return "slice"
        elif self == TypeKind.Array:
            return "array"
        elif self == TypeKind.DynArray:
            return "dynamic array"
        elif self == TypeKind.Tuple:
            return "tuple"
        elif self == TypeKind.Trait:
            return "trait"
        elif self == TypeKind.Struct:
            return "struct"
        elif self == TypeKind.Enum:
            return "enum"
        elif self == TypeKind.Never:
            return "never"
        return "placeholder"

    def __str__(self):
        return self.__repr__()

# Type infos

class AliasInfo:
    def __init__(self, parent):
        self.parent = parent
        self.is_resolved = False

class ArrayInfo:
    def __init__(self, elem_typ, size, is_mut):
        self.elem_typ = elem_typ
        self.size = size
        self.is_mut = is_mut
        self.has_contains_method = False

class DynArrayInfo:
    def __init__(self, elem_typ, is_mut):
        self.elem_typ = elem_typ
        self.is_mut = is_mut
        self.has_contains_method = False

class SliceInfo:
    def __init__(self, elem_typ, is_mut):
        self.elem_typ = elem_typ
        self.is_mut = is_mut
        self.has_contains_method = False

class TupleInfo:
    def __init__(self, types):
        self.types = types

class EnumVariant:
    def __init__(self, name, has_typ, typ, has_fields):
        self.name = name
        self.has_typ = has_typ
        self.typ = typ
        self.value = "0"
        self.has_fields = has_fields

class EnumInfo:
    def __init__(self, underlying_typ, is_tagged, is_boxed):
        self.underlying_typ = underlying_typ
        self.is_tagged = is_tagged
        self.is_boxed = is_boxed
        self.variants = []

    def add_variant(self, name, has_typ, typ, has_fields):
        self.variants.append(EnumVariant(name, has_typ, typ, has_fields))

    def get_variant(self, name):
        for v in self.variants:
            if v.name == name:
                return v
        return None

    def get_variant_by_type(self, typ):
        for v in self.variants:
            if v.has_typ and v.typ.symbol() == typ.symbol():
                return v
        return None

    def has_variant(self, name):
        if _ := self.get_variant(name):
            return True
        return False

class TraitInfo:
    def __init__(self):
        self.has_objects = False
        self.bases = []
        self.implements = []

    def indexof(self, sym):
        for idx, s in enumerate(self.implements):
            if s.id == sym.id:
                return idx
        return 0

    def implement(self, implementor):
        self.implements.append(implementor)
        for b in self.bases:
            b.info.implements.append(implementor)

    def mark_has_objects(self):
        self.has_objects = True

class StructInfo:
    def __init__(self, is_opaque, is_boxed = False, is_enum_variant = False):
        self.bases = []
        self.traits = []
        self.is_boxed = is_boxed
        self.is_opaque = is_opaque
        self.is_enum_variant = is_enum_variant

class Type(Sym):
    def __init__(self, is_public, name, kind, fields = [], info = None, attributes=None):
        Sym.__init__(self, is_public, name)
        self.attributes = attributes
        self.kind = kind
        self.fields = fields.copy()
        self.full_fields_ = []
        self.info = info
        self.size = -1
        self.align = -1
        self.raw_size = -1
        self.raw_align = -1
        self.default_value = None

    def find_field(self, name):
        for f in self.fields:
            if f.name == name:
                return f
        if self.kind == TypeKind.Struct:
            for base_t in self.info.traits:
                if f := base_t.find_field(name):
                    return f
            for base in self.info.bases:
                if f := base.find_field(name):
                    return f
        return None

    def has_field(self, name):
        if _ := self.find_field(name):
            return True
        return False

    def find_in_base(self, name):
        if self.kind == TypeKind.Trait:
            for base in self.info.bases:
                if s := Sym.find(base, name):
                    return s
        elif self.kind == TypeKind.Struct:
            for base_t in self.info.traits:
                if s := base_t.find(name):
                    return s
            for base in self.info.bases:
                if s := Sym.find(base, name):
                    return s
        return None

    def find(self, name):
        if s := Sym.find(self, name):
            return s
        if s := self.find_in_base(name):
            return s
        return None

    def full_fields(self):
        if len(self.full_fields_) > 0:
            return self.full_fields_
        fields = []
        if self.kind == TypeKind.Struct:
            for base_t in self.info.traits:
                fields += base_t.full_fields()
            for base in self.info.bases:
                fields += base.full_fields()
        for f in self.fields:
            fields.append(f)
        self.full_fields_ = fields
        return fields

    def update(self, other):
        if self.kind == TypeKind.Placeholder:
            # update placeholder
            self.is_public = other.is_public
            self.kind = other.kind
            self.fields = other.fields
            for ss in other.syms:
                self.add(ss)
            self.info = other.info

    def implement_trait(self, trait_sym):
        return self in trait_sym.info.implements

    def is_boxed(self):
        if isinstance(self.info, EnumInfo):
            return self.info.is_boxed
        elif isinstance(self.info, StructInfo):
            return self.info.is_boxed
        return self.kind == TypeKind.Trait

    def is_primitive(self):
        if self.kind == TypeKind.Enum:
            return not self.info.is_tagged
        return self.kind.is_primitive()

class Arg:
    def __init__(self, name, is_mut, typ, def_expr, has_def_expr, pos):
        self.name = name
        self.is_mut = is_mut
        self.is_self = name == "self"
        self.typ = typ
        self.def_expr = def_expr
        self.has_def_expr = has_def_expr
        self.pos = pos

class Func(Sym):
    def __init__(
        self, abi, is_public, is_extern, is_unsafe, is_method, is_variadic,
        name, args, ret_typ, has_named_args, has_body, name_pos, self_is_mut,
        self_is_ptr, self_typ = None, attributes = None, self_is_boxed = False
    ):
        Sym.__init__(self, is_public, name)
        self.is_main = False
        self.abi = abi
        self.is_extern = is_extern
        self.is_unsafe = is_unsafe
        self.is_method = is_method
        self.is_variadic = is_variadic
        self.self_typ = self_typ
        self.self_is_ptr = self_is_ptr
        self.self_is_boxed = self_is_boxed
        self.self_is_mut = self_is_mut
        self.args = args
        self.ret_typ = ret_typ
        self.has_named_args = has_named_args
        self.has_body = has_body
        self.name_pos = name_pos
        self.attributes = attributes

    def get_arg(self, idx):
        arg = self.args[idx]
        if arg.is_self:
            return self.args[idx + 1]
        return arg

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
        from .type import Func
        return Func(
            self.is_extern, self.abi, self.is_method, self.args,
            self.is_variadic, self.ret_typ, self.self_is_mut, self.self_is_ptr
        )

def universe():
    from .type import Ptr, Type as type_Type

    uni = Mod(False, "universe")
    uni.add(Type(True, "void", TypeKind.Void))
    uni.add(Type(True, "never", TypeKind.Never))
    uni.add(Type(True, "none", TypeKind.None_))
    uni.add(Type(True, "bool", TypeKind.Bool))
    uni.add(Type(True, "rune", TypeKind.Rune))
    uni.add(Type(True, "int8", TypeKind.Int8))
    uni.add(Type(True, "int16", TypeKind.Int16))
    uni.add(Type(True, "int32", TypeKind.Int32))
    uni.add(Type(True, "int64", TypeKind.Int64))
    uni.add(Type(True, "int", TypeKind.Int))
    uni.add(Type(True, "uint8", TypeKind.Uint8))
    uni.add(Type(True, "uint16", TypeKind.Uint16))
    uni.add(Type(True, "uint32", TypeKind.Uint32))
    uni.add(Type(True, "uint64", TypeKind.Uint64))
    uni.add(Type(True, "uint", TypeKind.Uint))
    uni.add(Type(True, "comptime_int", TypeKind.ComptimeInt))
    uni.add(Type(True, "comptime_float", TypeKind.ComptimeFloat))
    uni.add(Type(True, "float32", TypeKind.Float32))
    uni.add(Type(True, "float64", TypeKind.Float64))
    uni.add(Type(True, "string", TypeKind.String, info = StructInfo(False)))

    return uni
