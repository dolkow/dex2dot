#!/usr/bin/env python3
#coding=utf8

import re

def parselist(string, pattern, separator):
	assert pattern.groups == 1
	out = []

	first = True
	while True:
		if not first:
			if not string.startswith(separator):
				break
			string = string[len(separator):]
		first = False
		match = pattern.match(string)
		if not match:
			break
		out.append(match.group(1))
		string = string[match.end():]

	return string, out

REG  = re.compile(r'(v[0-9]+)')
REGS = lambda data: parselist(data, REG, ', ')
CLS  = re.compile(r'(L[^;]+;)')
ID   = re.compile(r'([0-9A-Za-z_<>]+)') # okay, this doesn't cover all valid IDs
TYP  = re.compile(r'([VZBSCIJFD[]|L[^;]+;)')
TYPS = lambda data: parselist(data, TYP, '')
CMT  = re.compile(r'\s*// ([a-z]+@[0-9a-f]+)$')


commentre = re.compile(' // [a-z]+@[0-9a-f]+$')
def rmcomment(s):
	return commentre.sub('', s)

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

def simplify(block, config):
	if not config.simplify:
		return
	last_orig_op = None
	for ix, addr in enumerate(block.addrs):
		op   = block.ops[ix]
		args = block.args[ix]

		if op.startswith('const'):
			op   = ' ='.join(args.split(',', 1))
			op = rmcomment(op)
			args = ''
		elif op in ('packed-switch', 'sparse-switch'):
			op = 'switch %s' % args.split(',')[0]
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
					vin[jx] += '~%d' % (regnum+1)
			assert len(vin) == len(vtypes)

			op = '%s.%s(%s)' % (instance, fname, ', '.join(vin))
			args = ''
		elif op.startswith('move-result'):
			funccall = '<last function call result>'
			# the move must be immediately after the call, but the block might
			# be split because of different catches
			if ix > 0 and last_orig_op.startswith('invoke-'):
				funccall = block.ops[ix-1]
				block.ops[ix-1] = '↓'
			op = args + ' = ' + funccall
			args = ''
		elif op.startswith('goto'):
			op = 'goto %s' % (args.split('//')[0].strip())
			args = ''
		elif op == 'new-instance':
			op = ' = new'.join(args.split(','))
			op = rmcomment(op)
			args = ''
		elif op == 'iput-object':
			# TODO: this can probably be generalized for all iput variants
			args, val, obj, objclazz, attrname, valclazz, cmt = expect(
					args, REG, ', ', REG, ', ', CLS, '.', ID, ':', TYP, CMT)
			op = '%s.%s = %s' % (obj, attrname, val)
			args = ''
		elif op == 'sget-object':
			# TODO: this can probably be generalized for all sget variants
			args, val, clazz, attrname, valclazz, comment = expect(
					args, REG, ', ', CLS, '.', ID, ':', TYP, CMT)
			op = '%s = %s.%s' % (val, clazz, attrname)
			args = ''
		elif op == 'check-cast':
			args, reg, clazz, comment = expect(args, REG, ', ', CLS, CMT)
			op = '%s = (%s)%s' % (reg, clazz, reg)
			args = ''

		last_orig_op = block.ops[ix]
		block.ops[ix] = op
		block.args[ix] = args
