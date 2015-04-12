#!/usr/bin/env python3
#coding=utf8

import logging as log
log = log.getLogger(__name__)
import re

def parselist(string, pattern, separator):
	out = []

	try:
		string, matched = expect(string, pattern)
		out.append(matched)
		while True:
			string, matched = expect(string, separator, pattern)
			out.append(matched)
	except Mismatch:
		# no more matches -- return!
		return string, out

class RegReplacer(object):
	def __init__(self):
		self.replacements = None
		self.addr = None
		self.re = re.compile(r'(v[0-9]+)')

	def __call__(self, string):
		import sys
		string, reg = expect(string, self.re)
		if self.replacements is None:
			return string, reg
		reg = int(reg[1:])
		assert self.addr is not None
		try:
			for region in self.replacements[reg]:
				if self.addr in region:
					return string, 'v%d_%s' % (reg, region.name)
		except KeyError:
			pass # had no mappings for that register
		return string, 'v%d' % reg

REG  = RegReplacer()
REGS = lambda data: parselist(data, REG, ', ')
CLS  = re.compile(r'(L[^;]+;)')
ID   = re.compile(r'([0-9A-Za-z_<>]+)') # okay, this doesn't cover all valid IDs
TYP  = re.compile(r'(\[*(?:[VZBSCIJFD]|L[^;]+;))')
TYPS = lambda data: parselist(data, TYP, '')
ADDR = re.compile(r'([0-9a-f]{4,})')
CMT  = re.compile(r'\s*// ([a-z]+@[0-9a-f]+)$')
NUM  = re.compile(r'([0-9]+)')

CMPOP = {'eq':'==', 'ne':'!=', 'le':'<=', 'lt':'<', 'ge':'>=', 'gt':'>'}

class Mismatch(Exception):
	def __init__(self, expected, data):
		Exception.__init__(self, 'pattern not found in data', expected, data)

def expect(data, *patterns):
	out = []
	for pattern in patterns:
		if type(pattern) is str:
			if not data.startswith(pattern):
				raise Mismatch(pattern, data)
			data = data[len(pattern):]
		elif 'match' in dir(pattern):
			match = pattern.match(data)
			if not match:
				raise Mismatch(pattern, data)
			out.extend(match.groups())
			data = data[match.end():]
		else:
			data, matched = pattern(data)
			out.append(matched)
	if out:
		return (data,) + tuple(out)
	return data

def doublify(reg):
	if reg[0] == 'v':
		try:
			regnum = int(reg[1:])
		except ValueError:
			return reg
		return 'v%d~%d' % (regnum, regnum+1)
	return reg

