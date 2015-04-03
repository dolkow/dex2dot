#!/usr/bin/env python3
#coding=utf8

from .function import createfunc
from .utf8dex import *

from os.path import dirname, splitext, exists, getmtime, isfile, islink
from select import select
from subprocess import Popen, PIPE
from tempfile import mkstemp
import os
import re
import sys

def _from_little_endian(bytes, signed):
	out = 0
	multiplier = 1
	for b in bytes:
		out += multiplier * b
		multiplier <<= 8
	if signed and (bytes[-1] & 0x80):
		out -= multiplier
	return out

def le2u(bytes):
	return _from_little_endian(bytes, False)
def le2s(bytes):
	return _from_little_endian(bytes, True)

class DexFile(object):
	def __init__(self, path):
		self.path = path
		if not exists(path):
			raise Exception('File does not exist', path);

	def _do_disass(self, disass_path):
		success = False
		fd, tmppath = mkstemp(dir=dirname(disass_path), text=True)
		try:
			child = Popen(['dexdump', '-d', self.path], stdout=fd, stderr=PIPE)
			_, err = child.communicate(timeout=10)
			if len(err.strip()) > 0:
				raise Exception('dexdump printed to stderr', err)
			if child.returncode != 0:
				raise Exception('dexdump returned non-zero', child.returncode)
			os.rename(tmppath, disass_path)
			success = True
		except TimeoutExpired:
			child.kill()
		finally:
			os.close(fd)
			if not success:
				os.remove(tmppath)

	def _get_disass_path(self):
		dfile = splitext(self.path)[0] + '.disass'
		need_new = True
		if exists(dfile):
			if islink(dfile) or not isfile(dfile):
				raise Exception('not a normal file', dfile)

			if getmtime(dfile) > getmtime(self.path):
				need_new = False
		if need_new:
			self._do_disass(dfile)
		return dfile

	def getfunc(self, clazz, mname, mtype):
		''' The args should be in "mangled" format. '''

		# TODO: will need this eventually
		#with open(self._get_disass_path(), encoding='utf-8-dex') as disass:
		with open(self._get_disass_path()) as disass:
			generator = (line.strip('\r\n') for line in disass)

			classre = re.compile(r"^\s*#\d+\s*: \(in (L\S+;)\)$")
			namere  = re.compile(r"^\s*name\s*: '(\S+)'$")
			typere  = re.compile(r"^\s*type\s*: '(\S+)'$")
			for line in generator:
				m = classre.match(line)
				if m and m.group(1) == clazz:
					# found the correct class
					# name and type lines should be immediately below.
					n = namere.match(next(generator)).group(1)
					t = typere.match(next(generator)).group(1)
					if n == mname and t == mtype:
						break # next loop, please!
			else:
				raise Exception('Method not found', clazz, mname, mtype)

			code = []
			info = []
			catchre = re.compile(r"^\s*catches\s+: ")
			for line in generator:
				m = catchre.match(line)
				if m:
					info.append(line)
					break # next loop!
				code.append(line)

			for line in generator:
				if len(line.strip()) == 0:
					break # empty line means we're done!
				info.append(line)

			return createfunc(self, clazz, mname, mtype, code, info)

	def read_bytes(self, start, count):
		from zipfile import ZipFile, is_zipfile
		if is_zipfile(self.path):
			z = ZipFile(self.path)
			data = z.read('classes.dex')
			return data[start:start+count]
		else:
			assert self.path.endswith('.dex')
			from mmap import mmap, PROT_READ
			with open(self.path, 'r+b') as f:
				with mmap(f.fileno(), 0, prot=PROT_READ) as m:
					return m[start:start+count]

	def read_switch_table(self, funcstart, tableaddr):
		# https://source.android.com/devices/tech/dalvik/dalvik-bytecode.html#packed-switch
		addr = funcstart + 2 * tableaddr
		bytes = self.read_bytes(addr, 4)
		ident = le2u(bytes[0:2])
		size  = le2u(bytes[2:4])

		out = {}
		assert ident in (0x0100, 0x0200)
		if ident == 0x0100:
			# packed switch
			bytes = self.read_bytes(addr+4, size * 4 + 4)
			first_key = le2s(bytes[0:4])
			for i in range(size):
				key = first_key + i
				off = 4 + i*4
				target = le2s(bytes[off:off+4])
				out[key] = target
		else:
			# sparse switch
			raise Exception('not yet implemented')
		return out
