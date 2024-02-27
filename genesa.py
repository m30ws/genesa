import json
import os
import queue
import signal # signal.SIGTERM
import socket
import sys
import threading as thr
import time

import keyboard as kbd


class Config:
	KEY_EXIT_LOOP 			= 'f8'
	KEY_ACTIVATE_TRACKING 	= 'f1'
	KEY_ACTIVATE_TRIGGERS 	= 'f2'

	KEYS_TRACKED = ['left', 'right', 'x'] # ['x', 'y', 'c', 'v', 'a']

	HOST_KINDS 		= ['host', '1']
	CLIENT_KINDS 	= ['client', '2']
	HOST 			= 'host'
	CLIENT 			= 'client'
	DEFAULT_HOST 	= 'localhost'
	DEFAULT_PORT 	= 7654

	LOG_INFO 		= 1
	LOG_WARNING 	= 2
	LOG_ERROR 		= 3

	PRESS_SHOULD_BREAK     = -1 # if loop should break
	PRESS_NOTHING_HAPPENED =  0 # if nothing happened
	PRESS_PRESSED          =  1 # if keypress was triggered
	PRESS_RELEASED         =  2 # if key was released

	EVENT_KEY 			= 'key'
	EVENT_DISCONNECT 	= 'dc'

	NB_LOOP_DELAY = 0.001#s


def log_event(*args, level=Config.LOG_INFO, **kwargs):
	""" """
	if    level == Config.LOG_INFO:    lvl_txt = 'INFO'
	elif  level == Config.LOG_WARNING: lvl_txt = 'WARNING'
	elif  level == Config.LOG_ERROR:   lvl_txt = 'ERROR'
	else:                              lvl_txt = 'LOG'

	sys.stderr.write(f'[{lvl_txt}] {time.time():12.6f}: ')
	sys.stderr.write(*args, **kwargs)
	sys.stderr.write(f'\n')


def new_event(typ, name):
	""" """
	return f'{typ}|{name}'


def parse_event(q_ev):
	""" """
	spl = q_ev.split('|')
	if len(spl) > 1:
		return spl[0], spl[1]
	return spl[0], ''


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
						g_key_queue.put(new_event(Config.EVENT_KEY, event.name))
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
g_triggers = False
g_key_queue = queue.Queue()
g_hotkeys = [
	HotkeySimple(Config.KEY_EXIT_LOOP.split('+'), lambda _: trigger_exit() or -1),
	# HotkeySimple(['ctrl','c'], lambda _: trigger_exit() or -1),
	HotkeySimple(['ctrl','c'], lambda _: log_event(f'forcibly exiting (ctrl+c)', level=Config.LOG_WARNING) or os.kill(os.getpid(), signal.SIGTERM)),
]
g_kind = None # host,client
g_addr_player_mapping = {} # filled dynamically as players "connect"
g_player_controls_mapping = {} # loaded from disk (as json) on startup


def trigger_exit():
	""" """
	global g_tracking, g_running

	if g_kind == Config.CLIENT:
		g_key_queue.put(new_event(Config.EVENT_DISCONNECT, None))
		time.sleep(1) # wait until sent
	
	g_tracking = False
	g_running = False


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
	global g_running, g_tracking, g_triggers

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
				if hk.check(event) < 0:
					break
			if not g_running:
				break

			# parse the rest
			if event.name == Config.KEY_ACTIVATE_TRACKING and g_kind != Config.HOST:
				g_tracking = not g_tracking
				if g_tracking:
					log_event(f'tracking active [{Config.KEY_ACTIVATE_TRACKING.upper()}]', level=Config.LOG_WARNING)
				else:
					log_event(f'tracking disabled [{Config.KEY_ACTIVATE_TRACKING.upper()}]', level=Config.LOG_WARNING)

			elif event.name == Config.KEY_ACTIVATE_TRIGGERS and g_kind == Config.HOST:
				g_triggers = not g_triggers
				if g_triggers:
					log_event(f'triggers active [{Config.KEY_ACTIVATE_TRIGGERS.upper()}]', level=Config.LOG_WARNING)
				else:
					log_event(f'triggers disabled [{Config.KEY_ACTIVATE_TRIGGERS.upper()}]', level=Config.LOG_WARNING)

			else:
				if not g_tracking:
					continue

				if g_kind == Config.CLIENT and event.name in Config.KEYS_TRACKED:
					g_key_queue.put(new_event(Config.EVENT_KEY, event.name))
					log_event(f'pressed: {event.name}')

	log_event('exiting input thread...')


def host_server_thread_func(host=Config.DEFAULT_HOST, port=Config.DEFAULT_PORT):
	""" """
	# await user selection in case started early
	while not g_kind:
		time.sleep(0.5)
	if g_kind != Config.HOST:
		return

	with socket.socket(family=socket.AF_INET, type=socket.SOCK_DGRAM) as serv:
		serv.setblocking(0)
		serv.bind((host, port))
		log_event(f'server started {serv.getsockname()}')

		while g_running:

			data, sender = None, None
			while g_running and (data,sender)==(None,None):
				try:
					data, sender = serv.recvfrom(2048)
				except BlockingIOError:
					pass
				time.sleep(Config.NB_LOOP_DELAY)
			if not g_running:
				break

			g_key_queue.put((data, sender))

	log_event('exiting host server thread...')


