import queue
import socket
import sys
import threading as thr
import time

import keyboard as kbd


class Config:
	KEY_EXIT_LOOP = 'esc'
	KEY_ACTIVATE_TRACKING = 'f7'
	KEYS_TRACKED = ['a','y','x','c','v']

	LOG_INFO = 1
	LOG_WARNING = 2
	LOG_ERROR = 3

	PRESS_SHOULD_BREAK     = -1 # if loop should break
	PRESS_NOTHING_HAPPENED =  0 # if nothing happened
	PRESS_PRESSED          =  1 # if keypress was triggered
	PRESS_RELEASED         =  2 # if key was released


class QueueEvent:
	def __init__(self, typ, name):
		self.typ = typ
		self.name = name
	def __str__(self):
		return f'QueueEvent(type={self.typ}, name={self.name})'


class HotkeyTracker:
	def __init__(self, press_seq, cb):
		""" """
		self.press_seq = press_seq
		self.cb = cb

	def check(self, event):
		""" """
		return 0


class HotkeySimple(HotkeyTracker):
	def __init__(self, press_seq, cb):
		""" """
		super(HotkeySimple, self).__init__(press_seq, cb)
		self.idx = 0

	def check(self, event):
		""" """
		if event.name == self.press_seq[self.idx]:
			if event.event_type == kbd.KEY_UP:
				self.idx = 0
				return 0

			elif event.event_type == kbd.KEY_DOWN:
				self.idx += 1

				# check if complete hotkey captured
				if self.idx >= len(self.press_seq):
					self.idx = 0

					# still note down keypress
					if g_tracking:
						g_key_queue.put(QueueEvent('key', event.name))
						log_event(f'pressed: {event.name}')

					return self.cb(event) or 0
				else:
					# continue capturing in next iteration
					return 0
			else:
				return 0

		else:
			if event.event_type == kbd.KEY_DOWN:
				self.idx = 0
			return 0


class HotkeyATMT(HotkeyTracker):
	def __init__(self, press_seq, cb):
		""" """
		HotkeyTracker.__init__(press_seq, cb)

	def check(self, event):
		""" """
		pass


g_running = True
g_tracking = False
g_key_queue = queue.Queue()
g_hotkeys = [
	HotkeySimple(['ctrl','c'], lambda _: trigger_exit() or -1),
]


def log_event(*args, level=Config.LOG_INFO, **kwargs):
	""" """
	if    level == Config.LOG_INFO:    lvl_txt = 'INFO'
	elif  level == Config.LOG_WARNING: lvl_txt = 'WARNING'
	elif  level == Config.LOG_ERROR:   lvl_txt = 'ERROR'
	else:                              lvl_txt = 'LOG'

	sys.stderr.write(f'[{lvl_txt}] ')
	sys.stderr.write(*args, **kwargs)
	sys.stderr.write(f'\n')


def trigger_exit():
	""" """
	global g_tracking, g_running
	g_tracking = False
	g_running = False
	g_key_queue.put(QueueEvent('exit', 'exit key triggered'))


def xXxRealHandleKeypressxXx(event, was_pressed: dict):
	""" Parse presses more-properly
		Used inside of loop after keyboard.read_event()
		Returns:
			- -1 if loop should break
			-  0 if nothing happened
			- +1 if keypress was triggered
			- +2 if key was released
	"""
	if event.event_type == kbd.KEY_DOWN:
		
		# Loop exit switch
		if event.name == Config.KEY_EXIT_LOOP:
			return Config.PRESS_SHOULD_BREAK

		# Initially assume unpressed
		if event.name not in was_pressed:
			was_pressed[event.name] = False

		if was_pressed[event.name] == True:
			# Skip if key was not released yet
			return Config.PRESS_NOTHING_HAPPENED
		elif was_pressed[event.name] == False:
			# Trigger keypress
			was_pressed[event.name] = True
			return Config.PRESS_PRESSED

	elif event.event_type == kbd.KEY_UP:
		# Unpress everyyy key
		was_pressed[event.name] = False
		return Config.PRESS_RELEASED


def input_thread_func():
	""" """
	global g_running, g_tracking
	
	was_pressed = {}
	while g_running:
		event = kbd.read_event() # suppress=g_tracking)

		stat = xXxRealHandleKeypressxXx(event, was_pressed)
		if stat == Config.PRESS_SHOULD_BREAK:
			trigger_exit()
			break

		if stat == Config.PRESS_PRESSED:
			# parse hotkeys
			for hk in g_hotkeys:
				if hk.check(event) < 0: break
			if not g_running: break

			# parse the rest
			if event.name == Config.KEY_ACTIVATE_TRACKING:
				g_tracking = not g_tracking
				if g_tracking:
					log_event(f'tracking activated [{Config.KEY_ACTIVATE_TRACKING.upper()}]', level=Config.LOG_WARNING)
				else:
					log_event(f'tracking disabled [{Config.KEY_ACTIVATE_TRACKING.upper()}]', level=Config.LOG_WARNING)

			else:
				if not g_tracking:
					continue

				g_key_queue.put(QueueEvent('key', event.name))
				log_event(f'pressed: {event.name}')

	log_event('exiting input thread...')


def server_thread_func():
	""" """
	while g_running:
		next_event = None
		while next_event is None:
			try:
				next_event = g_key_queue.get(block=False)
			except queue.Empty:
				pass
			time.sleep(0.01)

		if next_event.typ == 'exit':
			break

		log_event(f'{next_event}')

	log_event('exiting server thread...')


def main():
	""" """
	threads = {
		'input_thread' : thr.Thread(target=input_thread_func, daemon=True),
		'server_thread': thr.Thread(target=server_thread_func, daemon=True)
	}

	for t in threads.values():
		t.start()

	##
	log_event(f'Tracking [{Config.KEY_ACTIVATE_TRACKING.upper()}]: {g_tracking}')
	# log_event(f'thread ids:')
	# for n, t in threads.items():
	# 	log_event(f'  {n}: {t.native_id}')
	##

	try:
		kbd.wait(Config.KEY_EXIT_LOOP)
	except KeyboardInterrupt:
		trigger_exit()

	for t in threads.values():
		t.join()

	return 0


if __name__=='__main__':
	exit(main())