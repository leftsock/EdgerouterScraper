#!/usr/bin/python3
"""Parse and produce a unified diff from two EdgeRouter config files."""

import re
import sys


class Error(Exception):
  """Do not raise. Package level exception."""


class ProgrammerError(Error):
  """An impossible code branch has happened."""


class UnknownKeyError(Error):
  """Key could not be found."""


class Entry:
  """Entry key,value pairs, such as "address 1.2.3.4/24"."""

  def __init__(self, parent, key, value):
    self._key = key
    self._value = value
    self._parent = parent

  @property
  def name(self):
    """Return entry key."""
    return self._key

  @property
  def key(self):
    """Return entry key."""
    return self._key

  @property
  def value(self):
    """Return entry value."""
    return self._value
    # TODO: what's the rule for quoting?, but not always (disable,
    # exclude, failover-only, match-ipsec. maybe the opposite, if key is
    # description, plaintext-password, subnet-parameters

    # return '""'
    # not needed for just diff'ing, only for edits to the config

  def toString(self, prefix=None):
    """User readable string. prepend "prefix=" to every line."""
    if prefix is None:
      prefix = ''
    if self._value is None:
      return '%s%s' % (prefix, self._key)
    return '%s%s %s' % (prefix, self._key, self._value)

  def __str__(self):
    return self.toString()

  def __lt__(self, rhs):
    return str(self) > str(rhs)

  def __gt__(self, rhs):
    return str(self) < str(rhs)

  def __eq__(self, rhs):
    return str(self) == str(rhs)


class Entries:
  """Aggregate multiple Entry objects."""

  # DO NOT SORT these entries. order matters i.e. set interfaces ethernet eth0 address a.b.c.d/24
  unsorted_entries = ('address',)

  def __init__(self, parent, indent, entry):
    self._parent = parent
    self._indent = indent  # TODO: this is the indent of the parent.
    self._entries = [entry]
    self._name = entry.name

  @property
  def name(self):
    """Return name of these Entries."""
    return self._name

  def keys(self):
    """Return keys to sort the Entries by.
    Since 'key' is identical for all Entry objects, se must use value.
    """
    retval = []
    for entry in self._entries:
      retval.append(entry.value)
    return retval

  def sortable(self):
    """Returns True if this self._name is sortable.
    Some keys are order dependent. Don't mess with that.
    """
    return self._name not in Entries.unsorted_entries

  def get(self, key):
    """Returns the requested Entry object."""
    for entry in self._entries:
      if key == entry.value:
        return entry
    raise UnknownKeyError('no suck key %s' % key)

  def add(self, entry):
    """Add new Entry to this collection of Entries."""
    if self._name is None:
      self._name = entry.name
    assert entry.name == self._name, '%s != %s' % (entry.name, self._name)
    self._entries.append(entry)
    if self.sortable():
      self._entries.sort()

  def __lt__(self, rhs):
    return str(self) > str(rhs)

  def __gt__(self, rhs):
    return str(self) < str(rhs)

  def __eq__(self, rhs):
    return str(self) == str(rhs)

  def toString(self, prefix=None):
    """User readable string. prepend "prefix=" to every line."""
    if prefix is None:
      prefix = self._indent
    retval = []
    for entry in self._entries:
      retval.append('%s' % entry.toString(prefix=prefix))
    return '\n'.join(retval)

  def __str__(self):
    return self.toString()

  def udiff(self, rhs):
    """Returns list of strings containing unified-diff like output."""
    retval = []
    lhs_keys = self.keys()
    rhs_keys = rhs.keys()
    keys = list(set(lhs_keys + rhs_keys))
    if self.sortable():
      keys.sort()
    for key in keys:
      if key not in rhs_keys:
        retval.append('%s' % self.get(key).toString(prefix='-%s' % self._indent))
      elif key not in lhs_keys:
        retval.append('%s' % rhs.get(key).toString(prefix='+%s' % self._indent))
      elif self.get(key) == rhs.get(key):
        retval.append('%s' % self.get(key).toString(prefix=' %s' % self._indent))
      else:
        raise ProgrammerError('unexplained key %s' % key)
    return retval


