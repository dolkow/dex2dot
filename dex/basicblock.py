#!/usr/bin/env python3
#coding=utf8

import re

class BasicBlock(object):
	def __init__(self, name):
		if type(name) is int:
			name = 'block_%04x' % name
		self.name = name
		self.addrs = [] # list of instruction addresses, in order
		self.ops   = [] # list of instruction operations, in address order
		self.args  = [] # list of instruction everything-else, in address order
		self.catches = None
		self.succ = None

def codeparser(code):
	codere = re.compile(r"^[0-9a-f]+:(?: [0-9a-f]{4})+\s+(?:\.\.\. )?\s*\|"
	                  + r"([0-9a-f]{4}): (\S+) (\S.*)$")
	stringre = re.compile(r'" // string@[0-9a-f]{4}$')
	generator = iter(code)
	found_switch_data = False
	last_addr = -1
	for line in generator:
		m = codere.match(line)
		assert m, 'BUG: code regex does not match line "%s"' % line
		addr, op, args = m.groups()
		addr = int(addr, 16)

		assert addr > last_addr
		last_addr = addr

		if op in ('packed-switch-data', 'sparse-switch-data'):
			found_switch_data = True
			continue # don't include in any basic blocks

		assert not found_switch_data, 'I assumed switch data was always last'

		if op.startswith('const-string'):
			# join multi-line const strings
			while not stringre.search(line):
				line = next(generator)
				assert not codere.match(line), line
				args += '\\n'
				args += line

		yield addr, op, args

def makeblocks(dexfile, code, catches):
	blockstarts = set() # addresses of basic blocks' first instruction
	jumps = {} # src addr -> {cond -> dst addr};
	# cond True  = branch condition OK
	# cond <int> = switch value

	def addjmp(cond, src, dst):
		blockstarts.add(dst)
		if src not in jumps:
			jumps[src] = {}
		jumps[src][cond] = dst

	last_branched = True

	# find all branches
	for addr, op, arg in codeparser(code):
		if last_branched:
			blockstarts.add(addr)

		last_branched = True
		if op.startswith('goto'):
			addjmp(None, addr, int(arg.split()[0], 16))
		elif op.startswith('if-'):
			addjmp(True, addr, int(arg.split()[1], 16))
#		elif op == 'packed-switch':
#			pass # TODO
#		elif op == 'sparse-switch':
#			pass # TODO
#		elif op == 'throw':
#			pass # TODO
		elif op.startswith('return'):
			addjmp(None, addr, -2) # -2 is the exit node
		else:
			last_branched = False
	assert last_branched, 'no branch at function end'

	# create basic blocks
	block = BasicBlock('func_entry')
	fexit = BasicBlock('func_exit')
	fexit.succ = {}
	blocks = {-1:block, -2:fexit} # start addr -> block
	for addr, op, arg in codeparser(code):
		if addr in blockstarts:
			prev = block
			block = BasicBlock(addr)
			blocks[addr] = block
			if prev.succ is None:
				prev.succ = {}
			if None not in prev.succ:
				prev.succ[None] = addr # link fallthrough
		assert block.succ is None
		block.addrs.append(addr)
		block.ops.append(op)
		block.args.append(arg)
		if addr in jumps:
			block.succ = jumps[addr]
	assert block.succ is not None, 'function has no branch at the end'

	# convert branch targets from address to block reference
	for block in blocks.values():
		for cond in block.succ:
			dst_addr = block.succ[cond]
			block.succ[cond] = blocks[dst_addr]

	return tuple(blocks.values())
