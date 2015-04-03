#!/usr/bin/env python3
#coding=utf8

import re

clz  = r'L[^;]+;'
typ = r'[VZBSCIJFD[]|' + clz

invokere = r'^\{([v0-9 ,]*)\}, (%s)\.([^:]+):\(((?:%s)*)\)(%s) // method@'
invokere = re.compile(invokere % (clz, typ, typ))

typere = re.compile(typ)

def simplify(block, config):
	if not config.simplify:
		return
	last_orig_op = None
	for ix, addr in enumerate(block.addrs):
		op   = block.ops[ix]
		args = block.args[ix]

		if op.startswith('const'):
			op   = ' ='.join(args.split(',', 1))
			op = re.sub(' // string@[0-9a-f]+$', '', op)
			args = ''
		elif op in ('packed-switch', 'sparse-switch'):
			op = 'switch %s' % args.split(',')[0]
			args = ''
		elif op.startswith('invoke-'):
			match = invokere.match(args)
			assert match

			vin, clazz, fname, vtypes, rtype = match.groups()
			vin = vin.split(', ')
			instance = None

			if op.startswith('invoke-static'):
				instance = clazz
			else:
				instance = vin[0]
				vin = vin[1:]

			vtypes = typere.findall(vtypes)
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

		last_orig_op = block.ops[ix]
		block.ops[ix] = op
		block.args[ix] = args
