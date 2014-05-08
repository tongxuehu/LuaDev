#-----------------------------------------------------------------------------------
# LuaDev Sublime Text Plugin
# Author: tongxuehu@gmail.com
# Version: 1.2
# Description: Lua autocomplete improvements
#-----------------------------------------------------------------------------------

import sublime
import sublime_plugin
import os
import re
import threading
import subprocess

def is_lua_file(filename):
	return filename and filename.endswith(".lua")

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

def start_with(str, prefix):
	return

class KMethod:
	def __init__(self, name, signature, filename, hintStr, className, line_index, full_path):
		self._name = name
		self._lineindex = line_index
		self._filename = filename
		self._signature = signature
		self._hintStr = hintStr
		self._className = className
		self._fullpath = full_path
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
	def line_index(self):
		return self._lineindex
	def full_path(self):
		return self._fullpath


class KSigns:
	files = {}

	def has_file(self, file):
		return file in self.files

	def clear_file(self, file):
		self.files[file] = []

	def add_mathod(self, path, name, signature, filename, class_name, line_index, full_path):
		if not self.files[path]:
			self.files[path] = []

		hint = parse_hint(signature)
		methon = KMethod(name, signature, filename, hint, class_name, line_index, full_path)
		self.files[path].append(methon)

	def get_autocomplete_list(self, word, class_name = None):
		autocomplete_list = []
		for file in self.files:
			method_list = self.files[file]
			for method in method_list:
				if class_name == None:
					method_class_name = method.class_name()
					if method_class_name != "":
						if method_class_name.startswith(word) and method_class_name not in autocomplete_list:
							autocomplete_list.append((method.class_name() + '\t' + method.filename(), method.class_name()))
					elif method.name().startswith(word):
						method_str_to_append = method.name() + '(' + method.signature()+ ')'
						if method.class_name() != "":
							method_str_to_append = method_str_to_append + " - " + method.class_name() + '\t' + method.filename()
						method_str_hint = method.name() + '(' + method.hint() + ')'
						autocomplete_list.append((method_str_to_append, method_str_hint))
				elif class_name == method.class_name():
					method_str_to_append = method.name() + '(' + method.signature()+ ')'
					if method.class_name() != "":
						method_str_to_append = method_str_to_append + " - " + method.class_name() + '\t' + method.filename()
					method_str_hint = method.name() + '(' + method.hint() + ')'
					autocomplete_list.append((method_str_to_append, method_str_hint))
		autocomplete_list = list(set(autocomplete_list))
		autocomplete_list.sort()
		return autocomplete_list

	def get_methods_by_key(self, key, class_name = None):
		if class_name == None:
			class_name = ""

		methods = []
		for file in self.files:
			method_list = self.files[file]
			for method in method_list:
				if class_name == method.class_name() and key == method.name():
					methods.append(method)	
		return methods

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
		line_index = 0
		for line in file:
			line_index += 1
			if not "function" in line:
				continue

			matches = re.search('function\s*(\w+)[:\.](\w+)\s*\((.*)\)', line)
			if matches != None:
				file_name = os.path.basename(file_path)
				class_name = matches.group(1)
				method_name = matches.group(2)
				params = matches.group(3)
				self.collector.add_mathod(file_path, method_name, params, file_name, class_name, line_index, file_path)
				continue

			matches = re.search('function\s*(\w+)\s*\((.*)\)', line)
			if matches != None:
				file_name = os.path.basename(file_path)
				class_name = ""
				method_name = matches.group(1)
				params = matches.group(2)
				hint = parse_hint(params)
				self.collector.add_mathod(file_path, method_name, params, file_name, class_name, line_index, file_path)
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
			if not os.path.exists(path):
				continue
			if os.path.isfile(path):
				file_list.append(path)
			else:
				file_list += self.find_file(path, True)
		for file in file_list:
			try:
				self.parse_file(file)
			except Exception as e:
				print(str(e) + " at " + file)
		print("lua dev parsed " + str(len(file_list)) + " files!")
			
	def stop(self):
		if self.isAlive():
			self._Thread__stop()


class LuaDevCollector(KSigns, sublime_plugin.EventListener):
	_collector_thread = None
	_wait_thread = None

	TIMEOUT_MS = 200
	_pending = 0

	_modified_delete_flag = False

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

	def on_modified_async(self, view):
		if self._modified_delete_flag:
			self._modified_delete_flag = False
			return

		current_file = view.file_name()
		if not is_lua_file(current_file):
			return

		selection = view.sel()[0]
		if selection.a > 0:
			prefix = view.substr(selection.a - 1)
			if prefix == ".":
				view.run_command("auto_complete")				

	def on_query_completions(self, view, prefix, locations):
		print("on_query_completions", prefix, locations)
		class_name = None
		localtion = locations[0] - 1
		if localtion >= 1 and view.substr(localtion) == '.':
			word_region = view.word(localtion - 1)
			class_name = view.substr(word_region)

		completions = []

		local_comletions = view.extract_completions(prefix)
		for key in local_comletions:
			completions.append((key + "\t" + "- local", key))

		current_file = view.file_name()
		if is_lua_file(current_file):
			completions += self.get_autocomplete_list(prefix, class_name)
		return (completions, -1)

	def on_text_command(self, view, command_name, args):
		print("on_text_command", command_name, args)
		self._modified_delete_flag = True
		if False and command_name == "drag_select" and args["event"]["button"] == 1 and "additive" in args.keys() and args["additive"]:
			selection = view.sel()[0]
			if selection.a <= 0:
				return
			word_region = view.word(selection.a - 1)
			word = view.substr(word_region)
			class_name = None
			if word_region.a > 2 and view.substr(word_region.a - 1) == ".":
				class_name_region = view.word(word_region.a - 2)
				class_name = view.substr(class_name_region)

			methods = self.get_methods_by_key(word, class_name)
			if len(methods) == 1:
				method = methods[0]
				view.window().open_file(method.full_path() + ":" + str(method.line_index()), sublime.ENCODED_POSITION)
			else:
				menus = []
				for method in methods:
					menus.append(method.class_name() + "." + method.name() + "\t" + method.filename())
				view.show_popup_menu(menus, None)
		elif command_name == "left_delete" or command_name == "right_delete":
			self._modified_delete_flag = True
		return

	def parse(self, view, file):
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
