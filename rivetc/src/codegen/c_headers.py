# Copyright (C) 2023 The Rivet Developers. All rights reserved.
# Use of this source code is governed by an MIT license that can
# be found in the LICENSE file.

from ..utils import full_version

HEADER = f"// Auto-generated by {full_version()}" + """. DO NOT MODIFY!

#include <stddef.h>
#include <stdint.h>

#if defined(_WIN32) || defined(__CYGWIN__)
	#define RIVET_EXPORT extern __declspec(dllexport)
	#define RIVET_LOCAL static
#else
	// 4 < GCC < 5 is used by some older Ubuntu LTS and CentOS versions, and does
	// not support __has_attribute(visibility):
	#ifndef __has_attribute
		#define __has_attribute(x) 0 // Compatibility with non-clang compilers.
	#endif

	#if (defined(__GNUC__) && (__GNUC__ >= 4)) || (defined(__clang__) && __has_attribute(visibility))
		#ifdef ARM
			#define RIVET_EXPORT extern __attribute__((externally_visible,visibility("default")))
		#else
			#define RIVET_EXPORT extern __attribute__((visibility("default")))
		#endif

		#if defined(__clang__) && (defined(_VUSECACHE) || defined(_VBUILDMODULE))
			#define RIVET_LOCAL static
		#else
			#define RIVET_LOCAL __attribute__ ((visibility ("hidden")))
		#endif
	#else
		#define RIVET_EXPORT extern
		#define RIVET_LOCAL static
	#endif
#endif

#if !defined(RIVET_NEVER)
	#if defined(__TINYC__)
		#include <stdnoreturn.h>
		#define RIVET_NEVER noreturn
	#endif

	#if !defined(__TINYC__) && defined(__STDC_VERSION__) && __STDC_VERSION__ >= 201112L
	   #define RIVET_NEVER _Noreturn
	#elif defined(__GNUC__) && __GNUC__ >= 2
	   #define RIVET_NEVER __attribute__((noreturn))
	#endif

	#ifndef RIVET_NEVER
		#define RIVET_NEVER
	#endif
#endif

typedef int8_t int8;
typedef int16_t int16;
typedef int32_t int32;
typedef int64_t int64;
typedef uint8_t uint8;
typedef uint16_t uint16;
typedef uint32_t uint32;
typedef uint64_t uint64;
typedef ptrdiff_t isize;
typedef size_t usize;
typedef int64 comptime_int;

typedef uint8 bool;
typedef uint32 rune;

typedef float float32;
typedef double float64;
typedef float64 comptime_float;

"""

RIVET_BREAKPOINT = """#if !defined(RIVET_BREAKPOINT)
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

"""
