#-----------------------------------------------------------------------------------
# LuaDev Sublime Text Plugin
# Author: tongxuehu@gmail.com
# Version: 1.0
# Description: Lua autocomplete improvements
#-----------------------------------------------------------------------------------

import sublime
import sublime_plugin
import os
import re
import threading
import subprocess

def is_lua_file(filename):
	return filename[-4:] == ".lua"

def parse_hint(params):
	params = params.split(",")
	hint = ""
	count = 1
	for param in params:
		hint = hint + "${" + str(count) + ":" + param + "}"
		if count != len(params):
			hint += ","
		count = count + 1
	return hint

class KMethod:
	def __init__(self, name, signature, filename, hintStr, className):
		self._name = name
		self._filename = filename;
		self._signature = signature
		self._hintStr = hintStr
		self._className = className
	def name(self):
		return self._name
	def signature(self):
		return self._signature
	def filename(self):
		return self._filename
	def hint(self):
		return self._hintStr
	def class_name(self):
		return self._className


class KSigns:
	files = {}

	def has_file(self, file):
		return file in self.files

	def clear_file(self, file):
		self.files[file] = []

	def add_mathod(self, path, name, signature, filename, class_name):
		if not self.files[path]:
			self.files[path] = []

		hint = parse_hint(signature)
		methon = KMethod(name, signature, filename, hint, class_name)
		self.files[path].append(methon)

	def get_autocomplete_list(self, word):
		autocomplete_list = []
		for file in self.files:
			method_list = self.files[file]
			for method in method_list:
				if word in method.class_name():
					if method.class_name() not in autocomplete_list:
						autocomplete_list.append((method.class_name() + '\t' + method.filename(), method.class_name()))
					method_str_hint = method.name() + '(' + method.signature()+ ')'
					if method.class_name() != "":
						method_str_hint = method.class_name() + "." + method_str_hint;
					method_str_to_append = method_str_hint + '\t' + method.filename()
					autocomplete_list.append((method_str_to_append, method_str_hint))
				if word in method.name():
					method_str_to_append = method.name() + '(' + method.signature()+ ')'
					if method.class_name() != "":
						method_str_to_append = method_str_to_append + " - " + method.class_name() + '\t' + method.filename()
					method_str_hint = method.name() + '(' + method.hint() + ')'
					autocomplete_list.append((method_str_to_append, method_str_hint))
		autocomplete_list = list(set(autocomplete_list))
		autocomplete_list.sort()
		return autocomplete_list
	

class LuaDevCollectorThread(threading.Thread):
	def __init__(self, collector, path_list, timeout_seconds): 
		self.collector = collector
		self.timeout = timeout_seconds
		self.path_list = path_list
		threading.Thread.__init__(self)

	def parse_file(self, file_path):
		print("parse file " + file_path)
		self.collector.clear_file(file_path)
		file = open(file_path, "r", encoding="utf-8")
		for line in file:
			if not "function" in line:
				continue

			matches = re.search('function\s*(\w+)[:\.](\w+)\s*\((.*)\)', line)
			if matches != None:
				file_name = os.path.basename(file_path)
				class_name = matches.group(1)
				method_name = matches.group(2)
				params = matches.group(3)
				self.collector.add_mathod(file_path, method_name, params, file_name, class_name)
				continue

			matches = re.search('function\s*(\w+)\s*\((.*)\)', line)
			if matches != None:
				file_name = os.path.basename(file_path)
				class_name = ""
				method_name = matches.group(1)
				params = matches.group(2)
				hint = parse_hint(params)
				self.collector.add_mathod(file_path, method_name, params, file_name, class_name)
				continue


	def find_file(self, dir, skip_loaded_file):
		file_list = []
		for name in os.listdir(dir):
			path = os.path.join(dir, name)
			if os.path.isfile(path):
				if not is_lua_file(path):
					continue
				if skip_loaded_file and self.collector.has_file(path):
					continue
				file_list.append(path)
			else:
				file_list += self.find_file(path, skip_loaded_file)
		return file_list


	def run(self):
		file_list = []
		for path in self.path_list:
			if os.path.isfile(path):
				file_list.append(path)
			else:
				file_list += self.find_file(path, True)
		for file in file_list:
			self.parse_file(file)


	def stop(self):
		if self.isAlive():
			self._Thread__stop()


class LuaDevCollector(KSigns, sublime_plugin.EventListener):
	_collector_thread = None
	_wait_thread = None

	_local_token = []

	TIMEOUT_MS = 200
	_pending = 0

	def reload_path(self, view):
		current_file = view.file_name()
		if not is_lua_file(current_file):
			return

		window = view.window()
		if window == None:
			return

		path_list = [current_file]
		path_list += window.folders()

		if self._collector_thread != None:
			self._collector_thread.stop()
		self._collector_thread = LuaDevCollectorThread(self, path_list, 30)
		self._collector_thread.start()

	def on_load(self, view):
		self.reload_path(view)

	def on_post_save(self, view):
		self.reload_path(view)

		current_file = view.file_name()
		if not is_lua_file(current_file):
			return

		self._pending = self._pending + 1
		sublime.set_timeout(lambda: self.parse(view, current_file), self.TIMEOUT_MS)

	def on_query_completions(self, view, prefix, locations):
		completions = []
		for keyword in self._local_token:
			if prefix in keyword:
				completions.append((keyword + "\t" + "- local", keyword))

		current_file = view.file_name()
		if is_lua_file(current_file):
			completions += self.get_autocomplete_list(prefix)
		return (completions, sublime.OP_EQUAL)

	def parse(self, view, file):
		text = view.substr(sublime.Region(0, view.size()))
		self._local_token = re.findall(r'\w+', text)
		self._local_token = list(set(self._local_token))
		self._local_token.sort()

		self._pending = self._pending - 1
		if self._pending > 0:
			return
	
		packages_path = sublime.packages_path()
		cmd = "\"" + packages_path + "\\LuaDev\\luac5.1.exe\" -p " + file
		p = subprocess.Popen(cmd, stdin=subprocess.PIPE, stderr=subprocess.PIPE, shell=True)
		result = p.wait()
		errors = p.communicate()[1]

		view.erase_regions('lua_error')
		if result == 0:
			return

		msg = bytes.decode(errors, 'gbk')
		msg = re.findall(r"(\w+\.lua:[^$\n\r]+)", msg)[0]
		sublime.error_message(msg)
		pattern = re.compile(r':([0-9]+):')
		regions = [view.full_line(view.text_point(int(match) - 1, 0)) for match in pattern.findall(msg)]
		view.add_regions('lua_error', regions, 'invalid', 'DOT', sublime.DRAW_SQUIGGLY_UNDERLINE)
