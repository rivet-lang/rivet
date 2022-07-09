# Copyright (C) 2022 The Rivet Team. All rights reserved.
# Use of this source code is governed by an MIT license
# that can be found in the LICENSE file.

from . import *
from .. import ast, utils
from ..ast import sym, type
from ..utils import full_version

# NOTE: some of the words in `C_RESERVED` are not reserved in C, but are
# in C++, or have special meaning in Rivet, thus need escaping too.
# `small` should not be needed, but see:
# https://stackoverflow.com/questions/5874215/what-is-rpcndr-h
C_RESERVED = [
    'auto', 'bool', 'break', 'case', 'char', 'class', 'complex', 'const',
    'continue', 'default', 'delete', 'do', 'double', 'else', 'enum', 'export',
    'extern', 'false', 'float', 'for', 'goto', 'if', 'inline', 'int', 'long',
    'namespace', 'new', 'register', 'restrict', 'return', 'short', 'signed',
    'sizeof', 'static', 'struct', 'switch', 'typedef', 'typename', 'union',
    'unix', 'unsigned', 'void', 'volatile', 'while', 'template', 'true', 'small'
]

def c_escape(kw):
	if kw in C_RESERVED:
		return f"_ri_{kw}"
	return kw

HEADER = f"// Auto-generated by {full_version()}" + """. DO NOT MODIFY!

#include <stdint.h>
#include <stddef.h>

#if defined(_WIN32) || defined(__CYGWIN__)
	#define RIVET_EXPORTED_SYMBOL extern __declspec(dllexport)
	#define RIVET_LOCAL_SYMBOL static
#else
	// 4 < GCC < 5 is used by some older Ubuntu LTS and CentOS versions, and does
	// not support __has_attribute(visibility):
	#ifndef __has_attribute
		#define __has_attribute(x) 0 // Compatibility with non-clang compilers.
	#endif

	#if (defined(__GNUC__) && (__GNUC__ >= 4)) || (defined(__clang__) && __has_attribute(visibility))
		#ifdef ARM
			#define RIVET_EXPORTED_SYMBOL extern __attribute__((externally_visible,visibility("default")))
		#else
			#define RIVET_EXPORTED_SYMBOL extern __attribute__((visibility("default")))
		#endif

		#if defined(__clang__) && (defined(_VUSECACHE) || defined(_VBUILDMODULE))
			#define RIVET_LOCAL_SYMBOL static
		#else
			#define RIVET_LOCAL_SYMBOL __attribute__ ((visibility ("hidden")))
		#endif
	#else
		#define RIVET_EXPORTED_SYMBOL extern
		#define RIVET_LOCAL_SYMBOL static
	#endif
#endif

#if !defined(RIVET_NORETURN)
	#if defined(__TINYC__)
		#include <stdnoreturn.h>
		#define RIVET_NORETURN noreturn
	#endif

	#if !defined(__TINYC__) && defined(__STDC_VERSION__) && __STDC_VERSION__ >= 201112L
	   #define RIVET_NORETURN _Noreturn
	#elif defined(__GNUC__) && __GNUC__ >= 2
	   #define RIVET_NORETURN __attribute__((noreturn))
	#endif

	#ifndef RIVET_NORETURN
		#define RIVET_NORETURN
	#endif
#endif

#if !defined(RIVET_BREAKPOINT)
	#if (defined (__i386__) || defined (__x86_64__)) && defined (__GNUC__) && __GNUC__ >= 2
		#define RIVET_BREAKPOINT        { __asm__ __volatile__ (\"int $03\"); }
	#elif (defined (_MSC_VER) || defined (__DMC__)) && defined (_M_IX86)
		#define RIVET_BREAKPOINT        { __asm int 3h }
	#elif defined (_MSC_VER)
		#define RIVET_BREAKPOINT        { __debugbreak(); }
	#elif defined (__alpha__) && !defined(__osf__) && defined (__GNUC__) && __GNUC__ >= 2
		#define RIVET_BREAKPOINT        { __asm__ __volatile__ (\"bpt\"); }
	#elif defined (__APPLE__)
		#define RIVET_BREAKPOINT        { __builtin_trap(); }
	#else /* !__i386__ && !__alpha__ */
		#define RIVET_BREAKPOINT        { raise (SIGTRAP); }
	#endif
#endif

#if !defined(RIVET_UNREACHABLE)
	#if defined(__GNUC__) && !defined(__clang__)
		#define RIVET_GCC_VERSION  (__GNUC__ * 10000L + __GNUC_MINOR__ * 100L + __GNUC_PATCHLEVEL__)
		#if (RIVET_GCC_VERSION >= 40500L)
			#define RIVET_UNREACHABLE()  do { __builtin_unreachable(); } while (0)
		#endif
	#endif

	#if defined(__clang__) && defined(__has_builtin)
		#if __has_builtin(__builtin_unreachable)
			#define RIVET_UNREACHABLE()  do { __builtin_unreachable(); } while (0)
		#endif
	#endif

	#if defined(__FreeBSD__) && defined(__TINYC__)
		#define RIVET_UNREACHABLE() do { } while (0)
	#endif

	#ifndef RIVET_UNREACHABLE
		#define RIVET_UNREACHABLE() do { } while (0)
	#endif
#endif

typedef int8_t i8;
typedef int16_t i16;
typedef int32_t i32;
typedef int64_t i64;

typedef uint8_t u8;
typedef uint16_t u16;
typedef uint32_t u32;
typedef uint64_t u64;

typedef float f32;
typedef double f64;

typedef i64 untyped_int;
typedef f64 untyped_float;

typedef u8 bool;
typedef u32 rune;

typedef ptrdiff_t isize;
typedef size_t usize;
"""