class Section:
  """Nestable sections."""

  def __init__(self, parent, indent, name):
    self._indent = indent
    self._name = name
    self._parent = parent
    self._entries = {}
    self._sections = {}

  def add_entry(self, entry):
    """Add new Entry. For example "address 1.2.3.4/24"."""
    k = entry.key  # standardize on name?
    # duplicates possible e.g. 'network'
    if k in self._entries:
      self._entries[k].add(entry)
    else:
      self._entries[k] = Entries(self, self._indent+'    ', entry)

  def add_section(self, section):
    """Add new section. For example "firewall {...}"."""
    k = section.name
    assert k not in self._sections
    self._sections[k] = section

  @property
  def parent(self):
    """Track who's our parent."""
    return self._parent

  @parent.setter
  def parent(self, parent):
    """Track who's our parent."""
    self._parent = parent

  @property
  def name(self):
    """Returns section name."""
    return self._name

  def __lt__(self, rhs):
    return str(self) > str(rhs)

  def __gt__(self, rhs):
    return str(self) < str(rhs)

  def __eq__(self, rhs):
    return str(self) == str(rhs)

  def keys(self):
    """Return list of keys for sorting."""
    keys = list(self._sections)
    for k in self._entries:
      keys.append(self._entries[k].name)
    return keys

  def get(self, key):
    """Returns Section or Entries object for key.
    Raises KeyError if key not present.
    """
    if key in self._entries:
      return self._entries[key]
    if key in self._sections:
      return self._sections[key]
    raise UnknownKeyError(key)

  def toString(self, prefix=None):
    """User readable string. prepend "prefix=" to every line."""
    if prefix is None:
      prefix = self._indent
    #print('Section.__str__ %s' % self.name, file=sys.stderr)
    retval = ['%s%s {' % (prefix, self.name)]
    for k in sorted(self.keys()):
      retval.append(self.get(k).toString(prefix=prefix + '    '))
    retval.append('%s}' % prefix)
    return '\n'.join(retval)

  def __str__(self):
    return self.toString()

  def udiff(self, rhs):
    """Returns list of strings containing unified-diff like output."""
    retval = []
    # self
    assert self.name == rhs.name, '%s != %s' % (self.name, rhs.name)
    retval.append(' %s%s {' % (self._indent, self.name))
    # contents
    lhs_keys = self.keys()
    rhs_keys = rhs.keys()
    for key in sorted(set(lhs_keys + rhs_keys)):
      if key not in rhs_keys:
        retval.append('%s' % self.get(key).toString(prefix='-    %s' % self._indent))
      elif key not in lhs_keys:
        retval.append('%s' % rhs.get(key).toString(prefix='+    %s' % self._indent))
      else:  # recurse
        left = self.get(key)
        right = rhs.get(key)
        retval.extend(left.udiff(right))
    retval.append(' %s}' % self._indent)
    return retval


class Config:
  """Data class for EdgeRouter configuration."""

  def __init__(self):
    self._header = []
    # presumably only sections, no Entries. if so, change to extend Section?
    self._sections = {}
    self._footer = []

  def add_section(self, section):
    """Add new section."""
    k = section.name
    assert k not in self._sections, 'Duplicate found: %s' % k
    self._sections[k] = section

  def add_header(self, line):
    """Add header line before the config."""
    self._header.append(line)

  def add_footer(self, line):
    """Add footer line after the config."""
    self._footer.append(line)

  def keys(self):
    """Return list of keys for sorting."""
    k = list(self._sections.keys())
    return k

  def get(self, key):
    """Raises KeyError if key not present."""
    return self._sections[key]

  def __str__(self):
    return self.toString()

  def toString(self, prefix=None):
    """User readable string. prepend "prefix=" to every line."""
    if prefix is None:
      prefix = ''
    retval = []
    retval.extend(self._header)
    for k in sorted(self.keys()):
      retval.append(self.get(k).toString(prefix=prefix))
    retval.extend(self._footer)
    return '\n'.join(retval) + '\n'

  @property
  def header(self):
    """Configuration header."""
    return self._header

  @property
  def footer(self):
    """Configuration footer."""
    return self._footer

  def __lt__(self, rhs):
    return str(self) > str(rhs)

  def __gt__(self, rhs):
    return str(self) < str(rhs)

  def __eq__(self, rhs):
    return str(self) == str(rhs)

  def udiff(self, rhs):
    """Returns list of strings containing unified-diff like output."""
    retval = []
    lhs_keys = self.keys()
    rhs_keys = rhs.keys()
    for key in sorted(set(lhs_keys + rhs_keys)):
      if key not in rhs_keys:
        retval.append('%s' % (self.get(key).toString(prefix='-')))
      elif key not in lhs_keys:
        retval.append('%s' % (rhs.get(key).toString(prefix='+')))
      else:  # recurse
        left = self.get(key)
        right = rhs.get(key)
        retval.extend(left.udiff(right))
    # TODO: selectively print context (lines with '{', '}') and ...\n
    return '\n'.join(retval)


