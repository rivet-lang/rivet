# Copyright (C) 2023 Jose Mendoza. All rights reserved.
# Use of this source code is governed by an MIT license that can
# be found in the LICENSE file.

import copy

from . import token
from .sym import TypeKind, Type as sym_Type, Func as sym_Func, Arg, ABI

class _Ptr: # ugly hack =/
    def __init__(self, val):
        self.val = val

    def store(self, val):
        self.val.__class__ = val.__class__
        self.val.__dict__ = val.__dict__

class TBase:
    def value_is_boxed(self):
        if isinstance(self, Type):
            return self.is_boxed
        return self.symbol().is_boxed()

    def symbol(self):
        if isinstance(self, (DynArray, Array, Tuple, Variadic, Slice)):
            return self.sym
        elif isinstance(self, Func):
            return self.info()
        elif isinstance(self, Boxedptr):
            return sym_Type(False, "boxedptr", TypeKind.Void)
        return self.typ.symbol()

    def unalias(self):
        if isinstance(self, (Result, Option)):
            self.typ.unalias()
        elif isinstance(self, Func):
            for i in range(len(self.args)):
                self.args[i].typ.unalias()
            self.ret_typ.unalias()
        elif isinstance(self, Tuple):
            for t in self.types:
                t.unalias()
        elif isinstance(self, (Array, DynArray, Ptr, Variadic, Slice)):
            self.typ.unalias()
        elif isinstance(self, Type):
            if self.is_resolved() and self.sym.kind == TypeKind.Alias:
                self.sym.info.parent.unalias()
                _Ptr(self).store(self.sym.info.parent)

class Type(TBase):
    def __init__(self, sym, is_boxed = False, is_mut = False):
        self.sym = sym
        self.expr = None
        self._unresolved = False

        self.is_boxed = is_boxed
        self.is_mut = is_mut

    @staticmethod
    def unresolved(expr, is_boxed = False, is_mut = False):
        typ = Type(None, is_boxed, is_mut)
        typ.expr = expr
        typ._unresolved = True
        return typ

    def resolve(self, sym):
        self.sym = sym
        self._unresolved = False

    def is_resolved(self):
        return not self._unresolved

    def to_boxed(self, is_mut):
        return Type(self.sym, True, is_mut)

    def qualstr(self):
        qualname = self.sym.qualname()
        if self.is_boxed:
            res = "+"
            if self.is_mut:
                res += "mut "
            res += qualname
            return res
        return qualname

    def symbol(self):
        sy = self.sym
        return sy

    def __eq__(self, other):
        if not isinstance(other, Type):
            return False
        if self.is_boxed and not other.is_boxed:
            return False
        if self.is_mut and not other.is_mut:
            return False
        return self.sym == other.sym

    def __str__(self):
        if self._unresolved:
            res = str(self.expr)
        else:
            res = str(self.sym.name)
        if self.is_boxed:
            if self.is_mut:
                res = f"^mut {res}"
            else:
                res = f"^{res}"
        return res

class Boxedptr(TBase):
    def __init__(self):
        pass

    def nr_level(self):
        return 0

    def qualstr(self):
        return "boxedptr"

    def __eq__(self, other):
        return isinstance(other, Boxedptr)

    def __str__(self):
        return "boxedptr"

class Ptr(TBase):
    def __init__(self, typ, is_mut = False, is_indexable = False):
        self.typ = typ
        self.is_mut = is_mut
        self.is_indexable = is_indexable or str(typ) == "void"

    def nr_level(self):
        level = 0
        p = self
        while isinstance(p, Ptr):
            level += 1
            p = p.typ
            if isinstance(p, Option):
                p = p.typ
        return level

    def qualstr(self):
        if str(self.typ) == "void":
            return "rawptr"
        elif self.is_mut:
            if self.is_indexable:
                return f"[&]mut {self.typ.qualstr()}"
            return f"&mut {self.typ.qualstr()}"
        if self.is_indexable:
            return f"[&]{self.typ.qualstr()}"
        return f"&{self.typ.qualstr()}"

    def __eq__(self, other):
        if not isinstance(other, Ptr):
            return False
        elif self.is_mut and not other.is_mut:
            return False
        elif self.is_indexable and not other.is_indexable:
            return False
        return self.typ == other.typ

    def __str__(self):
        if str(self.typ) == "void":
            return "rawptr"
        elif self.is_mut:
            if self.is_indexable:
                return f"[&]mut {self.typ}"
            return f"&mut {self.typ}"
        if self.is_indexable:
            return f"[&]{self.typ}"
        return f"&{self.typ}"

