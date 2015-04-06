#!/usr/bin/env python3
#encoding=utf8

import codecs

def dex_special_handler(err):
	''' handles DEX files' special modified UTF-8 when the default utf-8
	    decoder can't.
	    https://source.android.com/devices/tech/dalvik/dex-format.html'''

	if type(err) is not UnicodeDecodeError:
		raise err

	def _read_one(bytes):
		b = bytes[0]
		if (b & 0xc0) != 0xc0:
			raise err # this is some other problem

		if (b & 0xe0) == 0xe0:
			n = 3
			if (b & 0x10):
				raise err # binary 1111xxxx is not allowed.
		else:
			n = 2

		result = b & 0x1f
		for b in bytes[1:n]:
			if (b & 0xc0) != 0x80:
				raise err # continuation bytes should be binary 10xxxxxx
			result = (result << 6) | (b & 0x3f)
		return result, n

	result, used = _read_one(err.object[err.start:])
	continuepos = err.start + used
	# we now have one 16-bit number; it may be part of a UTF-16 surrogate pair
	if (result & 0xf800) == 0xd800:
		assert used == 3

		if (result & 0x0400):
			# it's the second part of the pair?! Does not compute!
			raise err

		second, used = _read_one(err.object[err.start+3:])
		if (second & 0xfc00) != 0xdc00:
			raise err # this wasn't a second pair..?
		assert used == 3
		continuepos += 3

		# Dalvik, why are you doing this to me? I thought we were friends! :(
		result = ((result & 0x3ff) << 10) | (second & 0x3ff)
		assert result >= 0 and result <= 0xfffff
		result += 0x10000

	return chr(result), continuepos

codecs.register_error('dex', dex_special_handler)

if __name__ == '__main__':
	import tempfile
	import os
	f, path = tempfile.mkstemp()
	exp = [    0x4d,     0,      0x61, 0xF0000]
	exp = ''.join(chr(x) for x in exp)
	b = bytes([0x4d, 0xc0, 0x80, 0x61, 0xED, 0xAE, 0x80, 0xED, 0xB0, 0x80])
	os.write(f, b)
	os.close(f)
	with open(path, encoding='utf-8', errors='dex') as f:
		s = f.read()
		print('wanted: %s = %s' % (' '.join('%06x' % ord(x) for x in exp), exp))
		print('actual: %s = %s' % (' '.join('%06x' % ord(x) for x in s), s))
		print()
		print('Yay, it matches!' if exp == s else 'MISMATCH!!!!')
	os.remove(path)
