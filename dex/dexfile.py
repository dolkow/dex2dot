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

		cur_clazz = None
		cur_name = None

		classre = re.compile(r"^\s*#\d+\s*: \(in (L\S+;)\)$")
		infore  = re.compile(r"^\s*(name|type)\s*: '(\S+)'$")

		func = None
		code = None
		found_locals = False

		# TODO: will need this eventually
		#with open(self._get_disass_path(), encoding='utf-8-dex') as disass:
		with open(self._get_disass_path()) as disass:
			for line in disass:
				line = line.strip('\r\n')
				if code is not None:
					if found_locals and len(line.strip()) == 0:
						# empty line after locals block ends function.
						return code
						# TODO: return createfunc(clazz, mname, mtype, code)
					else:
						code.append(line)

				m = infore.match(line)
				if m:
					attr, val = m.groups()
					if attr == 'name':
						cur_name = val
					else:
						if (cur_clazz, cur_name, val) == (clazz, mname, mtype):
							code = [] # start collecting code
							found_locals = False
					continue

				m = classre.match(line)
				if m:
					cur_clazz = m.group(1)
					continue

				if line == '      locals        : ':
					found_locals = True
		raise Exception('function %s.%s %s not found' % (clazz, mname, mtype))

if __name__ == '__main__':
	import sys
	df = DexFile(sys.argv[1])
	code = df.getfunc(*sys.argv[2:5])
	for c in code:
		print('code:', c)