class Parser:
  """Parser for Edgerouter config."""

  def __init__(self):
    self._config = Config()
    self._current = None
    # Track what part is currently being parsed; header, body, or footer
    self._mode = 0  # header

  def line(self, line):
    """Parse next line into config."""
    #print(line, file=sys.stderr)
    # sample """firewall {"""
    # sample """interfaces {"""
    # sample """         site-to-site {"""
    # sample """        rule 5003 {"""
    new_section = re.match(r'( *)(.*) {', line)
    # sample """}"""
    # sample """         }"""  # i.e. lines up with new_section indent
    end = re.match(r'( *)}', line)
    if self._mode == 0:  # header
      assert not end
      if not new_section:
        self._config.add_header(line)
      else:  # First body line, is always a section starter
        section = Section(self._config, new_section.group(1), new_section.group(2))
        self._config.add_section(section)
        self._current = section
        #print('========== end header', file=sys.stderr)
        self._mode = 1  # body
    elif self._mode == 1:  # body
      # sample """  all-ping enable"""
      # sample """            key value"""  # i.e. indent +4 spaces
      entry = re.match(r'( *)(.+)', line)
      if new_section:
        section = Section(self._current, new_section.group(1), new_section.group(2))
        self._current.add_section(section)
        self._current = section
      elif end:
        #print('end', file=sys.stderr)
        self._current = self._current.parent
      elif entry:  # because this is a .* regex, it must come last
        if ' ' in entry.group(2):
          key, value = entry.group(2).split(' ', 1)
          self._current.add_entry(Entry(self._current, key, value))
        else:  # bare keyword, no value
          self._current.add_entry(Entry(self._current, entry.group(2), None))
      else:  # presume body -> footer
        #print('========== begin footer', file=sys.stderr)
        self._config.add_footer(line)
        self._mode = 2  # footer
    elif self._mode == 2:  # footer
      self._config.add_footer(line)

  @property
  def config(self):
    """Return configuration object."""
    return self._config


def main(argv):
  """Main."""
  assert len(argv) == 3
  assert argv[1]
  assert argv[2]

  lhs_fn = argv[1]
  rhs_fn = argv[2]

  # parse
  parse = Parser()
  with open(lhs_fn, 'r') as fh:
    for line in fh.read().split('\n'):
      line = line.rstrip()
      parse.line(line)
  lhs = parse.config
  # TEST #
  #print(lhs)
  #sys.exit(0)
  # TEST #
  parse = Parser()
  with open(rhs_fn, 'r') as fh:
    for line in fh.read().split('\n'):
      line = line.rstrip()
      parse.line(line)
  rhs = parse.config

  # diff headers
  if lhs.header != rhs.header:
    # TODO: diff header properly
    for head in lhs.header:
      print('-%s' % head)
    for head in rhs.header:
      print('+%s' % head)
  else:
    for head in lhs.header:
      print(' %s' % head)

  print(lhs.udiff(rhs))

  # diff footer
  if lhs.footer != rhs.footer:
    # TODO: diff footer properly
    for foot in lhs.footer:
      print('-%s' % foot)
    for foot in rhs.footer:
      print('+%s' % foot)
  else:
    for foot in lhs.footer:
      print(' %s' % foot)


main(sys.argv)
