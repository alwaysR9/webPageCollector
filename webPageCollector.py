import os
import re
import errno
import time
		
import socket
import select
import threading

from Queue import Queue

class DataBuff:

	def __init__(self):
		
		self.data = ""
		self.page_type = None # 'Transfer-Encoding' or 'Content-Length'
		self.content_length = None # valid only when page_type == Content-Length is True

class Url:

	def __init__(self, ip, host, uri):
		
		self.ip   = ip
		self.host = host
		self.uri  = uri
		self.url  = host + uri
	
class WebPageCollector:

	'''
	@Param batch_size:  The number of URL will be cocurrent collected at once
	@Param wait_time_for_event: Wait time for one epoll event
	@Param queue_size: The size of queue to hold collected data
	@Param is_debug: Output debug info if this param is set to True
	'''
	def __init__(self, batch_size=200, wait_time_for_event=5.0, queue_size=1000, is_debug=False):
		
		self.batch_size = batch_size
		self.wait_time_for_event = wait_time_for_event
		self.queue_size = queue_size
		self.queue = Queue(self.queue_size)

		self.urls = None
		self.user_agent	= None
		self.cookie		= None

		self.is_debug = is_debug

	''' Interface function '''

	def set_urls(self, urls):

		self.urls = urls

	def start(self):

		# start crawling thread
		try:
			t = threading.Thread(target=WebPageCollector.__collect, args=(self, self.urls))
			t.start()
		except Exception as e:
			print "[Error] %s" % str(e)

	def pop(self):

		return self.queue.get(block=True)

	def set_user_agant(self, user_agent):
		''' optional '''

		self.user_agent = user_agent

	def set_cookie(self, cookie):
		''' optional '''

		self.cookie = cookie


	''' Private function '''

	'''
	@Func: Crawling web page, put them into the queue
	@Instruction: This function should conceal HTTP_301 and HTTP_302 to user
	@Return: Void
	'''
	def __collect(self, urls):

		b_time = time.time()

		while urls != None and len(urls) > 0:

			# extract host and uri from urls
			hosts, uris = self.__split_host_uri(urls)

			if self.is_debug:
				for i in xrange(len(hosts)):
					print hosts[i], uris[i]

			# convert host to ip
			ips = self.__get_ip(hosts)
			#ips = [socket.gethostbyname(host) for host in hosts]

			if self.is_debug:
				for ip in ips:
					print ip

			# cut ips into pieces with the size of batch_size,
			# crawling all these pieces.
			# deal redirection with recursive.
			urls_redirect = []

			piece = 0
			while len(ips) - (piece+1)*self.batch_size >= 0:
				ip   = ips[piece*self.batch_size : (piece+1)*self.batch_size]
				host = hosts[piece*self.batch_size : (piece+1)*self.batch_size]
				uri  = uris[piece*self.batch_size : (piece+1)*self.batch_size]
				urls_redirect.extend( self.__collect_piece(ip, host, uri) )
				piece += 1
			ip   = ips[piece*self.batch_size : ]
			host = hosts[piece*self.batch_size : ]
			uri  = uris[piece*self.batch_size : ]
			urls_redirect.extend( self.__collect_piece(ip, host, uri) )

			# crawling redirection urls
			urls = urls_redirect

		# crawling finished
		self.queue.put(None, block=True)
			
		e_time = time.time()
		print "Total Time Consuming: %f Seconds" % (e_time-b_time)

	'''
	@Func: Crawling web page accroding to their ip, 
			put them into the queue(If them is not HTTP_301 or HTTP_302)
	@Return: Urls of HTTP_301 and HTTP_302
	'''
	def __collect_piece(self, ip, host, uri):
		
		# create sockets
		fd_2_sock	= {}
		fd_2_url	= {}
		fd_2_data	= {}
	
		for i in xrange(len(ip)):
			sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
			sock.setblocking(0)
			fd_2_sock[sock.fileno()] = sock
			fd_2_url[sock.fileno()]  = Url(ip[i], host[i], uri[i])
		print "Create %d Sockets Finished!" % len(fd_2_sock.items())
	
		# create listener
		epoll = select.epoll()
	
		# non-blocking connect
		for (fd, sock) in fd_2_sock.items():
			try:
				sock.connect( (fd_2_url[fd].ip, 80) )
			except Exception, e:
				if e.args[0] == 115:
					epoll.register(fd, select.EPOLLOUT)
				else:
					print "[Connection Error] Url %s : %s" % (fd_2_url[fd].url, str(e))
		print "Non-Blocking Connection Finished"

		# listen connection result
		# save redirection urls when HTTP return code is 301 or 302
		urls_redirect = []

		b = time.time()
		while True:
			events = epoll.poll(self.wait_time_for_event)
			if len(events) == 0: break
			for fd, event in events:
				if event & select.EPOLLOUT:
					# connection event
					err = fd_2_sock[fd].getsockopt(socket.SOL_SOCKET, socket.SO_ERROR)
					if err == 0:
						req = self.__generate_request(fd_2_url[fd])
						n_send = fd_2_sock[fd].send(req)
						epoll.modify(fd, select.EPOLLIN)
					else:
						print "[Connection Error] Connect %s Fail, Errno : %d" % (fd_2_url[fd].url, err)
						fd_2_sock[fd].close()
				elif event & select.EPOLLIN:
					# data event
					if not fd_2_data.has_key(fd):
						fd_2_data[fd] = DataBuff()
					try:
						# first, we should read data to buffer
						# second, we should check whether finished data reading job,
						# 	if data reading job has finished, socket should be closed;
						#	and put data into the queue.
						if self.__read_to_buff(fd_2_sock[fd], fd_2_data[fd]) == True:
							if self.__has_finished_data_sending(fd_2_data[fd]):
								http_return_code = self.__get_http_return_code(fd_2_data[fd].data)
								print "HTTP " + http_return_code
								if http_return_code == "301" or http_return_code == "302":
									urls_redirect.append( self.__get_redirect_url(fd_2_data[fd].data) )
								else:
									self.queue.put( [fd_2_url[fd].url, fd_2_data[fd].data], block=True )
								del fd_2_data[fd]
							fd_2_sock[fd].close()
						else:
							if self.__has_finished_data_sending(fd_2_data[fd]):
								http_return_code = self.__get_http_return_code(fd_2_data[fd].data)
								print "HTTP " + http_return_code
								if http_return_code == "301" or http_return_code == "302":
									urls_redirect.append( self.__get_redirect_url(fd_2_data[fd].data) )
								else:
									self.queue.put( [fd_2_url[fd].url, fd_2_data[fd].data], block=True )
								del fd_2_data[fd]
								fd_2_sock[fd].close()
					except Exception as e:
						print str(e)
						fd_2_sock[fd].close()
		print "Time Consuming Of Crawling Data: %f seconds" % (time.time()-b)

		# return redirect urls of HTTP_301 and HTTP_302
		print "HTTP 301 Number: %d" % len(urls_redirect)
		return urls_redirect

	def __split_host_uri(self, urls):
		
		hosts = []
		uris  = []
		for url in urls:
			i = url.find("?")
			if i >= 0:
				tmp_str = url[i:]
				url = url.replace(tmp_str, "")
			url = url.replace("http://", "")
			pos = url.find("/")
			if pos >= 0:
				host = url[:pos]
				uri  = url[pos:]
			else:
				host = url
				uri  = "/"
			hosts.append(host)
			uris.append(uri)
		
		return hosts, uris

	def __get_ip(self, hosts):

		host_2_ip = {}
		for host in hosts:
			host_2_ip[host] = None

		for (host, _) in host_2_ip.items():
			ip = socket.gethostbyname(host)
			host_2_ip[host] = ip

		ips = []
		for host in hosts:
			ip = host_2_ip[host]
			ips.append(ip)

		return ips

	def __generate_request(self, url):

		req = "GET " + url.uri + " HTTP/1.1\r\n"
		if self.user_agent != None:
			req += "User-Agent:" + self.user_agent + "\r\n"
		if self.cookie != None:
			req += "Cookie:" + self.cookie + "\r\n"
		req += "Host:" + url.host + "\r\n"
		req += "\r\n"
		return req
	
	def __read_to_buff(self, sock, buff):
		'''
		return 	True if server send FIN 
		'''
	
		while True:
			try:
				data = sock.recv(2048)
				if len(data) == 0:
					return True
				buff.data += data
			except Exception as e:
				if e.args[0] == errno.EAGAIN or e.args[0] == errno.EWOULDBLOCK:
					break
				raise
		return False 
	
	def __has_finished_data_sending(self, buff):
		'''
		return  True if buff.data is a complete response data
		'''

		pattern_TE = re.compile(r"[Tt]ransfer-[Ee]ncoding")
		pattern_CL = re.compile(r"[Cc]ontent-[Ll]ength")

		if not buff.page_type:
			if re.search(pattern_TE, buff.data) != None:
				buff.page_type = "TE"
			elif re.search(pattern_CL, buff.data) != None:
				buff.page_type = "CL"
			else:
				return False
	
		if buff.page_type == "TE":
			if buff.data.find("\r\n0\r\n\r\n") >= 0:
				return True
			else:
				return False
		
		elif buff.page_type == "CL":
			if not buff.content_length:
				b = buff.data.find("Content-Length:")
				if b < 0:
					b = buff.data.find("content-length:")
					if b < 0:
						b = buff.data.find("Content-length:")
				#b = buff.data.find(pattern_CL)
				#print "b : " + str(b)
				b += len("Content-Length:")
				e = buff.data.find("\r\n", b)
				buff.content_length = int(buff.data[b:e].strip())
			b_content = buff.data.find("\r\n\r\n")+len("\r\n\r\n")
			if len(buff.data) - b_content == buff.content_length:
				return True
			else:
				return False
	
		else:
			raise ValueError("page_type error")

	def __get_http_return_code(self, data):
		
		i = data.find("HTTP/1.1 ")
		if i >= 0:
			b = i + len("HTTP/1.1 ")
			e = data.find(" ", b)
			code = data[b:e]
			return code
		else:
			return None

	def __get_redirect_url(self, data):

		try:
			b = data.index("location:") + len("location:")
		except:
			b = data.find("Location:") + len("Location:")
		e = data.find("\n", b)
		redirect_url = data[b:e].strip()
		return redirect_url


if __name__ == "__main__":

	#urls = []
	#urls.append("http://www.meituan.com/shop/318")
	#urls.append("http://www.cnblogs.com/li0803/archive/2008/11/03/1324746.html")
	#urls.append("http://baike.baidu.com/view/5255837.htm")
	#urls.append("localhost/haha.txt")

	urls = open("urls_large.txt", "rb").read().strip().split()

	web_page_collector = WebPageCollector(batch_size=200, wait_time_for_event=5.0, is_debug=True)

	web_page_collector.set_urls(urls)
	web_page_collector.start()

	os.system("rm -r ./data/")
	os.system("mkdir data")
	c = 0
	while True:

		item = web_page_collector.pop()
		if item == None:
			break

		c += 1
		with open("./data/"+str(c), "wb") as fo:
			fo.write(item[0]+"\n")
			fo.write(item[1])
		print c
