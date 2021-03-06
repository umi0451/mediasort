#!/usr/bin/python3
import sys
import os
import shutil
import subprocess
import re
import chardet
import itertools
from functools import reduce
from collections import defaultdict
import argparse

def get_max_common_beginning(sequences):
	if not sequences:
		return None
	max_beginning = sequences[0]
	for seq in sequences:
		comps = [x[0]==x[1] for x in zip(max_beginning, seq)]
		if False in comps:
			max_beginning = seq[:comps.index(False)]
	return max_beginning

def get_remains(sequence, beginning):
	s = filter(lambda a: a[0] is None or a[1] is None, itertools.zip_longest(sequence, beginning))
	return map(lambda a: a[0] if a[1] is None else a[1], s)

def get_most_frequent_value(valuelist):
	frequencies = defaultdict(int)
	for value in valuelist:
		frequencies[value] += 1
	max_freq = max(frequencies.values()) if frequencies else 0
	for value in frequencies:
		if frequencies[value] == max_freq:
			return value
	return None

def get_working_dir(args):
	if args:
		return args[0]
	return os.getcwd()

def get_dir_content(dirname):
	filenames = os.listdir(dirname)
	mp3_filenames, other_filenames = [], []
	for filename in filenames:
		filepath = os.path.join(dirname, filename)
		root, extension = os.path.splitext(filepath)
		if extension == '.mp3':
			mp3_filenames.append(filepath)
		else:
			other_filenames.append(filepath)
	if not mp3_filenames:
		for filename in filenames:
			if os.path.isdir(os.path.join(dirname, filename)):
				mp3, other = get_dir_content(os.path.join(dirname, filename))
				mp3_filenames += mp3
				other_filenames += other
	return mp3_filenames, other_filenames

def _split_path(path):
	path, filename = os.path.split(path)
	dirnames = []
	while path:
		path, dirname = os.path.split(path)
		if dirname:
			dirnames.insert(0, dirname)
		else:
			if path:
				dirnames.insert(0, path)
			break
	return dirnames + [filename]

def get_exists_path_part(path):
	existing_path = ''
	remains = _split_path(path)
	while remains:
		if not os.path.exists(os.path.join(existing_path, remains[0])):
			ok = False
			for entry in os.listdir(existing_path):
				if entry.upper() == remains[0].upper():
					remains[0] = entry
					ok = True
					break
			if not ok:
				break 
		part, remains = remains[0], remains[1:]
		existing_path = os.path.join(existing_path, part)
	remains = reduce(os.path.join, remains) if remains else ''
	return existing_path, remains

def parse(expression_list, string):
	for expression in expression_list:
		m = re.match(expression, string)
		if m:
			return m.groupdict()
	return None

# ------

class TagInfo:
	def __init__(self):
		self.artist = ''
		self.album = ''
		self.year = 0
		self.number = 0
		self.title = ''

def _get_tag_content(data, regexp):
	match = re.search(regexp, data, re.MULTILINE)
	if match:
		return match.group(1)
	return ''

def get_taginfo_for_file(filename):
	id3v2_process = subprocess.Popen(['id3v2', '-l', filename], stdout=subprocess.PIPE)
	id3v2_process.wait()
	output = id3v2_process.stdout.read()

	taginfo = TagInfo()
	taginfo.artist = _get_tag_content(output, b'^TPE1 .*: (.*)$')
	taginfo.album  = _get_tag_content(output, b'^TALB .*: (.*)$')
	taginfo.year   = _get_tag_content(output, b'^TYER .*: (.*)$')
	taginfo.number = _get_tag_content(output, b'^TRCK .*: (.*)/.*$')
	taginfo.title  = _get_tag_content(output, b'^TIT2 .*: (.*)$')
	#print(taginfo.artist, taginfo.album, taginfo.year, taginfo.number, taginfo.title)
	if type(taginfo.year) is bytes:
		taginfo.year = taginfo.year.decode('utf-8')
	return taginfo

def get_artist_subdir(root_path, artist_dir):
	for entry in os.listdir(root_path):
		full_entry_path = os.path.join(root_path, entry)
		if not os.path.isdir(full_entry_path):
			continue
		for artist in os.listdir(full_entry_path):
			if artist.lower() == artist_dir.lower():
				return entry, artist
	return '', artist_dir