class Gen:
	def __init__(self, comp):
		self.comp = comp
		self.inside_func_ret_typ = False
		self.typedefs = utils.Builder()
		self.types = utils.Builder()
		self.protos = utils.Builder()
		self.statics = utils.Builder()
		self.out = utils.Builder()

	def gen_rir(self, rir_file):
		self.gen_types(rir_file.types)
		self.gen_externs(rir_file.externs)
		self.gen_statics(rir_file.statics)
		self.gen_decls(rir_file.decls)

	def get_output(self):
		res = utils.Builder()
		res.writeln(HEADER)
		res.writeln(str(self.typedefs))
		res.write(str(self.types))
		res.writeln()
		res.writeln(str(self.protos))
		res.writeln(str(self.statics))
		res.writeln(
		    """void _R9init_argsZ(i32 __argc, u8** __argv) {
  _R4core4ARGS = (_R4core6_slice){
	.ptr=malloc(sizeof(_R4core4_str) * __argc),
	.elem_size=sizeof(_R4core4_str), .len=__argc
  };
  for (int i = 0; i < __argc; i++) {
	u8* arg = __argv[i];
	_R4core4_str tmp = _R4core4_str9from_cstrF(arg);
	_R4core6_slice3setM(&_R4core4ARGS, i, &tmp);
  }
}

void _R9drop_argsZ(void) {
	free(_R4core4ARGS.ptr);
}"""
		)
		res.write(str(self.out))
		res.writeln("int main(i32 __argc, char** __argv) {")
		pkg_main = f"_R{len(self.comp.prefs.pkg_name)}{self.comp.prefs.pkg_name}4mainF"
		res.writeln(
		    f"  _R4core10rivet_mainF(__argc, (u8**)__argv, {pkg_main});"
		)
		res.writeln("  return 0;")
		res.writeln("}")
		return str(res)

	def write_to_file(self, filename):
		with open(filename, "w+") as f:
			f.write(self.get_output())

	def write(self, txt):
		self.out.write(txt)

	def writeln(self, txt = ""):
		self.out.writeln(txt)

	def gen_types(self, types):
		for i, t in enumerate(types):
			if isinstance(t, Alias):
				keyword = "struct " if t.sy.info.elem_typ.get_sym(
				).kind in (sym.TypeKind.Struct, sym.TypeKind.Tuple) else ""
				self.types.writeln(
				    f"typedef {keyword}{self.gen_type_str(t.sy.info.elem_typ)} {t.name} [{t.sy.info.size}];\n"
				)
			elif isinstance(t, RiUnion):
				self.typedefs.writeln(f"typedef struct {t.name} {t.name};")
				self.types.writeln(f"struct {t.name} {{")
				self.types.writeln("  union {")
				for v in t.variants:
					self.types.writeln(
					    f"    {self.gen_type_str(v)} {mangle_type(v)};"
					)
				self.types.writeln("  };")
				self.types.writeln("  i64 idx;")
				self.types.writeln("};")
				if i < len(types) - 1:
					self.types.writeln()
			else:
				keyword = "union" if t.is_union else "struct"
				self.typedefs.writeln(f"typedef {keyword} {t.name} {t.name};")
				if t.is_opaque:
					self.types.writeln(f"{keyword} {t.name};")
				else:
					self.types.writeln(f"{keyword} {t.name} {{")
					for f in t.fields:
						fname = c_escape(f.name)
						if isinstance(f.typ, type.Fn):
							self.types.writeln(
							    f"  {self.wrap_fn_ptr_str(f.typ, fname)};"
							)
						else:
							self.types.writeln(
							    f"  {self.gen_type_str(f.typ)} {fname};"
							)
					self.types.writeln("};")
				if i < len(types) - 1:
					self.types.writeln()
		self.writeln()

	def gen_externs(self, externs):
		for extern in externs:
			self.protos.write("extern ")
			if extern.ret_typ == self.comp.no_return_t:
				self.protos.write("RIVET_NORETURN ")
			self.inside_func_ret_typ = True
			self.protos.write(self.gen_type_str(extern.ret_typ))
			self.inside_func_ret_typ = False
			self.protos.write(f" {extern.name}(")
			if len(extern.args) == 0:
				self.protos.write("void")
			else:
				for i, arg in enumerate(extern.args):
					if isinstance(arg.typ, type.Fn):
						self.protos.write(
						    self.wrap_fn_ptr_str(arg.typ, arg.name)
						)
					else:
						self.protos.write(self.gen_type_str(arg.typ))
						self.protos.write(" ")
						self.protos.write(arg.name)
					if i < len(extern.args) - 1:
						self.protos.write(", ")
				if extern.is_variadic:
					self.protos.write(", ...")
			self.protos.writeln(");")
		self.protos.writeln()

	def gen_statics(self, statics):
		for s in statics:
			if s.is_extern:
				self.statics.write("extern ")
			elif not s.is_pub:
				self.statics.write("RIVET_LOCAL_SYMBOL ")
			self.statics.write(self.gen_type_str(s.typ))
			self.statics.writeln(f" {s.name};")

	def gen_decls(self, decls):
		for decl in decls:
			self.gen_decl(decl)

	def gen_decl(self, decl):
		if isinstance(decl, VTable):
			self.statics.writeln(
			    f"static {decl.structure} {decl.name}[{decl.implement_nr}] = {{"
			)
			for i, ft in enumerate(decl.funcs):
				self.statics.writeln('  {')
				for f, impl in ft.items():
					self.statics.writeln(f'    .{f} = (void*){impl}')
				self.statics.write("  }")
				if i < len(decl.funcs) - 1:
					self.statics.writeln(",")
				else:
					self.statics.writeln()
			self.statics.writeln("};")
		elif isinstance(decl, FnDecl):
			if decl.ret_typ == self.comp.no_return_t:
				self.write("RIVET_NORETURN ")
				self.protos.write("RIVET_NORETURN ")
			if decl.is_pub:
				self.write("RIVET_EXPORTED_SYMBOL ")
			else:
				self.write("RIVET_LOCAL_SYMBOL ")
			self.inside_func_ret_typ = isinstance(decl.ret_typ, type.Array)
			ret_typ_str = self.gen_type_str(decl.ret_typ)
			self.protos.write(ret_typ_str)
			self.write(ret_typ_str)
			self.inside_func_ret_typ = False
			self.protos.write(f" {decl.name}(")
			self.write(f" {decl.name}(")
			if len(decl.args) == 0:
				self.write("void")
				self.protos.write("void")
			else:
				for i, arg in enumerate(decl.args):
					arg_name = c_escape(arg.name)
					if isinstance(arg.typ, type.Fn):
						self.wrap_fn_ptr(arg.typ, arg_name)
						self.protos.write(
						    self.wrap_fn_ptr_str(arg.typ, arg_name)
						)
					else:
						self.gen_type(arg.typ)
						self.write(" ")
						self.write(arg_name)
						self.protos.write(
						    f"{self.gen_type_str(arg.typ)} {arg_name}"
						)
					if i < len(decl.args) - 1:
						self.write(", ")
						self.protos.write(", ")
			self.protos.writeln(");")
			self.writeln(") {")
			self.gen_instrs(decl.bb)
			self.writeln("}\n")

	def gen_instrs(self, insts):
		for inst in insts:
			if isinstance(inst, Label):
				self.writeln()
			else:
				self.write("  ")
			if isinstance(inst, Skip):
				pass # skip
			elif isinstance(inst, Comment):
				self.writeln(f"/* {inst.text} */")
			elif isinstance(inst, Label):
				self.writeln(f"{inst.label}: {{}}")
			elif isinstance(inst, Alloca):
				self.gen_type(inst.typ)
				if isinstance(
				    inst.inst, Inst
				) and inst.inst.kind == InstKind.Call and isinstance(
				    inst.inst.args[0], Ident
				) and isinstance(inst.inst.args[0].typ, type.Array):
					self.write("_Ret")
				self.write(f" {inst.name} = ")
				self.gen_expr(inst.inst)
				self.writeln(";")
			elif isinstance(inst, Inst):
				self.gen_inst(inst)
				if inst.kind == InstKind.DbgStmtLine:
					self.writeln()
				else:
					self.writeln(";")

	def gen_inst(self, inst):
		if inst.kind == InstKind.Nop:
			self.write("/* NOP */")
		elif inst.kind == InstKind.Alloca:
			if isinstance(inst.args[0].typ, type.Fn):
				self.wrap_fn_ptr(inst.args[0].typ, inst.args[0].name)
			else:
				self.gen_type(inst.args[0].typ)
				self.write(" ")
				self.gen_expr(inst.args[0])
		elif inst.kind in (InstKind.Store, InstKind.StorePtr):
			arg0 = inst.args[0]
			arg1 = inst.args[1]
			is_ident_or_selector = isinstance(arg0, Ident
			                                  ) or isinstance(arg0, Selector)
			arg0_sym = arg0.typ.get_sym(
			) if is_ident_or_selector else self.comp.void_t
			if is_ident_or_selector and (
			    isinstance(arg0.typ, type.Array)
			    or arg0_sym.kind == sym.TypeKind.Array
			):
				# use memcpy for arrays
				self.write("memcpy(")
				if inst.kind != InstKind.StorePtr:
					self.write("&")
				self.gen_expr(arg0)
				self.write(", ")
				if not (isinstance(arg1, Ident) and arg1.use_arr_field):
					self.write("&")
				self.gen_expr(arg1)
				size, _ = self.comp.type_size(arg0.typ)
				self.write(f", {size})")
			else:
				if inst.kind == InstKind.StorePtr:
					self.write("(*")
				self.gen_expr(arg0)
				if inst.kind == InstKind.StorePtr:
					self.write(")")
				self.write(" = ")
				self.gen_expr(arg1)
		elif inst.kind == InstKind.LoadPtr:
			self.write("(*(")
			self.gen_expr(inst.args[0])
			self.write("))")
		elif inst.kind == InstKind.GetElementPtr:
			self.write("(")
			self.gen_expr(inst.args[0])
			self.write(" + ")
			self.gen_expr(inst.args[1])
			self.write(")")
		elif inst.kind == InstKind.GetRef:
			arg0 = inst.args[0]
			if isinstance(
			    arg0, (Ident, Selector, ArrayLiteral)
			) or (isinstance(arg0, Inst) and arg0.kind == InstKind.LoadPtr):
				self.write("(&")
				self.gen_expr(arg0)
				if isinstance(arg0, ArrayLiteral):
					self.write("[0]")
				self.write(")")
			else:
				self.write(f"(&(({self.gen_type_str(arg0.typ)}[]){{ ")
				self.gen_expr(arg0)
				self.write(" }[0]))")
		elif inst.kind == InstKind.Cast:
			self.write("((")
			self.gen_expr(inst.args[1])
			self.write(")(")
			self.gen_expr(inst.args[0])
			self.write("))")
		elif inst.kind == InstKind.Cmp:
			self.gen_expr(inst.args[1])
			self.write(" ")
			self.gen_expr(inst.args[0])
			self.write(" ")
			self.gen_expr(inst.args[2])
		elif inst.kind == InstKind.Select:
			self.write("(")
			self.gen_expr(inst.args[0])
			self.write(") ? (")
			self.gen_expr(inst.args[1])
			self.write(") : (")
			self.gen_expr(inst.args[2])
			self.write(")")
		elif inst.kind == InstKind.DbgStmtLine:
			self.write(f'#line {inst.args[1].name} "{inst.args[0].name}"')
		elif inst.kind == InstKind.Unreachable:
			self.write("RIVET_UNREACHABLE()")
		elif inst.kind == InstKind.Breakpoint:
			self.write("RIVET_BREAKPOINT()")
		elif inst.kind in (
		    InstKind.Add, InstKind.Sub, InstKind.Mult, InstKind.Div,
		    InstKind.Mod, InstKind.BitAnd, InstKind.BitOr, InstKind.BitXor,
		    InstKind.Lshift, InstKind.Rshift
		):
			self.gen_expr(inst.args[0])
			if inst.kind == InstKind.Add: self.write(" + ")
			elif inst.kind == InstKind.Sub: self.write(" - ")
			elif inst.kind == InstKind.Mult: self.write(" * ")
			elif inst.kind == InstKind.Div: self.write(" / ")
			elif inst.kind == InstKind.Mod: self.write(" % ")
			elif inst.kind == InstKind.BitAnd: self.write(" & ")
			elif inst.kind == InstKind.BitOr: self.write(" | ")
			elif inst.kind == InstKind.BitXor: self.write(" ^ ")
			elif inst.kind == InstKind.Lshift: self.write(" << ")
			elif inst.kind == InstKind.Rshift: self.write(" >> ")
			self.gen_expr(inst.args[1])
		elif inst.kind in (InstKind.Inc, InstKind.Dec):
			self.gen_expr(inst.args[0])
			if inst.kind == InstKind.Inc:
				self.write("++")
			else:
				self.write("--")
		elif inst.kind in (InstKind.BitNot, InstKind.BooleanNot, InstKind.Neg):
			if inst.kind == InstKind.BooleanNot:
				self.write("!(")
			elif inst.kind == InstKind.Neg:
				self.write("-")
			else:
				self.write("~")
			self.gen_expr(inst.args[0])
			if inst.kind == InstKind.BooleanNot:
				self.write(")")
		elif inst.kind == InstKind.Br:
			if len(inst.args) == 1:
				self.write(f"goto {inst.args[0].name}")
			else:
				self.write("if (")
				self.gen_expr(inst.args[0])
				self.write(
				    f") goto {inst.args[1].name}; else goto {inst.args[2].name}"
				)
		elif inst.kind == InstKind.Call:
			arg0 = inst.args[0]
			args = inst.args[1:]
			if isinstance(arg0, Ident):
				self.write(arg0.name)
			else:
				self.gen_expr(arg0)
			self.write("(")
			for i, arg in enumerate(args):
				self.gen_expr(arg)
				if i < len(args) - 1:
					self.write(", ")
			self.write(")")
		elif inst.kind == InstKind.Ret:
			self.write("return")
			if len(inst.args) == 1:
				self.write(" ")
				arg0 = inst.args[0]
				if isinstance(arg0, ArrayLiteral):
					arg0_sym = arg0.typ.get_sym()
					self.write(f"({arg0_sym.mangled_name}_Ret){{.arr=")
					self.gen_expr(arg0)
					self.write("}")
				else:
					self.gen_expr(arg0)
		else:
			raise Exception(inst) # unreachable

	def gen_expr(self, expr):
		if isinstance(expr, Skip):
			self.write("/* <skip> */")
		elif isinstance(expr, Inst):
			self.gen_inst(expr)
		elif isinstance(expr, NoneLiteral):
			self.write("NULL")
		elif isinstance(expr, IntLiteral):
			if expr.value() == MAX_INT64:
				# NOTE: `-9223372036854775808` is wrong because C compilers
				# parse literal values without sign first, and `9223372036854775808`
				# overflows `i64`, hence the consecutive subtraction by `1`.
				self.write("(-9223372036854775807 - 1)")
			else:
				self.write(expr.lit)
			if self.comp.is_unsigned_int(expr.typ):
				self.write("U")
			if self.comp.num_bits(expr.typ) == 64:
				self.write("L")
		elif isinstance(expr, FloatLiteral):
			self.write(expr.lit)
			if expr.typ == self.comp.float32_t:
				self.write("f")
		elif isinstance(expr, RuneLiteral):
			self.write(expr.lit)
		elif isinstance(expr, StringLiteral):
			if isinstance(expr.typ, type.Ptr):
				self.write(f'(u8*)"{expr.lit}"')
			else:
				self.write(
				    f'(_R4core4_str){{.ptr=((u8*)"{expr.lit}"), .len={expr.len}U}}'
				)
		elif isinstance(expr, ArrayLiteral):
			self.write("(")
			self.gen_type(expr.typ)
			if expr.is_variadic_init:
				self.write("[]")
			self.write("){ ")
			for i, e in enumerate(expr.elems):
				self.gen_expr(e)
				if i < len(expr.elems) - 1:
					self.write(", ")
			self.write(" }")
		elif isinstance(expr, Ident):
			if expr.use_arr_field:
				self.write(expr.name)
				self.write(".arr")
			else:
				self.write(c_escape(expr.name))
		elif isinstance(expr, Selector):
			self.gen_expr(expr.left)
			self.write(".")
			self.write(c_escape(expr.name.name))
		elif isinstance(expr, Name):
			self.write(c_escape(expr.name))
		elif isinstance(expr, Type):
			self.gen_type(expr.typ)

	def gen_type(self, typ):
		self.write(self.gen_type_str(typ))

	def gen_type_str(self, typ):
		res = utils.Builder()
		if isinstance(typ, type.Result):
			res.write(typ.sym.mangled_name)
		elif isinstance(typ, type.Optional):
			if isinstance(typ.typ, (type.Ptr, type.Ref)):
				res.write(self.gen_type_str(typ.typ))
			else:
				res.write(typ.sym.mangled_name)
		elif isinstance(typ, (type.Ptr, type.Ref)):
			res.write(self.gen_type_str(typ.typ))
			res.write("*")
		elif isinstance(typ, type.Fn):
			res.write(self.wrap_fn_ptr_str(typ, ""))
		elif isinstance(typ, type.Slice):
			res.write("_R4core6_slice")
		elif isinstance(typ, type.Array):
			if typ.sym:
				res.write(typ.sym.mangled_name)
				if self.inside_func_ret_typ:
					res.write("_Ret")
					if not typ.sym.info.has_wrapper:
						typ.sym.info.has_wrapper = True
						name = f"{typ.sym.mangled_name}_Ret"
						self.typedefs.writeln(f"typedef struct {name} {name};")
						self.types.writeln(
						    f"struct {name} {{ {self.gen_type_str(typ.sym.info.elem_typ)}* arr; }};"
						)
		elif typ in (self.comp.void_t, self.comp.no_return_t):
			res.write("void")
		elif self.comp.is_number(typ) or typ in (
		    self.comp.bool_t, self.comp.rune_t
		):
			res.write(typ.sym.name)
		elif typ.sym:
			if typ.sym.kind == sym.TypeKind.Enum:
				res.write(self.gen_type_str(typ.sym.info.underlying_typ))
			else:
				res.write(mangle_symbol(typ.sym))
		return str(res)

	def wrap_fn_ptr(self, fn_ptr, name):
		self.write(self.wrap_fn_ptr_str(fn_ptr, name))

	def wrap_fn_ptr_str(self, fn_ptr, name):
		res = utils.Builder()
		res.write(self.gen_type_str(fn_ptr.ret_typ))
		res.write(f" (*{name})(")
		if fn_ptr.is_method:
			res.write("void* self")
			if len(fn_ptr.args) > 0:
				res.write(", ")
		if len(fn_ptr.args) == 0:
			if not fn_ptr.is_method: res.write("void")
		else:
			for i, arg in enumerate(fn_ptr.args):
				res.write(self.gen_type_str(arg))
				if i < len(fn_ptr.args) - 1:
					res.write(", ")
		res.write(")")
		return str(res)