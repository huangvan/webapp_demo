# -*- coding: utf-8 -*-
"""
Created on Tue Aug  7 13:53:47 2018
url handlers 
@author: Van Huang
"""

 
import re, time, json, logging, hashlib, base64, asyncio

import markdown2
from coroweb import get, post
from aiohttp import web

from config import configs
from apis import Page, APIValueError, APIResourceNotFoundError, APIError, APIPermissionError
from models import User, Comment, Blog, next_id


#以下为数据处理逻辑

COOKIE_NAME = 'demosession'
_COOKIE_KEY = configs.session.secret


def get_page_index(page_str):
    p = 1
    try:
        p = int(page_str)
    except ValueError as e:
        pass
    if p < 1:
        p = 1
    return p

def user2cookie(user, max_age):
    '''
    Generate cookie str by user.
    '''
    # build cookie string by: id-expires-sha1
    expires = str(int(time.time() + max_age))
    s = '%s-%s-%s-%s' % (user.id, user.passwd, expires, _COOKIE_KEY)
    L = [user.id, expires, hashlib.sha1(s.encode('utf-8')).hexdigest()]
    return '-'.join(L)

def text2html(text):
    lines = map(lambda s: '<p>%s</p>' % s.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;'), filter(lambda s: s.strip() != '', text.split('\n')))
    return ''.join(lines)


async def cookie2user(cookie_str):
    '''
    Parse cookie and load user if cookie is valid.
    '''
    if not cookie_str:
        return None
    try:
        L = cookie_str.split('-')
        if len(L) != 3:
            return None
        uid, expires, sha1 = L
        if int(expires) < time.time():
            return None
        user = await User.find(uid)
        if user is None:
            return None
        s = '%s-%s-%s-%s' % (uid, user.passwd, expires, _COOKIE_KEY)
        if sha1 != hashlib.sha1(s.encode('utf-8')).hexdigest():
            logging.info('invalid sha1')
            return None
        user.passwd = '******'
        return user
    except Exception as e:
        logging.exception(e)
        return None

def check_admin(request):
    if request.__user__ is None or not request.__user__.admin:
        raise APIPermissionError()



#以下为根据URL进行页面处理逻辑

#浏览首页：GET /
@get('/')
async def index(*, page='1'):
    page_index = get_page_index(page)
    num = await Blog.findNumber('count(id)')
   
    page = Page(num)
    if num == 0:
        blogs = []
    else:
        blogs = await Blog.findAll(orderBy='created_at desc', limit=(page.offset, page.limit))

    return {
        '__template__': 'blogs.html',
        'page': page,
        'blogs': blogs,
        'page_index': page_index
    }

#浏览首页：GET /home
@get('/home')
async def home(*, page='1'):
    page_index = get_page_index(page)
    num = await Blog.findNumber('count(id)')
   
    page = Page(num)
    if num == 0:
        blogs = []
    else:
        blogs = await Blog.findAll(orderBy='created_at desc', limit=(page.offset, page.limit))
    return {
        '__template__': 'blogs.html',
        'page': page,
        'blogs': blogs,
        'page_index': page_index
    }


#注册页：GET /register  
@get('/register')
def register():
    return {
        '__template__': 'register.html'
    }

#登录页：GET /signin
@get('/signin')
def signin():
    return {
        '__template__': 'signin.html'
    }

#注销页：GET /signout
@get('/signout')
def signout(request):
    referer = request.headers.get('Referer')
    r = web.HTTPFound(referer or '/')
    r.set_cookie(COOKIE_NAME, '-deleted-', max_age=0, httponly=True)
    logging.info('user signed out.')
    return r

#获取blog详情页：GET /blog/:blog_id
@get('/blog/{id}')
async def get_blog(id):
    blog = await Blog.find(id)
    comments = await Comment.findAll('blog_id=?', [id], orderBy='created_at desc')
    for c in comments:
        c.html_content = text2html(c.content)
    blog.html_content = markdown2.markdown(blog.content)
    return {
        '__template__': 'blog.html',
        'blog': blog,
        'comments': comments
    }

#创建blog页：GET /manage/blogs/create
@get('/manage/blogs/create')
def manage_create_blog():
    return {
        '__template__': 'manage_blog_edit.html',
        'id': '',
        'action': '/api/blogs'
    }
    
#展示blog列表页：GET /manage/blogs
@get('/manage/blogs')
def manage_blogs(*, page='1'):
    return {
        '__template__': 'manage_blogs.html',
        'page_index': get_page_index(page)
    }

#修改blog页：GET /manage/blogs/edit
@get('/manage/blogs/edit')
def manage_edit_blog(*, id):
    return {
        '__template__': 'manage_blog_edit.html',
        'id': id,
        'action': '/api/blogs/%s' % id
    }

    
#评论列表页：GET /manage/comments
@get('/manage/comments')
def manage_comments(*, page='1'):
    return {
        '__template__': 'manage_comments.html',
        'page_index': get_page_index(page)
    }

#跳转评论列表页：redirect:/manage/comments
@get('/manage/')
def manage():
    return 'redirect:/manage/comments'

#获取户列表页：GET /manage/users
@get('/manage/users')
def manage_users(*, page='1'):
    return {
        '__template__': 'manage_users.html',
        'page_index': get_page_index(page)
    }
    
#修改用户信息：GET /manage/users/edit
@get('/manage/users/edit')
def manage_edit_user(*, id):
    return {
        '__template__': 'manage_user_edit.html',
        'id': id,
        'action': '/api/users/%s' % id
    }


#获取user详情页：GET /user/user_id
@get('/user/{id}')
def get_user(id):
    return {
        '__template__': 'user.html',
        'id': id
    }


#以下为API处理逻辑 
    
#创建新用户：POST /api/users
_RE_EMAIL = re.compile(r'^[a-z0-9\.\-\_]+\@[a-z0-9\-\_]+(\.[a-z0-9\-\_]+){1,4}$')
_RE_SHA1 = re.compile(r'^[0-9a-f]{40}$')
@post('/api/users')
async def api_register_user(*, email, name, passwd):
    if not name or not name.strip():
        raise APIValueError('name')
    if not email or not _RE_EMAIL.match(email):
        raise APIValueError('email')
    if not passwd or not _RE_SHA1.match(passwd):
        raise APIValueError('passwd')
    users = await User.findAll('email=?', [email])
    if len(users) > 0:
        raise APIError('register:failed', 'email', 'Email is already in use.')
    uid = next_id()
    sha1_passwd = '%s:%s' % (uid, passwd)
    user = User(id=uid, name=name.strip(), email=email, passwd=hashlib.sha1(sha1_passwd.encode('utf-8')).hexdigest(), image='http://www.gravatar.com/avatar/%s?d=mm&s=120' % hashlib.md5(email.encode('utf-8')).hexdigest())
    await user.save()
    # make session cookie:
    r = web.Response()
    r.set_cookie(COOKIE_NAME, user2cookie(user, 86400), max_age=86400, httponly=True)
    user.passwd = '******'
    r.content_type = 'application/json'
    r.body = json.dumps(user, ensure_ascii=False).encode('utf-8')
    return r

#获取用户：GET /api/users
@get('/api/users')
async def api_get_users(*, page='1'):
    page_index = get_page_index(page)
    num = await User.findNumber('count(id)')
    p = Page(num, page_index)
    if num == 0:
        return dict(page=p, users=())
    users = await User.findAll(orderBy='created_at desc', limit=(p.offset, p.limit))
    for u in users:
        u.passwd = '******'
    return dict(page=p, users=users)

#删除用户：POST /api/blogs/:blog_id/delete
@post('/api/users/{id}/delete')
async def api_delete_user(request, *, id):
    check_admin(request)
    user = await User.find(id)
    await user.remove()
    return dict(id=id)

#获取用户信息：GET /api/user_id
@get('/api/users/{id}')
async def api_get_user(*, id):
    user = await User.find(id)
    return user

#修改用户信息：POST /api/users/user_id
@post('/api/users/{id}')
async def api_update_user(id, request, *, name, email, passwd, admin, oldpasswd):
    check_admin(request)
    user = await User.find(id)
    if not name or not name.strip():
        raise APIValueError('name', 'name cannot be empty.')
    if not email or not email.strip():
        raise APIValueError('email', 'email cannot be empty.')
    if not passwd or not passwd.strip():
        raise APIValueError('passwd', 'passwd cannot be empty.')
    user.name = name.strip()
    user.email = email.strip()
    if oldpasswd:
        user.passwd=passwd
    else:
        sha1_passwd = '%s:%s' % (user.id, passwd)
        user.passwd = hashlib.sha1(sha1_passwd.encode('utf-8')).hexdigest()
    user.admin = int(admin)
    await user.update()
    return user

#构造cookie，验证用户登录
@post('/api/authenticate')
async def authenticate(*, email, passwd):
    if not email:
        raise APIValueError('email', 'Invalid email.')
    if not passwd:
        raise APIValueError('passwd', 'Invalid password.')
    users = await User.findAll('email=?', [email])
    if len(users) == 0:
        raise APIValueError('email', 'Invalid email or password.')
    user = users[0]
    # check passwd:
    sha1 = hashlib.sha1()
    sha1.update(user.id.encode('utf-8'))
    sha1.update(b':')
    sha1.update(passwd.encode('utf-8'))
    if user.passwd != sha1.hexdigest():
        logging.info(user.passwd)
        logging.info(sha1.hexdigest())
        raise APIValueError('passwd', 'Invalid email or password.')
    # authenticate ok, set cookie:
    r = web.Response()
    r.set_cookie(COOKIE_NAME, user2cookie(user, 86400), max_age=86400, httponly=True)
    user.passwd = '******'
    r.content_type = 'application/json'
    r.body = json.dumps(user, ensure_ascii=False).encode('utf-8')
    return r

#获取首页blog：GET /api/home
@get('/api/home')
async def api_home(*, page='1'):
    page_index = get_page_index(page)
    num = await Blog.findNumber('count(id)')
    page = Page(num, page_index)
    if num == 0:
        return dict(page=page, blogs=())
    blogs = await Blog.findAll(orderBy='created_at desc', limit=(page.offset, page.limit))
    return dict(page=page, blogs=blogs)


#获取blog：GET /api/blogs
@get('/api/blogs')
async def api_blogs(*, page='1'):
    page_index = get_page_index(page)
    num = await Blog.findNumber('count(id)')
    p = Page(num, page_index)
    if num == 0:
        return dict(page=p, blogs=())
    blogs = await Blog.findAll(orderBy='created_at desc', limit=(p.offset, p.limit))
    return dict(page=p, blogs=blogs)

#创建blog：POST /api/blogs
@post('/api/blogs')
async def api_create_blog(request, *, name, summary, content):
    check_admin(request)
    if not name or not name.strip():
        raise APIValueError('name', 'name cannot be empty.')
    if not summary or not summary.strip():
        raise APIValueError('summary', 'summary cannot be empty.')
    if not content or not content.strip():
        raise APIValueError('content', 'content cannot be empty.')
    blog = Blog(user_id=request.__user__.id, user_name=request.__user__.name, user_image=request.__user__.image, name=name.strip(), summary=summary.strip(), content=content.strip())
    await blog.save()
    return blog

#获取用户blog：GET /api/blog_id
@get('/api/blogs/{id}')
async def api_get_blog(*, id):
    blog = await Blog.find(id)
    return blog

#修改用户blog：POST /api/blogs/:blog_id
@post('/api/blogs/{id}')
async def api_update_blog(id, request, *, name, summary, content):
    check_admin(request)
    blog = await Blog.find(id)
    if not name or not name.strip():
        raise APIValueError('name', 'name cannot be empty.')
    if not summary or not summary.strip():
        raise APIValueError('summary', 'summary cannot be empty.')
    if not content or not content.strip():
        raise APIValueError('content', 'content cannot be empty.')
    blog.name = name.strip()
    blog.summary = summary.strip()
    blog.content = content.strip()
    await blog.update()
    return blog

#删除blog：POST /api/blogs/:blog_id/delete
@post('/api/blogs/{id}/delete')
async def api_delete_blog(request, *, id):
    check_admin(request)
    blog = await Blog.find(id)
    await blog.remove()
    return dict(id=id)

#获取评论：GET /api/comments
@get('/api/comments')
async def api_comments(*, page='1'):
    page_index = get_page_index(page)
    num = await Comment.findNumber('count(id)')
    p = Page(num, page_index)
    if num == 0:
        return dict(page=p, comments=())
    comments = await Comment.findAll(orderBy='created_at desc', limit=(p.offset, p.limit))
    return dict(page=p, comments=comments)

#创建评论：POST /api/blogs/:blog_id/comments
@post('/api/blogs/{id}/comments')
async def api_create_comment(id, request, *, content):
    user = request.__user__
    if user is None:
        raise APIPermissionError('Please signin first.')
    if not content or not content.strip():
        raise APIValueError('content')
    blog = await Blog.find(id)
    if blog is None:
        raise APIResourceNotFoundError('Blog')
    comment = Comment(blog_id=blog.id, user_id=user.id, user_name=user.name, user_image=user.image, content=content.strip())
    await comment.save()
    return comment

#删除评论：POST /api/comments/:comment_id/delete
@post('/api/comments/{id}/delete')
async def api_delete_comments(id, request):
    check_admin(request)
    c = await Comment.find(id)
    if c is None:
        raise APIResourceNotFoundError('Comment')
    await c.remove()
    return dict(id=id)

