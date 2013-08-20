#!/usr/bin/env python

# Convert text and standoff annotations into GrAF format.


from __future__ import with_statement
import sys
import os
import re
from collections import namedtuple

SEMICOLON_RE = re.compile(';')

Text = namedtuple('Text', 'start end')
Trigger = namedtuple('Trigger', 'id type')
Argument = namedtuple('Argument', 'id type')
Note = namedtuple('Note', 'id type text annotation_id')
Normalization = namedtuple('Normalization', 
					'norm_type anno_id resource_id entry_id text_str')			


class Entity(object):
	"""
	assigns a type (e.g. Person or Organization) to a (dis)continuous
	text span.
	"""
	def __init__(self, entity_id, list_of_offsets, text_str):
		self.id = entity_id

		# support for discontinuous text-bound annotations (brat v1.3)
		for offset_tuple in list_of_offsets:
			assert isinstance(offset_tuple, tuple) and \
				len(offset_tuple) == 2

		self.offsets = list_of_offsets		
		self.string = text_str


class Event(object):
	"""
	represents one event from a brat .ann file
	
	Example: 'E1	MERGE-ORG:T2 Org1:T1 Org2:T3'
		event id: E1
		trigger type: MERGE-ORG
		trigger id: T2 (a text span defined earlier)
		arguments: (T1, Org1), (T3, Org2)
	"""
	def __init__(self, event_id, trigger, arguments):
		self.id = event_id
		self.trigger = trigger
		
		for arg in arguments:
			assert isinstance(arg, tuple) and len(arg) == 2
		self.arguments = arguments

class Relation(object):
	"""represents a relation from a brat .ann file"""
	def __init__(self, relation_id, relation_type, arguments):
		self.id = relation_id
		self.type = relation_type

		for arg in arguments:
			assert isinstance(arg, tuple) and len(arg) == 2
		self.arguments = arguments

class Equivalence(object):
	"""represents an equivalence relation between a set of entities"""
	def __init__(self, relation_type, entities):
		self.type = relation_type # should be "Equiv", but who knows ...
		self.entities = entities
		
class Attribute(object):
	"""represents an additional attribute of an annotation"""
	def __init__(self, attribute_id, attribute_type, annotation_id, 
					attribute_value=None):
		self.id = attribute_id
		self.type = attribute_type
		self.value = attribute_value
		self.annotation_id = annotation_id
	

def parse_annotation(anno_file):
	"""
	parses a brat standoff annotation file and returns a list of
	Annotation instances.
	
	Text-bound annotations identify a specific span of text and assigns
	it a type, e.g. "T2	MERGE-ORG 14 27	joint venture".
	"""
	annotations = []
	
	with open(anno_file, 'r') as f:
		lines = f.readlines()
		for line in lines:
			columns = line.split('\t')
			assert 1 < len(columns) < 4, \
				"an annotation must have 2 or 3 tab-separated columns"
			
			anno_id = columns[0]
						
			if anno_id.startswith("T"): # text-bound annotation, i.e. entities
				# maxsplit = 1
				anno_type, offsets_str = columns[1].split(' ', 1)
				list_of_offsets = parse_offsets(offsets_str)
				text_str = columns[2].rstrip()
				anno = Entity(anno_id,
						list_of_offsets,
						text_str)
				annotations.append(anno)
			
			elif anno_id.startswith("E"): # event annotation
				trigger_str, arguments_str = columns[1].split(' ', 1)
				trigger_type, trigger_id = trigger_str.split(':')
				
				arguments = parse_arguments(arguments_str)
				anno = Event(anno_id,
						Trigger(trigger_id, trigger_type),
						arguments)
				annotations.append(anno)
				
			elif anno_id.startswith("R"): # relation annotation
				relation_type, arguments_str = columns[1].split(' ', 1)
				arguments = parse_arguments(arguments_str)
				anno = Relation(anno_id,
						relation_type, arguments)
				annotations.append(anno)
				
			elif anno_id == "*": # equivalence relation
				relation_type, entities_str = columns[1].split(' ', 1)
				anno = Equivalence(relation_type, 
						entities_str.split(' '))
				annotations.append(anno)
				
			elif anno_id.startswith("A") or anno_id.startswith("M"): # attribute annotation
				anno = parse_attribute(anno_id, columns[1])
				annotations.append(anno)

			elif anno_id.startswith("N"): # normalization annotation
				anno = parse_normalization(columns[1], columns[2])
				annotations.append(anno)
				
			elif anno_id.startswith("#"): # note annotation
				note_id = anno_id
				note_type, annotation_id = columns[1].split(' ')
				anno = Note(note_id, note_type, columns[2].rstrip(), 
						annotation_id)
				annotations.append(anno)
					
	return annotations


def parse_normalization(normalization_str, entity_str):
	"""
	parses a string that links an entity to some external resource,
	e.g. 'Reference T1 Wikipedia:534366'.
	"""
	norm_type, anno_id, resource_str = normalization_str.split(' ')
	resource_id, entry_id = resource_str.split(':')
	return Normalization(norm_type, anno_id, resource_id, entry_id, 
			entity_str)

def parse_attribute(attribute_id, attribute_str):
	"""
	parse the string that describes an additional attribute of an
	annotation.
	"""
	attribute_value = None
	attribute_list = attribute_str.split(' ')
	
	if len(attribute_list) == 2:
		attribute_type, annotation_id = attribute_list
	elif len(attribute_list) == 3:
		attribute_type, annotation_id, attribute_value = attribute_list
	else:
		raise ValueError, "Can't parse attribute annotation: {0}".format(attribute_str)
	
	return Attribute(attribute_id, attribute_type, annotation_id, 
			attribute_value)
	

def parse_arguments(arguments_str):
	"""
	parses a string that contains a number of event/relation arguments,
	e.g. "Org1:T1 Org2:T3" or "Arg1:T3 Arg2:T4" and returns a list of
	Argument instances.
	"""
	list_of_arguments = []
	if arguments_str.rstrip():
		# there are events without arguments but with trailing space,
		# e.g. "E15	Process:T40 " in 
		# example-data/corporaBioNLP-ST_2011/BioNLP-ST_2011_ID/
		# PMC2266911-02-Results_and_Discussion-01-02-02.ann
		for arg_str in arguments_str.split(' '):
			arg_type, arg_id = arg_str.split(':')
			list_of_arguments.append(Argument(arg_id, arg_type))
	return list_of_arguments


def parse_offsets(offsets_str):
	"""
	parses a string that represents text offsets.
	supports discontinuous text-bound annotations (brat v1.3).
	
	example (continuous): "14 27" -> [Text(start=14, end=27)]
	example (discontinous): "0 5;16 23" -> [Text(start=0, end=5), Text(start=16, end=23)]
	"""
	list_of_offsets = []
	
	if SEMICOLON_RE.search(offsets_str):
		offsets_strings = offsets_str.split(';')
		for string in offsets_strings:
			offsets = [int(offset) for offset in string.split(' ')]
			list_of_offsets.append(Text(*offsets))
	else:
		offsets = offsets_str.split(' ')
		list_of_offsets.append(Text(*offsets))
		
	return list_of_offsets


if __name__ == '__main__':
	annotations = parse_annotation(sys.argv[1])
	for annotation in annotations:
		print annotation
