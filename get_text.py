import os
import re
import time
import json
import roman
import urllib.request
import pymongo
from pymongo import MongoClient
from bs4 import BeautifulSoup

with open('config.json') as f:
    config = json.load(f)

url = config['url'] #'http://shakespeare.mit.edu/1henryiv/full.html'
cache = 'text.html'
maxage = 100000000 # just in case shakespeare changes anything

if not os.path.isfile(cache) or os.path.getmtime(cache) - time.time() > maxage:
    print('making request...')
    with urllib.request.urlopen(url) as req:
        page = req.read().decode()
        with open(cache, 'w') as f:
            f.write(page)
else:
    print('using cached...')
    with open(cache, 'r') as f:
        page = f.read()
            
            
soup = BeautifulSoup(page, 'html.parser')

r = re.compile('(?P<type>SCENE|ACT)\s(?P<num>[IVX]+)\.?\s?(?P<desc>[\s\S]+)?')

last = soup.find('h3')
act, scene = None, None

speakers = set({})
lineblocks = []

last = last.find_next('h3')
print('looking for lines...')
while last:
    # find act / scene headers
    m = r.match(last.text)
    num = m.group('num')
    n = roman.fromRoman(num)

    if m.group('type') == 'ACT':
        act = n # act number

    elif m.group('type') == 'SCENE':
        # create new scene
        scene = n               # scene number
        desc = m.group('desc')  # description

        # for finding by NAME=1.2.3
        text = '.'.join(['(?P<act>{})'.format(act), '(?P<scene>{})'.format(scene)]) + '\.(?P<line>\d+)'
        numre = re.compile(text)
        # for finding by NAME=speech1
        spere = re.compile('speech\d+')

        # find next speaker
        speaker_elem = last.find_next_sibling('p').find('a', {'name':spere})
        while speaker_elem:
            speaker = speaker_elem.b.text.upper() # speaker name

            if speaker == 'Scene III': # wierd bug in html
                scene = 3
                text = '.'.join(['(?P<act>{})'.format(act), '(?P<scene>{})'.format(scene)]) + '\.(?P<line>\d+)'
                numre = re.compile(text)

            else:
                speakers.add(speaker)

                block = speaker_elem.find_next_sibling('blockquote')
                if block:
                    lines_raw = block.find_all('a', {'name':numre})
                    lines = [{'_id':line['name'], 'text':line.text.strip()} for line in lines_raw]
                    if len(lines) > 0:
                        lineblocks.append({'speaker': speaker, 'lines' : lines, 'scene': scene, 'act': act, 'start':lines[0]['_id']})

            speaker_elem = speaker_elem.find_next_sibling('a', {'name':spere})

    last = last.find_next('h3')

client = MongoClient(config['dburl'])#'mongodb://samzagrobelny.com:27017/shakespeare')
db = client.shakespeare

speakertoid = {};

speakerscol = db.speakers
linescol = db.lines
linescol.create_index([("start", pymongo.ASCENDING)])

for speaker in speakers:
    doc = {'name': speaker}
    speakerscol.update_one(doc, {'$set':doc}, upsert=True)

for i, lineblock in enumerate(lineblocks):
    print('{} / {}'.format(i, len(lineblocks)))
    linescol.update_one({'start' : lineblock['start']}, {'$set' : lineblock}, upsert=True)
