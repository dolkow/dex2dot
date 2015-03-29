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
		self.next = None
		self.cond_next = None
		self.switch_next = None

	def add_instruction(self, addr, op, args):
		assert not self.addrs or self.addrs[-1] < addr
		self.addrs.append(addr)
		self.ops.append(op)
		self.args.append(args)

	def split(self, addr):
		''' split this block, returning a new block *ending* at addr '''
		low = BasicBlock(self.name)
		self.name = 'block_%04x' % addr
		low.catches = self.catches # identical catches.

		# we're keeping our own outs, and the new block will have us as next.
		low.next = self

		# now split the code
		assert self.addrs
		ix = self.addrs.index(addr)
		assert ix > 0
		low.addrs, self.addrs = self.addrs[:ix], self.addrs[ix:]
		low.ops,   self.ops   = self.ops[:ix],   self.ops[ix:]
		low.args,  self.args  = self.args[:ix],  self.args[ix:]

		return low

	def finished(self):
		return self.next is not None

class BlockList(object):
	def __init__(self):
		entry  = BasicBlock('__func_entry')
		exit   = BasicBlock('__func_exit')
		zero   = BasicBlock(0)
		entry.next = zero
		self.addrs  = [-1, 0, 2**16] # ordered by address
		self.blocks = [entry, zero, exit] # same length and order as addrs

	def find_index(self, addr):
		''' find the index of the block that contains addr '''
		assert addr >= 0 and addr < 2**16 # dalvik method length is 16-bit
		prev = 0
		for ix, blockstart in enumerate(self.addrs):
			if addr < blockstart:
				assert ix != 0
				return ix-1
		assert False, 'BUG: should have found the index!' # due to exit block

	def get_or_create(self, addr):
		''' get basic block that contains addr, creating it if needed '''
		ix = self.find_index(addr)
		block = self.blocks[ix]
		if block.finished():
			block = BasicBlock(addr)
			self.addrs.insert(ix+1, addr)
			self.blocks.insert(ix+1, block)
		return block

	def get_or_split(self, addr):
		''' get basic block starting at addr, splitting as needed '''
		ix = self.find_index(addr)
		block = self.blocks[ix]
		if self.addrs[ix] == addr:
			return block
		lower = block.split(addr)
		self.addrs.insert(ix+1, addr) # yes, the ix diff here is intentional:
		self.blocks.insert(ix, lower) # lower inherits block's old addr
		return block

	def add_instruction(self, addr, op, args):
		block = self.get_or_create(addr)
		block.add_instruction(addr, op, args)
		if op.startswith('goto'):
			target = int(args.split()[0], 16)
			target = self.get_or_split(target)
			block.next = target
		elif op.startswith('if-'):
			pass # TODO
		elif op == 'packed-switch':
			pass # TODO
		elif op == 'sparse-switch':
			pass # TODO
		elif op == 'throw':
			pass # TODO
		elif op.startswith('return'):
			pass # TODO

def makeblocks(dexfile, code, catches):
	codere = re.compile(r"^[0-9a-f]+:(?: [0-9a-f]{4})+\s+(?:\.\.\. )?\s*\|"
	                  + r"([0-9a-f]{4}): (\S+) (\S.*)$")
	stringre = re.compile(r'" // string@[0-9a-f]{4}$')
	blocklist = BlockList()

	generator = (line for line in code)
	for line in generator:
		m = codere.match(line)
		assert m, 'BUG: code regex does not match line "%s"' % line
		addr, op, args = m.groups()
		addr = int(addr, 16)

		if op.startswith('const-string'):
			# join multi-line const strings
			while not stringre.search(line):
				line = next(generator)
				assert not codere.match(line), line
				args += '\\n'
				args += line

		if op in ('packed-switch-data', 'sparse-switch-data'):
			continue # don't include in any basic blocks

		blocklist.add_instruction(addr, op, args)

	for block in blocklist.blocks:
		print(block.name, len(block.ops))
		for instruction in zip(block.addrs, block.ops, block.args):
			print('    %04x: %-20s %s' % instruction)
		print()
