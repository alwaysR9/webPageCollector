高效的python爬虫组件 —— webPageCollector<br>
========================================

适用场景<br>
--------
当有很多链接需要爬取时，爬取链接的任务可以交给`webPageCollector`，它可以高效的完成爬取任务，并保证爬到的数据包含完整的网页内容，利用它可以取代频繁调用urlopen的情况。`webPageCollector`<b>特别适合爬取单一大型网站的页面（例如爬取美团上所有的店家信息），因为程序中对此情况的时间效率进行了优化</b><br>

与urlopen函数时间效率对比<br>
-------------------------
* 实验数据：3154个美团店家主页地址<br>
* 实验环境：网速4Mb/s<br>
* 实验一：`webPageCollector`<br>
	* 成功爬取3135个店家主页，漏爬率%0.6<br>
	* 耗时868秒<br>
* 实验二：`单线程调用urlopen函数`<br>
	* 成功爬取3140个店家主页，漏爬率0.44%<br>
	* 耗时4614秒<br>
* 实验结果：<br>
	* 时间效率上，使用`webPageCollector`是使用`单线程调用urlopen函数`的 5.31倍<br>
	* 漏爬率，使用`webPageCollector`比使用`单线程调用urlopen函数`高 0.16%<br>

运行环境<br>
--------
在 Linux 3.13 内核上可正常运行<br>
Linux 2.6 或以上版本的内核应该也可以运行<br>

运行示例<br>
--------
```python
from webPageCollector import WebPageCollector

# 加载800个美团店家的URL地址
urls = open("urls.txt", "rb").read().strip().split()

# 创建爬虫
crawler = WebPageCollector()
# 设置URL
crawler.set_urls(urls)
# 开始爬取
crawler.start()

# 接收并输出爬取到的数据
while True:
	item = crawler.pop()
	# item为None表是爬取结束
	if item == None:
		break
	
	(url, data) = item
	print url
	print data
```
<b>注意！：</b><br>
<b>webPageCollector只负责请求并完整接收服务器数据</b><br>
<b>服务器返回数据包含HTTP协议头部和内容，返回的内容可能是UTF-8编码，可也能是经过gzip压缩的内容，需要用户自己查看数据类型并解析</b><br>

webPageCollector支持<br>
--------------------
`HTTP 1.1` 协议`GET`请求<br>
`HTTP 301`和`HTTP 302`重定向<br>

webPageCollector不支持<br>
----------------------
`Https`协议<br>
被`墙`的网页<br>

联系方式<br>
--------
zhufangze123@gmail.com