default_subdir = None
def get_new_filename(taginfo, root_path, use_subdirs):
	global default_subdir
	artist_dir = taginfo.artist
	album_dir  = '{0}-{1}'.format(taginfo.year, taginfo.album)
	filename   = '{0:0>2}-{1}.mp3'.format(taginfo.number, taginfo.title).replace('/', '-')
	if use_subdirs:
		artist_subdir, artist_dir = get_artist_subdir(root_path, artist_dir)
		if not artist_subdir:
			if not default_subdir:
				subdirs = os.listdir(root_path)
				print("Cannot determine subdir for {0}.".format(taginfo.artist))
				for index, subdir in enumerate(subdirs):
					print('{0}: {1}'.format(index, subdir))
				result_index = -1
				while result_index not in range(len(subdirs)):
					result_index = input('Which subdir?')
					try:
						result_index = int(result_index)
					except ValueError as e:
						continue
				default_subdir = subdirs[result_index]
			artist_subdir = default_subdir
		return os.path.join(root_path, artist_subdir, artist_dir, album_dir, filename)
	else:
		return os.path.join(root_path, artist_dir, album_dir, filename)


def get_tags_from_filesystem(filepaths):
	fs_tags = {}
	for index, filepath in enumerate(filepaths, 1):
		taginfo = TagInfo()
		taginfo.fs_index = index
		dirname, filename = os.path.split(filepath)
		filename, ext = os.path.splitext(filename)

		DIR_PATTERNS = [
				r'(?P<artist>.+) ?- ?(?P<year>[0-9]+) ?- ?(?P<album>.+)',
				r'(?P<artist>.+) ?\[(?P<year>[0-9]+)\] ?(?P<album>.+)',
				r'(?P<artist>.+) ?- ?(?P<album>.+) - \(?(?P<year>[0-9]{4})\)?',
				r'(?P<artist>.+) ?- ?(?P<album>.+) \(?(?P<year>[0-9]{4})\)?',
				r'(?P<artist>.+) ?- ?(?P<album>.+) \((?P<year>[0-9]{4})( - Advance)?\)',
				r'\[?(?P<year>[0-9]+)\]? ?- ?(?P<album>.+)',
				r'(?P<year>[0-9]+)_(?P<album>.+)',
				r'(?P<year>[0-9]+). *(?P<album>.+)',
				r'(?P<artist>.+) ?- ?(?P<album>.+)',
				r'(?P<album>.+)'
				]
		dir_parts = parse(DIR_PATTERNS, dirname)
		if dir_parts:
			if 'year' in dir_parts: taginfo.year = dir_parts['year']
			if 'album' in dir_parts: taginfo.album = dir_parts['album']
			if 'artist' in dir_parts: taginfo.artist = dir_parts['artist']
		else:
			print("Unknown dirname pattern: " + dirname)

		if not taginfo.artist:
			uplevel_dir = os.path.basename(os.path.normpath(os.path.abspath(dirname).replace(dirname, '')))
			uplevel_dir = uplevel_dir.replace(' - Discography', '')
			taginfo.artist = uplevel_dir

		FILE_PATTERNS = [
				r'(?P<number>[0-9]+) ?- ?(?P<title>.+)',
				r'(?P<number>[0-9]+)\.(?P<title>.+)',
				r'(?P<number>[0-9]+)_(?P<title>.+)',
				r'(?P<number>[0-9]+) (?P<title>.+)',
				r'(?P<number>[0-9]+)(?P<title>.+)',
				r'(?P<title>.+)'
				]
		file_parts = parse(FILE_PATTERNS, filename)
		if file_parts:
			if 'number' in file_parts: taginfo.number = file_parts['number']
			if 'title' in file_parts: taginfo.title = file_parts['title']
		else:
			print("Unknown filename pattern: " + filename)

		if not taginfo.number:
			taginfo.number = index

		fs_tags[filepath] = taginfo
	return fs_tags