class DynArray(TBase):
    def __init__(self, typ, is_mut):
        self.typ = typ
        self.is_mut = is_mut
        self.sym = None

    def resolve(self, sym):
        self.sym = sym

    def qualstr(self):
        if self.is_mut:
            return f"[]mut {self.typ.qualstr()}"
        return f"[]{self.typ.qualstr()}"

    def __eq__(self, other):
        if not isinstance(other, DynArray):
            return False
        return self.typ == other.typ and self.is_mut == other.is_mut

    def __str__(self):
        if self.is_mut:
            return f"[]mut {self.typ}"
        return f"[]{self.typ}"

class Slice(TBase):
    def __init__(self, typ, is_mut):
        self.typ = typ
        self.is_mut = is_mut
        self.sym = None

    def resolve(self, sym):
        self.sym = sym

    def qualstr(self):
        if self.is_mut:
            return f"[:]mut {self.typ.qualstr()}"
        return f"[:]{self.typ.qualstr()}"

    def __eq__(self, other):
        if not isinstance(other, Slice):
            return False
        return self.typ == other.typ and self.is_mut == other.is_mut

    def __str__(self):
        if self.is_mut:
            return f"[:]mut {self.typ}"
        return f"[:]{self.typ}"

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
    def __init__(self, typ, size, is_mut):
        self.typ = typ
        self.size = size
        self.is_mut = is_mut
        self.sym = None

    def resolve(self, sym):
        self.sym = sym

    def qualstr(self):
        if self.is_mut:
            return f"[{self.size}]mut {self.typ.qualstr()}"
        return f"[{self.size}]{self.typ.qualstr()}"

    def __eq__(self, other):
        if not isinstance(other, Array):
            return False
        return self.typ == other.typ and self.size == other.size and self.is_mut == other.is_mut

    def __str__(self):
        if self.is_mut:
            return f"[{self.size}]mut {self.typ}"
        return f"[{self.size}]{self.typ}"

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

class Func(TBase):
    def __init__(
        self, is_extern, abi, is_method, args, is_variadic, ret_typ,
        self_is_mut, self_is_ptr
    ):
        self.is_unsafe = abi != ABI.Rivet
        self.is_extern = is_extern
        self.abi = abi
        self.is_method = is_method
        self.self_is_mut = self_is_mut
        self.self_is_ptr = self_is_ptr
        self.args = args
        self.is_variadic = is_variadic
        self.ret_typ = ret_typ

    def info(self):
        return sym_Func(
            self.abi, True, self.is_extern, self.is_unsafe, self.is_method,
            self.is_variadic, self.stringify(False),
            self.args, self.ret_typ, False, not self.is_extern,
            token.Pos("", 0, 0, 0), self.self_is_mut, self.self_is_ptr
        )

    def stringify(self, qual):
        res = ""
        if self.is_extern:
            res += f'extern ({self.abi}) '
        res += "func("
        if self.is_method:
            if self.self_is_mut:
                res += "mut "
            elif self.self_is_ptr:
                res += "&"
            res += "self"
            if len(self.args) > 0:
                res += ", "
        for i, arg in enumerate(self.args):
            if arg.is_mut:
                res += "mut "
            if qual:
                res += arg.typ.qualstr()
            else:
                res += str(arg.typ)
            if i < len(self.args) - 1:
                res += ", "
        if self.is_extern and self.is_variadic:
            if len(self.args) > 0:
                res += ", "
            res += "..."
        res += ")"
        if str(self.ret_typ) != "void":
            res += " "
            if qual:
                res += self.ret_typ.qualstr()
            else:
                res += str(self.ret_typ)
        return res

    def qualstr(self):
        return str(self)

    def __str__(self):
        return self.stringify(False)

    def __eq__(self, got):
        if not isinstance(got, Func): return False
        if self.is_unsafe != got.is_unsafe:
            return False
        elif self.is_extern != got.is_extern:
            return False
        elif self.abi != got.abi:
            return False
        elif self.is_method != got.is_method:
            return False
        elif self.self_is_mut != got.self_is_mut:
            return False
        elif self.self_is_ptr != got.self_is_ptr:
            return False
        elif len(self.args) != len(got.args):
            return False
        for i, arg in enumerate(self.args):
            if arg.is_mut != got.args[i].is_mut:
                return False
            if arg.typ != got.args[i].typ:
                return False
        return self.ret_typ == got.ret_typ

class Option(TBase):
    def __init__(self, typ):
        self.typ = typ
        self.sym = None

    def is_pointer(self):
        if isinstance(self.typ, Type) and self.typ.is_boxed:
            return True
        tsym = self.typ.symbol()
        return self.typ.__class__ in (Ptr, Func, Boxedptr) or tsym.is_boxed()

    def qualstr(self):
        return f"?{self.typ.qualstr()}"

    def __eq__(self, other):
        if not isinstance(other, Option):
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
