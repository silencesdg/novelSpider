# novelSpider
a novel spider that use muti threads and mongodb for 2.7 version

### 生产消费、多线程的使用

> 由于python GIL的存在，对于计算密集型的任务多线程处理没有任何优势，反而会因为同步、切换线程等造成消耗，所以解析response只能单的线程处理，网络请求和磁盘读写可以多线程处理

* 20个线程请求数据
* 1个线程解析response
* 3个线程写入MongoDB
