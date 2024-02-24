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


class QueueEvent:
	def __init__(self, typ, name):
		self.typ = typ
		self.name = name
	def __str__(self):
		return f'QueueEvent(type={self.typ}, name={self.name})'


g_key_queue = queue.Queue()
g_running = True
g_tracking = False


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
	global g_running
	g_running = False
	g_key_queue.put(QueueEvent('exit', 'exit key triggered'))


def xXxRealHandleKeypressxXx(event, was_pr: dict):
	""" Parse presses more-properly
		Used inside of loop after keyboard.read_event()
		Returns:
			- +1 if keypress was triggered
			-  0 if nothing happened
			- -1 if should break loop
	"""
	if event.event_type == kbd.KEY_DOWN:
		
		# Loop exit switch
		if event.name == Config.KEY_EXIT_LOOP:
			return -1

		# Initially assume unpressed
		if event.name not in was_pr:
			was_pr[event.name] = False

		if was_pr[event.name] == True:
			# Skip if key was not released yet
			return 0
		elif was_pr[event.name] == False:
			# Trigger keypress
			was_pr[event.name] = True
			return 1

	elif event.event_type == kbd.KEY_UP:
		# Unpress everyyy key
		was_pr[event.name] = False
		return 0


def input_thread_func():
	""" """
	global g_running, g_tracking

	was_pressed = {}
	while g_running:
		event = kbd.read_event(suppress=g_tracking)

		stat = xXxRealHandleKeypressxXx(event, was_pressed)
		if stat < 0:
			trigger_exit()
			break

		elif stat > 0:
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