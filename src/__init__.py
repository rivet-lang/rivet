# Copyright (C) 2022 The Rivet Team. All rights reserved.
# Use of this source code is governed by an MIT license
# that can be found in the LICENSE file.

import os

from .ast import sym, type
from . import (
    ast, token, prefs, report, utils,

    # stages
    parser, resolver, checker, codegen
)

from .codegen import c

class Compiler:
	def __init__(self, args):
		# `universe` is the mega-package where all the packages being
		# compiled reside.
		self.universe = sym.universe()

		# Primitive types.
		self.void_t = type.Type(self.universe[0])
		self.none_t = type.Type(self.universe[1])
		self.bool_t = type.Type(self.universe[2])
		self.rune_t = type.Type(self.universe[3])
		self.int8_t = type.Type(self.universe[4])
		self.int16_t = type.Type(self.universe[5])
		self.int32_t = type.Type(self.universe[6])
		self.int64_t = type.Type(self.universe[7])
		self.isize_t = type.Type(self.universe[8])
		self.uint8_t = type.Type(self.universe[9])
		self.uint16_t = type.Type(self.universe[10])
		self.uint32_t = type.Type(self.universe[11])
		self.uint64_t = type.Type(self.universe[12])
		self.usize_t = type.Type(self.universe[13])
		self.untyped_int_t = type.Type(self.universe[14])
		self.untyped_float_t = type.Type(self.universe[15])
		self.float32_t = type.Type(self.universe[16])
		self.float64_t = type.Type(self.universe[17])
		self.str_t = type.Type(self.universe[18])
		self.error_t = type.Type(self.universe[19])
		self.no_return_t = type.Type(self.universe[20])

		self.prefs = prefs.Prefs(args)
		self.source_files = []
		self.extern_packages = [
		    ast.ExternPkgInfo("core"),
		    # TODO(StunxFS): ast.ExternPkgInfo("std", ["core"])
		]

		self.pointer_size = 8 if self.prefs.target_bits == prefs.Bits.X64 else 4

		self.core_pkg = None
		self.str_struct = None # from `core` package
		self.slice_struct = None # from `core` package
		self.err_struct = None # from `core` package

		self.trait_to_string = None

		self.pkg_sym = None
		self.pkg_attrs = None
		self.mod_sym = None # for `mod mod_name;`

		self.resolver = resolver.Resolver(self)
		self.checker = checker.Checker(self)
		self.ast2rir = codegen.AST2RIR(self)
		self.cgen = c.Gen(self)

	def build_package(self):
		self.parse_files()
		if not self.prefs.check_syntax:
			self.resolver.resolve_files(self.source_files)
			if report.ERRORS > 0:
				self.abort()

			self.load_core_pkg()

			self.checker.check_files(self.source_files)
			if report.ERRORS > 0:
				self.abort()

			if not self.prefs.check:
				unique_rir = self.ast2rir.convert(self.source_files)
				if report.ERRORS > 0:
					self.abort()
				if self.prefs.emit_rir:
					with open(f"{self.prefs.pkg_name}.rir", "w+") as f:
						f.write(str(unique_rir))
				else:
					self.check_pkg_attrs()
					if self.prefs.target_backend == prefs.Backend.C:
						self.cgen.gen(unique_rir)
						c_file = f"{self.prefs.pkg_name}.ri.c"
						self.cgen.write_to_file(c_file)
						args = [
						    self.prefs.ccompiler, c_file,
						    *self.prefs.objects_to_link, "-fno-builtin",
						    "-Werror", "-m64" if self.prefs.target_bits
						    == prefs.Bits.X64 else "-m32",
						    *[f"-l{l}" for l in self.prefs.library_to_link],
						    *[f"-L{l}" for l in self.prefs.library_path], "-o",
						    self.prefs.pkg_output,
						]
						if self.prefs.build_mode == prefs.BuildMode.Release:
							args.append("-flto")
							args.append("-O3")
						else:
							args.append("-g")
						self.vlog(f"C compiler options: {args}")
						res = utils.execute(*args)
						if res.exit_code == 0:
							if not self.prefs.keep_c:
								os.remove(c_file)
						else:
							utils.error(
							    f"error while compiling the output C file `{c_file}`:\n{res.err}"
							)

	def load_core_pkg(self):
		if core_pkg := self.universe.find("core"):
			self.core_pkg = core_pkg
			if str_struct := self.core_pkg.find("_str"):
				self.str_struct = str_struct
			else:
				utils.error("cannot find type `_str` in package `core`")

			if slice_struct := self.core_pkg.find("_slice"):
				self.slice_struct = slice_struct
			else:
				utils.error("cannot find type `_slice` in package `core`")

			if err_struct := self.core_pkg.find("_error"):
				self.err_struct = err_struct
			else:
				utils.error("cannot find type `_error` in package `core`")

			if traits := self.core_pkg.find("traits"):
				if to_string := traits.find("ToString"):
					self.trait_to_string = to_string
		else:
			utils.error("package `core` not found")

	def check_pkg_attrs(self):
		pkg_folder = os.path.join(prefs.RIVET_DIR, "objs", self.prefs.pkg_name)
		for attr in self.pkg_attrs.attrs:
			if attr.name == "c_compile":
				if not os.path.exists(pkg_folder):
					os.mkdir(pkg_folder)
				cfile = os.path.realpath(attr.args[0].expr.lit)
				objfile = os.path.join(
				    pkg_folder,
				    f"{os.path.basename(cfile)}.{self.get_postfix()}.o"
				)
				self.prefs.objects_to_link.append(objfile)
				msg = f"c_compile: compiling object for C file `{cfile}`..."
				if os.path.exists(objfile):
					if os.path.getmtime(objfile) < os.path.getmtime(cfile):
						msg = f"c_compile: {objfile} is older than {cfile}, rebuilding..."
					else:
						continue
				self.vlog(msg)
				args = [
				    self.prefs.ccompiler, cfile, "-m64"
				    if self.prefs.target_bits == prefs.Bits.X64 else "-m32",
				    "-O3" if self.prefs.build_mode == prefs.BuildMode.Release
				    else "-g", f'-L{os.path.dirname(cfile)}', "-c", "-o",
				    objfile,
				]
				res = utils.execute(*args)
				if res.exit_code != 0:
					utils.error(
					    f"error while compiling the object file `{objfile}`:\n{res.err}"
					)
			else:
				report.error(
				    f"unknown package attribute `{attr.name}`", attr.pos
				)
		if report.ERRORS > 0:
			self.abort()

	def get_postfix(self):
		postfix = str(self.prefs.target_os).lower()
		postfix += "-"
		postfix += str(self.prefs.target_arch).lower()
		postfix += "-"
		postfix += str(self.prefs.target_bits).lower()
		postfix += "-"
		postfix += str(self.prefs.target_endian).lower()
		postfix += "-"
		postfix += str(self.prefs.target_backend).lower()
		postfix += "-"
		if self.prefs.build_mode == prefs.BuildMode.Debug:
			postfix += "debug"
		else:
			postfix += "release"
		postfix += f"-{self.prefs.ccompiler}"
		return postfix

	def parse_files(self):
		self.source_files = parser.Parser(self).parse_pkg()
		if report.ERRORS > 0:
			self.abort()

	# ========================================================
	def is_number(self, typ):
		return self.is_int(typ) or self.is_float(typ)

	def is_int(self, typ):
		return self.is_signed_int(typ) or self.is_unsigned_int(typ)

	def is_signed_int(self, typ):
		return typ in (
		    self.int8_t, self.int16_t, self.int32_t, self.int64_t, self.isize_t,
		    self.untyped_int_t
		)

	def is_unsigned_int(self, typ):
		return typ in (
		    self.uint8_t, self.uint16_t, self.uint32_t, self.uint64_t,
		    self.usize_t
		)

	def is_float(self, typ):
		return typ in (self.float32_t, self.float64_t, self.untyped_float_t)

	def untyped_to_type(self, typ):
		if typ == self.untyped_int_t:
			return self.int32_t
		elif typ == self.untyped_float_t:
			return self.float64_t
		return typ

	def num_bits(self, typ):
		if self.is_int(typ):
			return self.int_bits(typ)
		return self.float_bits(typ)

	def int_bits(self, typ):
		typ_sym = typ.get_sym()
		if typ_sym.kind == sym.TypeKind.UntypedInt:
			return 75 # only for checker
		elif typ_sym.kind in (sym.TypeKind.Int8, sym.TypeKind.Uint8):
			return 8
		elif typ_sym.kind in (sym.TypeKind.Int16, sym.TypeKind.Uint16):
			return 16
		elif typ_sym.kind in (sym.TypeKind.Int32, sym.TypeKind.Uint32):
			return 32
		elif typ_sym.kind in (sym.TypeKind.Int64, sym.TypeKind.Uint64):
			return 64
		elif typ_sym.kind in (sym.TypeKind.Isize, sym.TypeKind.Usize):
			return 32 if self.prefs.target_bits == prefs.Bits.X32 else 64
		else:
			return -1

	def float_bits(self, typ):
		typ_sym = typ.get_sym()
		if typ_sym.kind == sym.TypeKind.Float32:
			return 32
		elif typ_sym.kind in (sym.TypeKind.Float64, sym.TypeKind.UntypedFloat):
			return 64
		else:
			return -1

	# Returns the size and alignment (in bytes) of `typ`, similarly to
	# C's `sizeof(T)` and `_Alignof(T)`.
	def type_size(self, typ):
		if isinstance(typ, (type.Result, type.Optional)):
			return self.type_size(typ.typ)
		elif isinstance(typ, (type.Ptr, type.Ref)):
			return self.pointer_size, self.pointer_size
		elif isinstance(typ, type.Fn):
			return self.pointer_size, self.pointer_size
		return self.type_symbol_size(typ.get_sym())

	def type_symbol_size(self, sy):
		if sy.size != -1:
			return sy.size, sy.align
		size, align = 0, 0
		if sy.kind in (
		    sym.TypeKind.Placeholder, sym.TypeKind.Void, sym.TypeKind.None_,
		    sym.TypeKind.NoReturn, sym.TypeKind.TypeArg
		):
			pass
		elif sy.kind == sym.TypeKind.Alias:
			size, align = self.type_size(sy.info.parent)
		elif sy.kind in (sym.TypeKind.Usize, sym.TypeKind.Isize):
			size, align = self.pointer_size, self.pointer_size
		elif sy.kind in (
		    sym.TypeKind.Int8, sym.TypeKind.Uint8, sym.TypeKind.Bool,
		    sym.TypeKind.ErrType
		):
			size, align = 1, 1
		elif sy.kind in (sym.TypeKind.Int16, sym.TypeKind.Uint16):
			size, align = 2, 2
		elif sy.kind in (
		    sym.TypeKind.Int32, sym.TypeKind.Uint32, sym.TypeKind.Rune,
		    sym.TypeKind.Float32, sym.TypeKind.UntypedInt
		):
			size, align = 4, 4
		elif sy.kind in (
		    sym.TypeKind.Int64, sym.TypeKind.Uint64, sym.TypeKind.Float64,
		    sym.TypeKind.UntypedFloat
		):
			size, align = 8, 8
		elif sy.kind == sym.TypeKind.Enum:
			size, align = self.type_size(sy.info.underlying_typ)
		elif sy.kind == sym.TypeKind.Array:
			elem_size, elem_align = self.type_size(sy.info.elem_typ)
			size, align = int(sy.info.size.lit) * elem_size, elem_align
		elif sy.kind == sym.TypeKind.Str:
			size, align = self.type_symbol_size(self.str_struct)
		elif sy.kind == sym.TypeKind.Slice:
			size, align = self.type_symbol_size(self.slice_struct)
		elif sy.kind == sym.TypeKind.Trait:
			size, align = self.pointer_size * 2, self.pointer_size
		elif sy.kind == sym.TypeKind.Union:
			for vtyp in sy.info.variants:
				v_size, v_alignment = self.type_size(vtyp)
				if v_size > size:
					size = v_size
					align = v_alignment
			if not sy.info.is_c_union:
				# `tag: i32` field
				size += 4
		elif sy.kind in (sym.TypeKind.Struct, sym.TypeKind.Tuple):
			total_size = 0
			max_alignment = 0
			types = list(
			    map(lambda it: it.typ, sy.fields)
			) if sy.kind == sym.TypeKind.Struct else sy.info.types
			for ftyp in types:
				field_size, alignment = self.type_size(ftyp)
				if alignment > max_alignment:
					max_alignment = alignment
				total_size = self.round_up(total_size, alignment) + field_size
			size = self.round_up(total_size, max_alignment)
			align = max_alignment
		else:
			raise Exception(f"type_size(): unsupported type `{sy.qualname()}`")
		sy.size = size
		sy.align = align
		return size, align

	# Rounds the number `n` up to the next multiple `multiple`.
	# NOTE: `multiple` must be a power of 2.
	def round_up(self, n, multiple):
		return (n + multiple - 1) & (-multiple)

	def evalue_comptime_condition(self, cond):
		if isinstance(cond, ast.BoolLiteral):
			return cond.lit
		elif isinstance(cond, ast.Ident):
			if cond.is_comptime:
				report.error("invalid comptime condition", cond.pos)
			# operating systems
			elif cond.name in ("_LINUX_", "_WINDOWS_"):
				return self.prefs.target_os.equals_to_string(cond.name)
			# architectures
			elif cond.name in ("_AMD64_", "_i386_"):
				return self.prefs.target_arch.equals_to_string(cond.name)
			# bits
			elif cond.name in ("_x32_", "_x64_"):
				if cond.name == "_x32_":
					return self.prefs.target_bits == prefs.Bits.X32
				else:
					return self.prefs.target_bits == prefs.Bits.X64
			# endian
			elif cond.name in ("_LITTLE_ENDIAN_", "_BIG_ENDIAN_"):
				if cond.name == "_LITTLE_ENDIAN_":
					return self.prefs.target_endian == prefs.Endian.Little
				else:
					return self.prefs.target_endian == prefs.Endian.Big
			else:
				if cond.name.startswith("_") and cond.name.endswith("_"):
					report.error(f"unknown builtin flag: `{cond}`", cond.pos)
					return False
				return cond.name in self.prefs.flags
		elif isinstance(cond, ast.UnaryExpr):
			if cond.op == token.Kind.Bang:
				return not self.evalue_comptime_condition(cond.right)
			else:
				report.error(f"expected `!`, found token `{cond.op}`", cond.pos)
		elif isinstance(cond, ast.BinaryExpr):
			if cond.op in (token.Kind.KeyAnd, token.Kind.KeyOr):
				if cond.op == token.Kind.KeyAnd:
					return self.evalue_comptime_condition(
					    cond.left
					) and self.evalue_comptime_condition(cond.right)
				else:
					return self.evalue_comptime_condition(
					    cond.left
					) or self.evalue_comptime_condition(cond.right)
			else:
				report.error("invalid comptime condition", cond.pos)
		elif isinstance(cond, ast.ParExpr):
			return self.evalue_comptime_condition(cond.expr)
		else:
			report.error("invalid comptime condition", cond.pos)
		return False

	# ========================================================

	def vlog(self, msg):
		if self.prefs.is_verbose:
			utils.eprint(">>", msg)

	def abort(self):
		if report.ERRORS == 1:
			msg = f"could not compile package `{self.prefs.pkg_name}`, aborting due to previous error"
		else:
			msg = f"could not compile package `{self.prefs.pkg_name}`, aborting due to {report.ERRORS} previous errors"
		if report.WARNS > 0:
			word = "warning" if report.WARNS == 1 else "warnings"
			msg += f"; {report.WARNS} {word} emitted"
		utils.error(msg)
		exit(1)

def main(args):
	comp = Compiler(args)
	comp.build_package()