def repair_tags(tags, args):
	fs_tags = get_tags_from_filesystem(sorted(tags.keys()))

	for filename in tags:
		taginfo = tags[filename]
		fs_taginfo = fs_tags[filename]
		
		if (args.FORCE_FS_TAGS or not taginfo.artist) and fs_taginfo.artist: taginfo.artist = fs_taginfo.artist
		if (args.FORCE_FS_TAGS or not taginfo.year)   and fs_taginfo.year:   taginfo.year = fs_taginfo.year
		if (args.FORCE_FS_TAGS or not taginfo.album)  and fs_taginfo.album:  taginfo.album = fs_taginfo.album
		if (args.FORCE_FS_TAGS or not taginfo.number) and fs_taginfo.number: taginfo.number = fs_taginfo.number
		if (args.FORCE_FS_TAGS or not taginfo.title)  and fs_taginfo.title:  taginfo.title = fs_taginfo.title
		if args.ALBUM:
			taginfo.album = args.ALBUM
		if args.ARTIST:
			taginfo.artist = args.ARTIST
		if args.YEAR:
			taginfo.year = args.YEAR
		#print(taginfo.artist, taginfo.album, taginfo.year, taginfo.number, taginfo.title)

		album_parts = _split_path(taginfo.album)
		if re.match(r'CD ?[0-9]', album_parts[-1], re.IGNORECASE):
			taginfo.album = reduce(os.path.join, album_parts[:-1])
		taginfo.album = taginfo.album.replace('(Deluxe Edition)', '')
		taginfo.album = taginfo.album.replace('(320k)', '')
		taginfo.album = taginfo.album.replace('(limited edition)', '')
		taginfo.album = taginfo.album.replace('[DemonUploader]', '')
		taginfo.album = taginfo.album.replace(' (Remastered)', '')
		taginfo.artist = taginfo.artist.replace('[Discography]', '')
		taginfo.artist = taginfo.artist.replace(' - дискография', '')
		taginfo.artist = taginfo.artist.replace('-Collection.2000-2008.MP3.320kbps', '')
		taginfo.artist = taginfo.artist.replace('The.', 'The ')

		try:
			taginfo.number = int(taginfo.number)
		except ValueError:
			print("Track number is not a number: {0}".format(taginfo.number))
			taginfo.number = fs_taginfo.number

		taginfo.title = taginfo.title.replace(args.SEPARATOR, ' ')
		taginfo.title = taginfo.title.replace('_', ' ')
		if taginfo.title.startswith(str(taginfo.number)):
			if taginfo.title[len(str(taginfo.number))] in '-. _':
				taginfo.title = taginfo.title[len(str(taginfo.number)):].lstrip()

		taginfo.album = taginfo.album.replace(args.SEPARATOR, ' ')
		if 'CD 1' in taginfo.album:
			taginfo.album = taginfo.album.replace(' - CD 1', '')
			taginfo.number += 100
		if 'CD 2' in taginfo.album:
			taginfo.album = taginfo.album.replace(' - CD 2', '')
			taginfo.number += 200

		taginfo.artist = taginfo.artist.replace(args.SEPARATOR, ' ')
		taginfo.artist = taginfo.artist.replace(args.SEPARATOR, ' ')

		taginfo.title  = taginfo.title.strip()
		taginfo.artist = taginfo.artist.strip()
		taginfo.album  = taginfo.album.strip()
		taginfo.number = taginfo.number
		taginfo.year   = taginfo.year.strip()

		taginfo.artist = re.sub(' +', ' ', taginfo.artist)
		taginfo.album = re.sub(' +', ' ', taginfo.album)
		taginfo.title = re.sub(' +', ' ', taginfo.title)

		m = re.match(r'(.*[^ ]) ?- ?(.*)', taginfo.title)
		if m:
			if m.group(1).lower() == taginfo.artist.lower():
				taginfo.title = m.group(2)

		m = re.match(r'([0-9]{4}).*', taginfo.year)
		if m:
			taginfo.year = m.group(1)
		else:
			taginfo.year = None
		
		taginfo.album = ''.join([word.capitalize() for word in re.split(r"([\w']+)", taginfo.album)])
		taginfo.title = ''.join([word.capitalize() for word in re.split(r"([\w']+)", taginfo.title)])
		taginfo.artist = ''.join([word.capitalize() for word in re.split(r"([\w']+)", taginfo.artist)])

	most_frequent_year = get_most_frequent_value([tags[filename].year for filename in tags])
	for filename in tags:
		tags[filename].year = most_frequent_year

	most_frequent_artist = get_most_frequent_value([tags[filename].artist for filename in tags])
	for filename in tags:
		tags[filename].artist = most_frequent_artist

	return tags

def guess_encoding(tags):
	encodings = []
	for filename in tags:
		taginfo = tags[filename]
		if type(taginfo.artist) is bytes:
			encodings.append(chardet.detect(taginfo.artist)['encoding'])
		if type(taginfo.album) is bytes:
			encodings.append(chardet.detect(taginfo.album)['encoding'])
		if type(taginfo.title) is bytes:
			encodings.append(chardet.detect(taginfo.title)['encoding'])

	non_ascii_encodings = filter(lambda x: x != "ascii", encodings)
	if non_ascii_encodings:
		encodings = non_ascii_encodings
	return get_most_frequent_value(encodings)

def reencode_tags(tags, args):
	encoding = None
	if args.ENCODING:
		encoding = args.ENCODING
		print("Using encoding: {0}".format(encoding))
	else:
		encoding = guess_encoding(tags)
		if encoding:
			print("Encoding detected: {0}".format(encoding))
	if not encoding:
		encoding = 'ascii'
	
	for filename in tags:
		taginfo = tags[filename]
		taginfo.artist = taginfo.artist.decode(encoding) if isinstance(taginfo.artist, bytes) else taginfo.artist
		taginfo.album  = taginfo.album.decode(encoding) if isinstance(taginfo.album, bytes) else taginfo.album
		taginfo.title  = taginfo.title.decode(encoding) if isinstance(taginfo.title, bytes) else taginfo.title
	
	return tags

