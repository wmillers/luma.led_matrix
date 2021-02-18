#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Copyright (c) 2017-18 Richard Hull and contributors
# See LICENSE.rst for details.

import re, time, argparse
from luma.led_matrix.device import max7219
from luma.core.interface.serial import spi, noop
from luma.core.render import canvas
from luma.core.virtual import viewport
from luma.core.legacy import text, show_message
from luma.core.legacy.font import proportional, CP437_FONT, TINY_FONT, SINCLAIR_FONT, LCD_FONT

from PIL import Image, ImageDraw, ImageFont

serial = spi(port=0, device=0, gpio=noop())
device = max7219(serial, cascaded=4, block_orientation=-90,rotate=0, blocks_arranged_in_reverse_order=False)

def maid(f):
    def clean(*args, **kwargs):
        try:
            f(*args, **kwargs)
        except BaseException as e:
            device.clear()
            print("\nMaid cleaned.")
            raise e
    return clean

class loop():
    def __init__(self, l):
        self.iter=l if isinstance(l, list) or isinstance(l, tuple) else [l]
        self.isSingle=len(self.iter)<=1
        self.i=-1
    
    def __next__(self):
        self.i+=1
        self.i%=len(self.iter)
        return self.iter[self.i]

def vibe_range(space, content, vibe):
    '''
    |SP [content] ACE|
    '''
    if space>=content:
        res=list(range(-vibe, space-content+vibe+1))
    else:
        res=list(range(4, -(vibe+1+4), -1))
    resR=res.copy()
    resR.reverse()
    return res+resR

SMALL_FONT=ImageFont.truetype("mem.ttf", 5)
CN_FONT=ImageFont.truetype("SimSun-special.ttf", 9)

def above(a, b):
    return a if a>b else b

@maid
def show(c="^ 3 ^", forceSingle=False, speed=25, timeout=10, vibe=None, overflow=True, font=SMALL_FONT, fontPadding=0, fill=1, quiet=False):
    v=loop(0), loop(0)
    c=str(c)
    d=int(device.size[0]/(font.size-1+fontPadding))
    isTwoRows=not forceSingle and font.size-1<=device.size[1]/2 and len(c)>d
    overflow=overflow and (font.getsize(c)[0]>device.size[0] if not isTwoRows else font.getsize(c[d:])[0]>device.size[0])
    count=0
    if overflow:
        if vibe is None:
            vibe=[0,0]
        if not isTwoRows:
            vibe[0]=font.getsize(c)[0]-device.size[0]
        else:
            vibe[1]=font.getsize(c[d:])[0]-device.size[0]
        v=loop(vibe_range(device.size[0], font.getsize(c[:d] if isTwoRows else c)[0], vibe[0]) if not isTwoRows and overflow else int(above(device.size[0]-font.getsize(c)[0], 0)/2)), loop(vibe_range(device.size[0], font.getsize(c[d:])[0], vibe[1]))
    else:
        if isTwoRows:
            if len(c)>d*2:
                c=c[len(c)-d*(2 if isTwoRows else 1):]
        elif font.getsize(c)[0]>device.size[0]:
            v=loop(device.size[0]-font.getsize(c)[0]), loop(0)
    if not quiet:
        print("\r|"+c[:d]+"|", "|"+c[d:][:d]+"|" if isTwoRows and c[d:] else "", flush=True, end="")
    while True:
        with canvas(device) as draw:
            draw.text((v[0].__next__(), -fontPadding+(0 if isTwoRows else int((device.size[1]-font.size+1)/2))), c[:d] if isTwoRows else c, fill=fill, font=font)
            if isTwoRows and c[d:]:
                draw.text((v[1].__next__(), 4-fontPadding), c[d:], fill=fill, font=font)
        count+=1
        if (timeout and count*1/speed>timeout) or (v[0].isSingle and v[1].isSingle):
            break
        time.sleep(1/speed)


import sys, tty, termios
 
def readchar():
	fd = sys.stdin.fileno()
	old_settings = termios.tcgetattr(fd)
	try:
		tty.setraw(sys.stdin.fileno())
		ch = sys.stdin.read(1)
	finally:
		termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
	return ch
 
def readkey(getchar_fn=None):
	getchar = getchar_fn or readchar
	c1 = getchar()
	if ord(c1) != 0x1b:
		return c1
	c2 = getchar()
	if ord(c2) != 0x5b:
		return c1
	c3 = getchar()
	return chr(0x10 + ord(c3) - 65)

def live(device=device):
    s=''
    onlySmall=True
    while True:
        key=readkey()
        if key==chr(3):# c-c
            break
        elif key==chr(127):# backspace
            key=chr(8)
            s=s[:-1]
        else:
            s+=key
        if (ord(key)>127):
            onlySmall=False
        print('\r'+s, flush=True, end="")
        show(s, overflow=False, quiet=True, font=SMALL_FONT if onlySmall else CN_FONT)
    if device:
        device.clear()


def emoji(emo="normal", font=SMALL_FONT):
    show("^_^", overflow=False, font=font)

def sun(bright=None):
    if bright is None:
        h=time.localtime(time.time()).tm_hour+(8-time.timezone/3600)
        if h>23:
            h-=24
        bright=8 if h in range(18, 24) or h in range(0, 10) else 128
    device.contrast(bright)


