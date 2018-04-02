# -*- coding: UTF-8 -*-

import requests
from bs4 import BeautifulSoup
import time
import os
import sys
from Queue import Queue
import threading
from pymongo import MongoClient


targetHost="https://www.xxbiquge.com"
targetId = "74_74821"


def getChapterTextFromHtml(novel_html):

	novel_soup = BeautifulSoup(novel_html, 'html.parser', from_encoding='utf-8')

	return getChapterTextFromSoup(novel_soup)

def getChapterTextFromSoup(novel_soup):
	chapter_text_label = novel_soup.find("div", id="content")
	if not chapter_text_label :
		return None

	chapter_text_lines = []
	for text_label in chapter_text_label.contents:
		if text_label.string and (len(text_label.string) > 0) and (not text_label.string.isspace()):
			chapter_text_lines.append(text_label.string)

	chapter_text = "\n\n".join(chapter_text_lines)
	return chapter_text
'''
	section_label = novel_soup.find_all('div', class_="text")[0]

	for a_label in section_label.contents:
		if a_label.string == u"\u4e0b\u4e00\u8282":
			nextUrl = a_label['href']
			nexthtml = requests.get(nextUrl).content
			nextText = getChapterTextFromHtml(nexthtml)
			if nextText :
				chapter_text = chapter_text + nextText
			break

	return chapter_text
'''

def getChapterAllFromHtml(novel_html):

	novel_soup = BeautifulSoup(novel_html, 'html.parser', from_encoding='utf-8')

	chapter_title_label = novel_soup.find('div', class_="bookname").h1
	chapter_title = chapter_title_label.string

	chapter_text = getChapterTextFromSoup(novel_soup)
	if chapter_title and chapter_text:
		return chapter_title + "\n\n" + chapter_text

	return ""


def getURLs():
	targetURL = targetHost +"/" + targetId
	html = requests.get(targetURL).content
	soup = BeautifulSoup(html, 'html.parser', from_encoding='utf-8')
	dds = soup('dd')
	urls = []

	for dd in dds:

		if dd.a:
			url = dd.a['href']
			urls.append(targetHost + url)


	print len(urls)
	return urls


condition = threading.Condition()
mongo_condition = threading.Condition()

count = 0
thread_count = 20

# page get
class Thread_getWebPage(threading.Thread):

	def __init__(self, threadID, q, nextQueue):
		threading.Thread.__init__(self)
		self.threadID = threadID
		self.q = q
		self.nextQueue = nextQueue

	def run(self):
		print "starting",self.threadID
		self.getPage()

	def getPage(self):
		while True:

			if self.q.empty():
				condition.acquire()
				global count
				count += 1
				condition.release()
				print "page get complete for",self.threadID
				break
			else:

				index,url = self.q.get()
				print "threadID:", self.threadID," fetching:",index
				html = requests.get(url).content
				condition.acquire()

				self.nextQueue.put((index,html))
				condition.notify()
				self.q.task_done()
				condition.release()

analysis_complete = False

#analysis
class Thread_analysis(threading.Thread):

	def __init__(self, threadID, q, nextQueue):
		threading.Thread.__init__(self)
		self.threadID = threadID
		self.q = q
		self.nextQueue = nextQueue

	def run(self):
		while True:
			condition.acquire()
			if (not self.q) or self.q.empty():

				print " analysis: waiting",count,"/",thread_count
				condition.wait()
				condition.release()
				if count == thread_count:
					global  analysis_complete
					analysis_complete = True
					mongo_condition.acquire()
					mongo_condition.notifyAll()
					mongo_condition.release()
					print " analysis: exit"
					break

			else:
				index, html = self.q.get()
				print " analysis:", index
				chapter_text = getChapterAllFromHtml(html)

				mongo_condition.acquire()
				self.nextQueue.put((index, chapter_text))
				mongo_condition.notify()
				mongo_condition.release()
				self.q.task_done()
				condition.release()



class Thread_mongo(threading.Thread):

	def __init__(self, threadID, q, collection):
		threading.Thread.__init__(self)
		self.threadID = threadID
		self.q = q
		self.collection = collection

	def run(self):
		while True:
			if self.q.empty():
				if analysis_complete:
					print "insert complete :", self.threadID
					break
				else:
					print "insert waiting :", self.threadID
					mongo_condition.acquire()
					mongo_condition.wait()
					mongo_condition.release()

			else:

				index, txt = self.q.get()

				print "threadId :",self.threadID,"inserting :",index
				NovelMongo.insertChapter((index, txt),self.collection)
				self.q.task_done()

#dao - mongo

class NovelMongo(object):

	@staticmethod
	def getCollection(dbname, collectionName):
		connect = MongoClient("127.0.0.1", 27017)
		db = connect[dbname]
		if db[collectionName]:
			db.drop_collection(collectionName)
		return db[collectionName]

	@staticmethod
	def insertChapter((index,chapter_all), collection):
		try:

			collection.insert({"chapter_index":index,"chapter":chapter_all})
		except Exception as e:
			print ('insert error')
			print(e)
		else:
			return



def main():

	urlQueue = Queue()
	urls = getURLs()
	print(urls)

	for index in range(len(urls)):
		urlQueue.put((index, urls[index]))

	dataQueue = Queue()

	writeQueue = Queue()

	collection = NovelMongo.getCollection("novel", targetId)

	mongo_thread_count = 3

	mongo_threads = []

	urlThreads = []
	for i in range(thread_count):
		thread = Thread_getWebPage(i,urlQueue, dataQueue)
		thread.setDaemon(True)
		thread.start()
		urlThreads.append(thread)

	analysisThread = Thread_analysis("a",dataQueue, writeQueue)
	analysisThread.setDaemon(True)
	analysisThread.start()

	for x in range(mongo_thread_count):
		mongo_thread = Thread_mongo(100+x,writeQueue,collection)
		mongo_thread.setDaemon(True)
		mongo_thread.start()
		mongo_threads.append(mongo_thread)

	print "start muti threads"

	for url_thread in urlThreads:
		url_thread.join()

	analysisThread.join()

	for mon_thread in mongo_threads:
		mon_thread.join()

	print "insert complete"

	write(collection)


def write(collection=NovelMongo.getCollection("novel",targetId)):
	print "starting writing"
	fo = open(targetId+'.txt', "a")
	for dic in collection.find().sort("chapter_index"):
		fo.write("\n\n" + dic["chapter"].encode('utf-8'))

	fo.close()


if __name__ == '__main__':
	time1 = time.time()
	main()
	# write()
	time2 = time.time()
	print "use time:",time2 - time1