def get_all_data(wd, args):
	mp3_filenames, other_filenames = get_dir_content(wd)
	mp3_filenames = sorted(mp3_filenames)
	tags = dict([(filename, get_taginfo_for_file(filename)) for filename in mp3_filenames])
	tags = reencode_tags(tags, args)
	tags = repair_tags(tags, args)
	new_filenames = dict([(filename, get_new_filename(tags[filename], args.NEW_ROOT_DIR, args.USE_SUBDIRS)) for filename in mp3_filenames])

	max_paths = set()
	paths_to_make = set()
	for filename in mp3_filenames:
		existing_path, path_to_make = get_exists_path_part(new_filenames[filename])
		max_paths.add(existing_path)
		path_to_make, tail = os.path.split(path_to_make)
		if path_to_make:
			paths_to_make.add(path_to_make)
	return mp3_filenames, other_filenames, tags, new_filenames, max_paths, paths_to_make

def print_all_data(mp3_filenames, other_filenames, tags, new_filenames, max_paths, paths_to_make):
	if other_filenames:
		print("These won't be stored:")
		for filename in other_filenames:
			print('\t', filename)
		print()

	print("Tags will be set:")
	for filename in mp3_filenames:
		tag = tags[filename]
		print('\tArtist: <{0}> | Album: <{1}> | Year: <{2}> | No: <{3}> | Title: <{4}> |'.format(tag.artist, tag.album, tag.year, tag.number, tag.title))
	print()

	common_src_path = get_max_common_beginning([_split_path(path) for path in mp3_filenames])
	common_dst_path = get_max_common_beginning([_split_path(new_filenames[path]) for path in mp3_filenames])
	print("Files will be placed to:")
	print("\t{0} -> {1}".format(reduce(os.path.join, common_src_path), reduce(os.path.join, common_dst_path)))
	for filename in mp3_filenames:
		src = reduce(os.path.join, get_remains(_split_path(filename), common_src_path))
		dst = reduce(os.path.join, get_remains(_split_path(new_filenames[filename]), common_dst_path))
		print("\t\t{0} -> {1}".format(src, dst))
	print

	if max_paths:
		print("This paths already exists:")
		for path in max_paths:
			print('\t' + path)
		print
	
	if paths_to_make:
		print("This subpaths will be created:")
		for path in paths_to_make:
			print('\t' + path)
		print
	
def main():
	parser = argparse.ArgumentParser(description="Collects music to the music library")
	parser.add_argument("wd", default=os.getcwd(), help="Working directory (default to current)")
	parser.add_argument("--force_fs_tags", dest="FORCE_FS_TAGS", action='store_true', default=False, help="Force filling MP3 tags from filenames instead of current ID3v2 tags")
	parser.add_argument("--force_artist", dest="ARTIST", default="", required=False, help="Override tagged artist name with this value")
	parser.add_argument("--force_year", dest="YEAR", default="", required=False, help="Override tagged year with this value")
	parser.add_argument("--force_album", dest="ALBUM", default="", required=False, help="Override tagged album title with this value")
	parser.add_argument("--force_encoding", dest="ENCODING", default="", required=False, help="Use this encoding on all tracks' tags")
	parser.add_argument("--root_dir", dest="NEW_ROOT_DIR", default=".", required=True, help="Library root directory")
	parser.add_argument("--use_subdirs", dest="USE_SUBDIRS", default=False, required=False, help="Is library directory contains all artist dirs in some subdirs (like by genre etc)?")
	parser.add_argument("--separator", dest="SEPARATOR", default=" ", required=False, help="Separator to use instead of space")
	args = parser.parse_args()

	wd = args.wd

	mp3_filenames, other_filenames, tags, new_filenames, max_paths, paths_to_make = get_all_data(wd, args)
	if not mp3_filenames:
		print("There is no MP3 files in here!")
		return
	print_all_data(mp3_filenames, other_filenames, tags, new_filenames, max_paths, paths_to_make)

	yes = input("Proceed (y/n)?")
	if yes == 'y':
		for filename in mp3_filenames:
			new_filename = new_filenames[filename]
			path, name = os.path.split(new_filename)
			if not os.path.exists(path):
				os.makedirs(path)
				print("Path created: {0}".format(path))
			shutil.copyfile(filename, new_filename)
			#print("Copied file: {0} -> {1}".format(filename, new_filename))
			
			taginfo = tags[filename]
			subprocess.check_call(["id3v2", "-D", new_filename])
			args = ["id3v2"]
			args += ["-2"]
			args += ["-a", taginfo.artist]
			args += ["-A", taginfo.album]
			args += ["-t", taginfo.title]
			args += ["-y", taginfo.year]
			args += ["-T", '{0:0>2}'.format(taginfo.number)]
			args += [new_filename]
			subprocess.check_call(args)
			#print("Successfully reset tags for {0}.".format(new_filename))


if __name__ == "__main__":
	main()
