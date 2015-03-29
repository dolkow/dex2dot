from function import createfunc
from os.path import dirname, splitext, exists, getmtime, isfile, islink
from select import select
from subprocess import Popen, PIPE
from tempfile import mkstemp
import os
import re
import sys
import utf8dex

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

if __name__ == '__main__':
	import sys
	df = DexFile(sys.argv[1])
	df.getfunc(*sys.argv[2:5])
