import re

class AddressRange(object):
	def __init__(self, start, end):
		self.start = int(start) # inclusive
		self.end = int(end) # exclusive

def parseinfo(info, regcount):
	generator = (line for line in info)

	assert next(generator).strip().startswith('catches')
	catches = [] # AddressRanges with 'jumpmap', ordered by start address
	regionre = re.compile(r"^\s*(0x[0-9a-f]{4}) - (0x[0-9a-f]{4})\s*$")
	catchre  = re.compile(r"^\s*(<any>|L.*;) -> (0x[0-9a-f]{4})\s*$")
	cur = None
	for line in generator:
		if line.strip().startswith('positions'):
			break # we're done with catches
		m = regionre.match(line)
		if m:
			start, end = (int(hx, 16) for hx in m.groups())
			cur = AddressRange(start, end)
			cur.jumpmap = {}
			catches.append(cur)
			continue
		m = catchre.match(line)
		assert m
		assert cur is not None
		name = m.group(1)
		target = int(m.group(2), 16)
		cur.jumpmap[name] = target

	positions = [] # AddressRanges with 'line', ordered by start address
	posre = re.compile(r"^\s*(0x[0-9a-f]{4}) line=(\d+)\s*$")
	pending = None
	for line in generator:
		if line.strip().startswith('locals'):
			break # we're done with positions
		m = posre.match(line)
		assert m
		pos = int(m.group(1), 16)
		line = int(m.group(2))
		if pending is not None:
			pending.end = pos
		pending = AddressRange(pos, -1)
		pending.line = line
		positions.append(pending)
	if pending is not None:
		pending.end = 2**16 # max size of a dalvik method

	local = {} # register -> [ranges with 'name'&'type', ordered by start addr]
	for r in range(regcount):
		local[r] = []
	localre = r"^\s*(0x[0-9a-f]{4}) - (0x[0-9a-f]{4}) reg=(\d+) (\S+) (\S+)\s*$"
	localre = re.compile(localre)
	for line in generator:
		m = localre.match(line)
		assert m
		start = int(m.group(1), 16)
		end   = int(m.group(2), 16)
		reg   = int(m.group(3))
		name  = m.group(4)
		vtype = m.group(5)
		var = AddressRange(start, end)
		var.name = name
		var.type = vtype
		local[reg].append(var)

	return catches, positions, local

def parsemeta(code):
	metare = re.compile(r"^\s*(\S.*\S)\s+(?:-|:)\s*(|\S|\S.*\S)\s*$")
	def expect(label, line):
		m = metare.match(line)
		assert m, 'Expected label %s, but line was "%s"' % (label, line)
		return m.group(2)
	access   = expect('access',     code[0])
	_        = expect('code',       code[1])
	regcount = expect('registers',  code[2])
	_        = expect('ins',        code[3])
	_        = expect('outs',       code[4])
	_        = expect('insns size', code[5])
	assert ' |[' in code[6], 'Expected function header, but was "%s"' % code[6]
	assert ' |0000: ' in code[7], 'Expected code start, but was "%s"' % code[7]
	access = int(access.split()[0], 16)
	regcount = int(regcount)
	return access, regcount, code[7:]

def createfunc(dexfile, clazz, mname, mtype, code, info):
	access, regcount, code = parsemeta(code)
	c, p, l = parseinfo(info, regcount)

	print('catches:')
	for catch in c:
		print('  0x%04x - 0x%04x' % (catch.start, catch.end))
		for exc, target in catch.jumpmap.items():
			print('    %s -> 0x%04x' % (exc, target))

	print('positions:')
	for pos in p:
		print('  0x%04x line=%d' % (pos.start, pos.line))

	print('locals:')
	for reg, ranges in l.items():
		for local in ranges:
			stuff = (local.start, local.end, reg, local.name, local.type)
			print('  0x%04x - 0x%04x reg=%d %s %s' % stuff)

	#for c in code:
	#	print('code:', c)