def host_parse_thread_func():
	""" """
	global g_addr_player_mapping

	# await user selection in case started early
	while not g_kind:
		time.sleep(0.5)
	if g_kind != Config.HOST:
		return

	while g_running:

		data = None
		while g_running and data is None:
			try:
				data, sender = g_key_queue.get(block=False)
			except queue.Empty:
				pass
			time.sleep(Config.NB_LOOP_DELAY)
		if not g_running:
			break

		typ, data = parse_event(data.decode('utf-8'))

		if typ == 'key':
			# find or create player
			player_id = None
			try:
				player_id = g_addr_player_mapping[sender]

			except KeyError:
				curr_players = len(g_addr_player_mapping)
				max_players = len(g_player_controls_mapping)

				# check if theres enough space and add new player
				if curr_players < max_players:
					g_addr_player_mapping[sender] = curr_players
					player_id = curr_players
					log_event(f'player {player_id} connected {sender}')
				else:
					# if not log error and continue;
					capac = f'{curr_players}/{max_players}' # print capacity for sanity check
					log_event(f'new player attempted to connect but game full {capac} {sender}', level=Config.LOG_ERROR)
					continue

			try:
				# find key mapping
				keypr = g_player_controls_mapping[player_id][data]

				# trigger
				if g_triggers:
					log_event(f'{sender}[player {player_id}]  TRIGGERED  {data} (-> HOST {keypr})')
					kbd.press(keypr)

			except KeyError:
				# if doesn't exist log error and continue;
				log_event(f'player control mapping doesn\'t exist {sender} -> {data}', level=Config.LOG_ERROR)

		elif typ == 'dc':
			if sender in g_addr_player_mapping:
				log_event(f'player {g_addr_player_mapping[sender]} {sender} disconnected')
				del g_addr_player_mapping[sender]

		else:
			log_event(f'(echo) {data} {sender}', level=Config.LOG_WARNING)

	log_event('exiting host parse thread...')


def client_thread_func(host=Config.DEFAULT_HOST, port=Config.DEFAULT_PORT):
	""" """
	# await user selection in case started early
	while not g_kind:
		time.sleep(0.5)
	if g_kind != Config.CLIENT:
		return

	with socket.socket(family=socket.AF_INET, type=socket.SOCK_DGRAM) as serv:
		while g_running:

			next_event = None
			while g_running and next_event is None:
				try:
					next_event = g_key_queue.get(block=False)
				except queue.Empty:
					pass
				time.sleep(Config.NB_LOOP_DELAY)
			if not g_running:
				break
			
			dat = next_event.encode('utf-8')
			log_event(f'{(host, port)} : {dat}')
			serv.sendto(dat, (host, port))
			log_event(f'-- sent {dat} to {(host, port)}')

	log_event('exiting client thread...')


def select_kind():
	""" """
	def set_kind(k):
		global g_kind
		if kind in Config.HOST_KINDS:
			g_kind = Config.HOST
		elif kind in Config.CLIENT_KINDS:
			g_kind = Config.CLIENT
		else:
			return None
		return g_kind

	if len(sys.argv) > 1:
		kind = sys.argv[1]
		if set_kind(kind): return kind
		print(f'Invalid cmd kind')

	# not specified in args or invalid args,
	# acquire interactively
	default_kind = Config.CLIENT
	while True:
		kind = input(f"1) Host ({'|'.join(Config.HOST_KINDS)})\n" \
		             f"2) Client ({'|'.join(Config.CLIENT_KINDS)})\n" \
		             f"Kind? [{default_kind}] ")
		if kind.strip() == '':
			kind = default_kind
		if set_kind(kind): return kind
		print(f'Invalid option')


def load_mappings(filename="./config.json"):
	""" """
	global g_player_controls_mapping
	try:
		with open(filename, 'r', encoding='utf-8') as fp:
			cfg_ = json.load(fp)
		
		cfg = {}
		for k, v in cfg_['keybinds'].items():
			cfg[int(k)] = v

		g_player_controls_mapping = cfg
		log_event(f'loaded mappings: {g_player_controls_mapping}')

	except Exception as e:
		log_event(f'unable to load config {e}', level=Config.LOG_ERROR)
		# sample mapping; maps only X key for each player (CLIENT x/x/x -> HOST s/k/n)
		g_player_controls_mapping = {0: {"x": "s"}, 1: {"x": "k"}, 2: {"x": "n"}}


def main():
	""" """
	global g_tracking

	try:
		kind = select_kind()
		log_event(f'selected kind: {kind}')

	except KeyboardInterrupt:
		return 0

	threads = {
		'input_thread': 		thr.Thread(target=input_thread_func, daemon=True),
		'client_thread': 		thr.Thread(target=client_thread_func, daemon=True),
		'host_server_thread': 	thr.Thread(target=host_server_thread_func, daemon=True),
		'host_parse_thread': 	thr.Thread(target=host_parse_thread_func, daemon=True),
	}

	#### 
	if kind == Config.CLIENT:
		threads['client_thread'].start()
		
		log_event(f'Exit bind [{Config.KEY_EXIT_LOOP.upper()}]')
		log_event(f'Tracking [{Config.KEY_ACTIVATE_TRACKING.upper()}]: {g_tracking}')
	else: # == Config.HOST
		load_mappings()

		g_tracking = False
		threads['host_server_thread'].start()
		threads['host_parse_thread'].start()

		log_event(f'Exit bind [{Config.KEY_EXIT_LOOP.upper()}]')
		log_event(f'Triggers [{Config.KEY_ACTIVATE_TRIGGERS.upper()}]: {g_triggers}')

	threads['input_thread'].start()

	for t in threads.values():
		if not t.is_alive(): continue
		try:
			t.join()
		except RuntimeError:
			pass

	return 0


if __name__=='__main__':
	exit(main())