import sys
from http.server import HTTPServer, BaseHTTPRequestHandler
import json
from urllib import parse, request
print("Created device")
info=dict({'pop':0, 'que_size':0, 'status_code':0, 'status':'', 'room_id':0, 'super_chat':[]})
class Resquest(BaseHTTPRequestHandler):
    def do_GET(self, data=None, method=None):
        if (parse.urlparse(self.path).path in ['/favicon.ico']):
            self.send_response(404)
            self.end_headers()
            return
        self.send_response(200)
        self.send_header('Content-type', 'text/html; charset=utf-8')
        self.end_headers()
        cmd_res=controlRoom(self.path, data, method)
        res=cmd_res[1]+('<br>' if cmd_res[1] and cmd_res[0] else '')+(readFromLive() if cmd_res[0] else '')
        self.wfile.write(res.encode('utf-8'))

    def do_POST(self):
        data=self.rfile.read(int(self.headers['content-length']))
        self.do_GET(data, method="POST")

    def do_PUT(self):
        data=self.rfile.read(int(self.headers['content-length']))



def runall(serial, device):
    # start demo
    msg = "MAX7219 LED Matrix Demo"
    print(msg)
    show_message(device, msg, fill="white", font=proportional(CP437_FONT))
    time.sleep(1)

    msg = "Fast scrolling: Lorem ipsum dolor sit amet, consectetur adipiscing\
    elit, sed do eiusmod tempor incididunt ut labore et dolore magna aliqua. Ut\
    enim ad minim veniam, quis nostrud exercitation ullamco laboris nisi ut\
    aliquip ex ea commodo consequat. Duis aute irure dolor in reprehenderit in\
    voluptate velit esse cillum dolore eu fugiat nulla pariatur. Excepteur sint\
    occaecat cupidatat non proident, sunt in culpa qui officia deserunt mollit\
    anim id est laborum."
    msg = re.sub(" +", " ", msg)
    print(msg)
    show_message(device, msg, fill="white", font=proportional(LCD_FONT), scroll_delay=0)

    msg = "Slow scrolling: The quick brown fox jumps over the lazy dog"
    print(msg)
    show_message(device, msg, fill="white", font=proportional(LCD_FONT), scroll_delay=0.1)

    print("Vertical scrolling")
    words = [
        "Victor", "Echo", "Romeo", "Tango", "India", "Charlie", "Alpha",
        "Lima", " ", "Sierra", "Charlie", "Romeo", "Oscar", "Lima", "Lima",
        "India", "November", "Golf", " "
    ]

    virtual = viewport(width=device.width, height=len(words) * 8)
    with canvas(virtual) as draw:
        for i, word in enumerate(words):
            text(draw, (0, i * 8), word, fill="white", font=proportional(CP437_FONT))

    for i in range(virtual.height - device.height):
        virtual.set_position((0, i))
        time.sleep(0.05)

    msg = "Brightness"
    print(msg)
    show_message(device, msg, fill="white")

    time.sleep(1)
    with canvas(device) as draw:
        text(draw, (0, 0), "A", fill="white")

    time.sleep(1)
    for _ in range(5):
        for intensity in range(16):
            device.contrast(intensity * 16)
            time.sleep(0.1)

    device.contrast(0x80)
    time.sleep(1)

    msg = "Alternative font!"
    print(msg)
    show_message(device, msg, fill="white", font=SINCLAIR_FONT)

    time.sleep(1)
    msg = "Proportional font - characters are squeezed together!"
    print(msg)
    show_message(device, msg, fill="white", font=proportional(SINCLAIR_FONT))

    # http://www.squaregear.net/fonts/tiny.shtml
    time.sleep(1)
    msg = "Tiny is, I believe, the smallest possible font \
    (in pixel size). It stands at a lofty four pixels \
    tall (five if you count descenders), yet it still \
    contains all the printable ASCII characters."
    msg = re.sub(" +", " ", msg)
    print(msg)
    show_message(device, msg, fill="white", font=proportional(TINY_FONT))

    time.sleep(1)
    msg = "CP437 Characters"
    print(msg)
    show_message(device, msg)

    time.sleep(1)
    for x in range(256):
        with canvas(device) as draw:
            text(draw, (0, 0), chr(x), fill="white")
            time.sleep(0.1)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='matrix_demo arguments',
        formatter_class=argparse.ArgumentDefaultsHelpFormatter)

    parser.add_argument('--cascaded', '-n', type=int, default=1, help='Number of cascaded MAX7219 LED matrices')
    parser.add_argument('--block-orientation', type=int, default=0, choices=[0, 90, -90], help='Corrects block orientation when wired vertically')
    parser.add_argument('--rotate', type=int, default=0, choices=[0, 1, 2, 3], help='Rotate display 0=0°, 1=90°, 2=180°, 3=270°')
    parser.add_argument('--reverse-order', type=bool, default=False, help='Set to true if blocks are in reverse order')

    args = parser.parse_args()

    #demo(args.cascaded, args.block_orientation, args.rotate, args.reverse_order)

    sun()
    show("我@试我@试我@试我@试", font=CN_FONT)

    show("T}{e q[_]ick br0\^/|\| f0x j|_|mps ()ver +|-|e lqzy dog$.", True)
    show("The quick brown fox jumps over the lazy dog.")
    show("我@试", font=CN_FONT)
    device.clear()