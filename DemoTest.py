# -*- coding: utf-8 -*-
"""
Created on Tue Aug  7 10:20:53 2018

@author: Van Huang
"""
import sys,time
import asyncio
sys.path.append(r'C:\webapp_demo\www')
from models import User, Blog, Comment
from orm import create_pool


async def test(loop):
    await create_pool(loop, user='root', password='123456', db='webdemo')
    u=User(name='Test', email='test@example.com', passwd='1234567890', image='about:blank')
    await u.save()
#print("Time1:",time.time())
loop=asyncio.get_event_loop()
#print("Time2:",time.time())
loop.run_until_complete(test(loop))
#print("Time3:",time.time())
loop.run_forever()
loop.close()
#print("Time4:",time.time())