def simplify(func, block, config):
	if not config.simplify:
		return

	def nicetype(t):
		# TODO: nicify functions as well (separate function?)
		arraydepth = 0
		while t.startswith('['):
			t = t[1:]
			arraydepth += 1
		assert len(t) > 0
		if t.startswith('L'):
			# TODO: use "java.lang.String" instead of "Ljava/lang/String;"
			return t + '[]' * arraydepth
		primitives = {'Z':'boolean', 'B':'byte', 'C':'char', 'S':'short',
		              'I':'int', 'J':'long', 'F':'float', 'D':'double'}
		return primitives[t]  + '[]' * arraydepth

	REG.replacements = func.locals if config.namevars else None
	last_orig_op = None
	for ix, addr in enumerate(block.addrs):
		REG.addr = addr
		op   = block.ops[ix]
		args = block.args[ix]
		log.debug('    before: %04x %s %s', addr, op, args)

		if op.startswith('const'):
			args, v = expect(args, REG, ', ')
			m = CMT.search(args)
			if m:
				args = args[:m.start()]
			if op.endswith('-class'):
				args += '.class'
			op = '%s = %s' % (v, args)
			args = ''
		elif op in ('packed-switch', 'sparse-switch'):
			args, var = expect(args, REG)
			op = 'switch %s' % var
			args = ''
		elif op.startswith('invoke-'):
			args, vin, clazz, fname, vtypes, rtype, comment = expect(args,
					'{', REGS, '}, ', CLS, '.', ID, ':(', TYPS, ')', TYP, CMT)

			instance = None
			if op.startswith('invoke-static'):
				instance = clazz
			else:
				instance = vin[0]
				vin = vin[1:]

			for jx, vtype in enumerate(vtypes):
				if vtype in 'JD':
					# long and double are the only wide types.
					regnum = int(vin[jx][1:])
					assert len(vin) > jx and vin[jx] == 'v%d' % (regnum+1)
					vin[jx] = doublify(vin[jx])
			assert len(vin) == len(vtypes)

			op = '%s.%s(%s)' % (instance, fname, ', '.join(vin))
			assert args == ''
		elif op.startswith('move-result'):
			funccall = '<last function call result>'
			# the move must be immediately after the call, but the block might
			# be split because of different catches
			args, var = expect(args, REG)
			if ix > 0 and last_orig_op.startswith('invoke-'):
				funccall = block.ops[ix-1]
				block.ops[ix-1] = '↓'
				log.debug('    stole %s from %04x', funccall, block.addrs[ix-1])
			op = '%s = %s' % (var, funccall)
			assert args == ''
		elif op.startswith('goto'):
			op = 'goto %s' % (args.split('//')[0].strip())
			args = ''
		elif op == 'new-instance':
			args, v, clazz, comment = expect(args, REG, ', ', CLS, CMT)
			op = '%s = new %s' % (v, clazz)
			assert args == ''
		elif op == 'iput-object':
			# TODO: this can probably be generalized for all iput variants
			args, val, obj, objclazz, attrname, valclazz, cmt = expect(
					args, REG, ', ', REG, ', ', CLS, '.', ID, ':', TYP, CMT)
			op = '%s.%s = %s' % (obj, attrname, val)
			assert args == ''
		elif op == 'sget-object':
			# TODO: this can probably be generalized for all sget variants
			args, val, clazz, attrname, valclazz, comment = expect(
					args, REG, ', ', CLS, '.', ID, ':', TYP, CMT)
			op = '%s = %s.%s' % (val, clazz, attrname)
			assert args == ''
		elif op == 'check-cast':
			args, reg, clazz, comment = expect(args, REG, ', ', TYP, CMT)
			op = '%s = (%s)%s' % (reg, clazz, reg)
			assert args == ''
		elif op.startswith('if-'):
			cmpop = CMPOP[op[3:5]]
			if op.endswith('z'):
				args, reg, dst = expect(args, REG, ', ', ADDR)
				op = 'if %s %s 0: goto %s' % (reg, cmpop, dst)
			else:
				args, a, b, dst = expect(args, REG, ', ', REG, ', ', ADDR)
				op = 'if %s %s %s: goto %s' % (a, cmpop, b, dst)
			args = ''
		elif op == 'move-exception':
			args, var = expect(args, REG)
			op = '%s = <caught exception>' % var
			args = ''
		elif op.startswith('move'):
			#note: move-exception and move-result already handled above.
			args, dst, src = expect(args, REG, ', ', REG)
			op = '%s = %s' % (dst, src)
			if dst == src:
				# can happen if we're switching the register for the variable
				op += ' (switching register)'
			assert args == ''
		elif op.startswith('cmp'):
			args, dst, left, right = expect(args, REG, ', ', REG, ', ', REG)
			assert args == ''
			if op.endswith('double') or op.endswith('long'):
				left  = doublify(left)
				right = doublify(right)
			op = '%s = %s %s, %s' % (dst, op, left, right)
		elif 'new-array' in op:
			if op.startswith('filled-'):
				args, initdata = expect(args, '{', REGS, '}')
				size = len(initdata)
				dst = None
			else:
				args, dst, size = expect(args, REG, ', ', REG)
				initdata = None
			args, typ, comment = expect(args, ', ', TYP, CMT)
			assert args == ''

			op = ''
			if dst is not None:
				op = '%s = ' % dst

			assert typ.startswith('[')
			typ = nicetype(typ)
			base, extradepth = typ.split('[]', 1)
			op += 'new %s[%s]%s' % (base, size, extradepth)
			if initdata is not None:
				# TODO: assert type(size) is int
				op += ' {%s}' % ', '.join(initdata)
		elif op in ('throw', 'return', 'return-object'):
			args, var = expect(args, REG)
			assert args == ''
			op = '%s %s' % (op, var)
		elif op in ('nop', 'packed-switch-data', 'sparse-switch-data'):
			pass # these use no regs, so they're safe to just copy
		else:
			# no simplification for this instruction yet... that's okay, except
			# if we were filling in var names (we don't want to mix with regs!)
			assert not config.namevars, ('unhandled instruction type "%s"; ' +
					'might cause problems when variable names are enabled') % op

		log.debug('    after:  %04x %s %s', addr, op, args)
		last_orig_op = block.ops[ix]
		block.ops[ix] = op
		block.args[ix] = args
