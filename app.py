# coding=utf-8
import os
import time, datetime
import functools
import base64
import cProfile, pstats, StringIO

import flask
from flask import Flask, request, render_template
from flask_sqlalchemy import SQLAlchemy
from flask_cors import CORS

if os.environ.get('DATABASE_URL') != None:
    DATABASE_URL = os.environ.get('DATABASE_URL')
else:
    DATABASE_URL = "postgresql+psycopg2://gaotian:password@localhost:5432/colorfight"
if os.environ.get('ADMIN_PASSWORD') != None:
    ADMIN_PASSWORD = os.environ.get('ADMIN_PASSWORD') 
else:
    ADMIN_PASSWORD = ''
if os.environ.get('PROFILE_INTERVAL') != None:
    pr_interval = int(os.environ.get('PROFILE_INTERVAL'))
else:
    pr_interval = 5

if os.environ.get('GAME_VERSION') != None:
    GAME_VERSION = os.environ.get('GAME_VERSION')
else:
    GAME_VERSION = 'mainline'

app = Flask(__name__, static_url_path='/static')
app.config['SQLALCHEMY_DATABASE_URI'] = DATABASE_URL
app.secret_key = base64.urlsafe_b64encode(os.urandom(24))
CORS(app)
db = SQLAlchemy(app)
if os.environ.get('PROFILE') == 'True':
    pr = cProfile.Profile()
else:
    pr = None
pr_lastPrint = 0
protocolVersion = 1

# ============================================================================
#                                 Decoreator
# ============================================================================ 
def require(*required_args, **kw_req_args):
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kw):
            data = request.get_json()
            if data == None:
                resp = flask.jsonify( msg="No json!")
                resp.status_code = 400
                return resp
            for arg in required_args:
                if arg not in data:
                    resp = flask.jsonify(code=400, msg="wrong args! need "+arg)
                    resp.status_code = 400
                    return resp
            if kw_req_args != None:
                if "login" in kw_req_args:
                    assert('token' in required_args)
                    username = data[kw_req_args["login"]]
                    token = data['token']
                    u = User(username = username, token = token)
                    if not u.valid:
                        resp = flask.jsonify(msg="This action requires login!")
                        resp.status_code = 401
                        return resp
                if "postValid" in kw_req_args:
                    p = Post()
                    if not p.Exist(data[kw_req_args["postValid"]]):
                        resp = flask.jsonify(msg="The reference post is not valid")
                        resp.status.code = 400
                        return resp
                if "protocol" in kw_req_args:
                    if "protocol" not in data:
                        return GetResp((400, {"msg":"Need protocol!"}))
                    if data['protocol'] < kw_req_args['protocol']:
                        return GetResp((400, {"msg":"Protocol version too low"}))
            return func(*args, **kw)
        return wrapper
    return decorator

class CellDb(db.Model):
    __tablename__ = 'cells'
    id            = db.Column(db.Integer, primary_key = True)
    x             = db.Column(db.Integer)
    y             = db.Column(db.Integer)
    owner         = db.Column(db.Integer, default = 0)
    occupy_time   = db.Column(db.Float, default = 0)
    is_taking     = db.Column(db.Boolean, default = False)
    attacker      = db.Column(db.Integer, default = 0)
    attack_time   = db.Column(db.Float, default = 0)
    finish_time   = db.Column(db.Float, default = 0)
    last_update   = db.Column(db.Float, default = 0)
    timestamp     = db.Column(db.TIMESTAMP, default = db.func.current_timestamp(), onupdate = db.func.current_timestamp())
    cell_type     = db.Column(db.String(15), default = "normal")
    
    def Init(self, owner, currTime):
        self.attack_time = currTime
        self.is_taking = True
        self.finish_time = currTime
        self.attacker = owner

    def GetTakeTimeEq(self, timeDiff):
        if timeDiff <= 0:
            return 200
        return 20*(2**(-timeDiff/20))+2

    def GetTakeTime(self, currTime):
        if self.is_taking == False:
            if self.owner != 0:
                takeTime  = self.GetTakeTimeEq(currTime - self.occupy_time)
            else:
                takeTime = 2
        else:
            takeTime = -1
        return takeTime

    def ToDict(self, currTime):
        return {'o':self.owner, 'a':self.attacker, 'c':int(self.is_taking), 'x': self.x, 'y':self.y, 'ot':self.occupy_time, 'at':self.attack_time, 't': self.GetTakeTime(currTime), 'f':self.finish_time, 'ct':self.cell_type}

    def Refresh(self, currTime):
        if self.is_taking == True and self.finish_time < currTime:
            if self.owner != 0:
                o = UserDb.query.get(self.owner)
                o.dirty = True
            a = UserDb.query.get(self.attacker)
            a.dirty = True
            self.is_taking = False
            self.owner     = self.attacker
            self.occupy_time = self.finish_time
            self.last_update = currTime

    def Attack(self, uid, currTime):
        if self.is_taking == True:
            return False, 2, "This cell is being taken."
        # Check whether it's adjacent to an occupied cell
        adjCells = 0
        if GAME_VERSION == "release":
            if self.owner != uid:
                for d in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
                    adjc = CellDb.query.filter_by(x = self.x + d[0], y = self.y + d[1]).first()
                    if adjc != None and adjc.owner == uid:
                        break
                else:
                    return False, 1, "Cell position invalid or it's not adjacent to your cell."
        elif GAME_VERSION == "mainline":
            for d in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
                adjc = CellDb.query.filter_by(x = self.x + d[0], y = self.y + d[1]).first()
                if adjc != None and adjc.owner == uid:
                    adjCells += 1
            if self.owner != uid and adjCells == 0:
                return False, 1, "Cell position invalid or it's not adjacent to your cell."



        user = UserDb.query.with_for_update().get(uid)
        if user.cd_time > currTime:
            db.session.commit()
            return False, 3, "You are in CD time!"
        self.attacker = uid
        self.attack_time = currTime
        self.finish_time = currTime + self.GetTakeTime(currTime) - max(0, (adjCells - 1))*0.5
        self.is_taking = True
        self.last_update = currTime
        user.cd_time = self.finish_time
        db.session.commit()
        return True, None, None

class InfoDb(db.Model):
    __tablename__ = 'info'
    id            = db.Column(db.Integer, primary_key = True)
    width         = db.Column(db.Integer, default = 0)
    height        = db.Column(db.Integer, default = 0)
    max_id        = db.Column(db.Integer, default = 0)         
    end_time      = db.Column(db.Float, default = 0)
    ai_only       = db.Column(db.Boolean, default = False)

class UserDb(db.Model):
    __tablename__ = 'users'
    id            = db.Column(db.Integer, primary_key = True)
    name          = db.Column(db.String(50))
    token         = db.Column(db.String(32), default = "")
    cd_time       = db.Column(db.Integer)
    cells         = db.Column(db.Integer)
    dirty         = db.Column(db.Boolean)

    def Dead(self):
        attackCells = CellDb.query.filter_by(attacker = self.id).with_for_update().all()
        for cell in attackCells:
            cell.is_taking = False
            cell.attacker = 0
        db.session.delete(self)
        return True


db.create_all()

# Utility
def GetGameSize():
    i = InfoDb.query.get(0)
    if i == None:
        return None, None
    else:
        return i.width, i.height


def GetResp(t):
    resp = flask.jsonify(t[1])
    resp.status_code = t[0]
    return resp

def GetCurrDbTime():
    res = db.select([db.func.current_timestamp(type_=db.TIMESTAMP, bind=db.engine)]).execute()
    for row in res:
        return row[0]

def GetCurrDbTimeSecs(dbtime = None):
    if dbtime == None:
        dbtime = GetCurrDbTime()
    return (dbtime - datetime.datetime(1970,1,1,tzinfo=dbtime.tzinfo)).total_seconds()

def GetDateTimeFromSecs(secs):
    dbtime = GetCurrDbTime()
    return datetime.datetime.utcfromtimestamp(secs)


#======================================================================
# Server side code 
#======================================================================
@app.route('/startgame', methods=['POST'])
@require('admin_password', 'last_time')
def StartGame():
    data = request.get_json()
    if data['admin_password'] != ADMIN_PASSWORD:
        return GetResp((200, {"msg":"Fail"}))
    softRestart = False
    if "soft" in data and data["soft"] == True:
        softRestart = True
    if "ai_only" in data and data["ai_only"] == True:
        aiOnly = True
    else:
        aiOnly = False
    width = 30
    height = 30
    currTime = GetCurrDbTimeSecs()
    if data['last_time'] != 0:
        endTime = currTime + data['last_time']
    else:
        endTime = 0
    # dirty hack here, set end_time = 1 during initialization so Attack() and 
    # Join() will not work while initialization
    i = InfoDb.query.with_for_update().get(0)
    if i == None:
        i = InfoDb(id = 0, width = width, height = height, max_id = width * height, end_time = endTime, ai_only = aiOnly)
        db.session.add(i)
    else:
        i.width = width
        i.height = height
        i.max_id = width*height
        i.end_time = endTime
        i.ai_only = aiOnly

    totalCells = width * height

    if softRestart:
        CellDb.query.with_for_update().update({'owner' : 0, 'occupy_time' : 0, 'is_taking' : False, 'attacker' : 0, 'attack_time' : 0, 'last_update' : currTime, 'cell_type': 'normal'})
    else:
        for y in range(height):
            for x in range(width):
                c = CellDb.query.with_for_update().get(x + y * width)
                if c == None:
                    c = CellDb(id = x + y * width, x = x, y = y, last_update = currTime)
                    db.session.add(c)
                else:
                    c.owner = 0
                    c.x = x
                    c.y = y
                    c.occupy_time = 0
                    c.is_taking = False
                    c.attacker = 0
                    c.attack_time = 0
                    c.last_update = currTime
                    c.cell_type = 'normal'

    users = UserDb.query.with_for_update().all()
    for user in users:
        db.session.delete(user)

    db.session.commit()

    if GAME_VERSION == 'mainline':
        goldenCells = CellDb.query.order_by(db.func.random()).with_for_update().limit(int(0.02*totalCells))
        for cell in goldenCells:
            cell.cell_type = 'gold'
        db.session.commit()

    return GetResp((200, {"msg":"Success"}))

@app.route('/getgameinfo', methods=['POST'])
def GetGameInfo():
    global pr
    if (pr):
        pr.enable()
    currTime = GetCurrDbTimeSecs()
    data = request.get_json()

    timeAfter = 0
    if 'timeAfter' in data:
        timeAfter = data['timeAfter']

    info = InfoDb.query.with_for_update().get(0)
    if info == None:
        return GetResp((400, {"msg": "No game established"}))
    db.session.commit()

    retInfo = {}
    retInfo['info'] = {'width':info.width, 'height':info.height, 'time':currTime, 'end_time':info.end_time}

    # Refresh the cells that needs to be refreshed first because this will
    # lock stuff
    cells = CellDb.query.filter(CellDb.id < info.max_id).filter_by(is_taking = True).with_for_update().all()

    for cell in cells:
        cell.Refresh(currTime)
    db.session.commit()

    users = UserDb.query.with_for_update().all()
    userInfo = []
    for user in users:
        if user.dirty:
            cellNum = CellDb.query.filter_by(owner = user.id).count()
            if GAME_VERSION == 'mainline':
                cellNum += 4*CellDb.query.filter_by(owner = user.id, cell_type = 'gold').count()
            user.cells = cellNum
            user.dirty = False
        if user.cells == 0:
            user.Dead()
        else:
            userInfo.append({"name":user.name, "id":user.id, "cd_time":user.cd_time, "cell_num":user.cells})
    db.session.commit()

    retInfo['users'] = userInfo

    retCells = []

    changedCells = CellDb.query.filter(CellDb.timestamp >= GetDateTimeFromSecs(timeAfter)).order_by(CellDb.id).all()
    for c in changedCells:
        retCells.append(c.ToDict(currTime))

    retInfo['cells'] = retCells

    resp = GetResp((200, retInfo))

    if pr:
        pr.disable()
        s = StringIO.StringIO()
        ps = pstats.Stats(pr, stream = s).sort_stats('cumulative')
        global pr_interval
        global pr_lastPrint
        if pr_lastPrint + pr_interval < currTime:
            ps.print_stats(30)
            pr_lastPrint = currTime
            print s.getvalue()

    return resp

@app.route('/joingame', methods=['POST'])
@require('name')
def JoinGame():
    info = InfoDb.query.get(0)
    if info.end_time != 0 and GetCurrDbTimeSecs() > info.end_time:
        return GetResp((200, {'err_code':4, "err_msg":"Game is ended"}))
    data = request.get_json()
    users = UserDb.query.order_by(UserDb.id).with_for_update().all()
    availableId = 1
    for u in users:
        if u.id != availableId:
            break
        availableId += 1

    token = base64.urlsafe_b64encode(os.urandom(24))
    newUser = UserDb(id = availableId, name = data['name'], token = token, cells = 1, dirty = False)
    db.session.add(newUser)
    db.session.commit()
    if GAME_VERSION == 'release':
        cell = CellDb.query.filter_by(is_taking = False).order_by(db.func.random()).with_for_update().limit(1).first()
    elif GAME_VERSION == 'mainline':
        cell = CellDb.query.filter_by(is_taking = False, owner = 0).order_by(db.func.random()).with_for_update().limit(1).first()
        if cell == None:
            cell = CellDb.query.filter_by(is_taking = False).order_by(db.func.random()).with_for_update().limit(1).first()

    if cell != None:
        cell.Init(availableId, GetCurrDbTimeSecs())
        db.session.commit()
        return GetResp((200, {'token':token, 'uid':availableId}))
    else:
        db.session.commit()
        return GetResp((200, {'err_code':10, 'err_msg':'No cell available to start'}))
    
@app.route('/attack', methods=['POST'])
@require('cellx', 'celly', 'token')
def Attack():
    data = request.get_json()
    u = UserDb.query.filter_by(token = data['token']).first()
    if u == None:
        return GetResp((400, {"msg":"user not valid"}))
    info = InfoDb.query.get(0)
    if info.end_time != 0 and GetCurrDbTimeSecs() > info.end_time:
        return GetResp((200, {"err_code":4, "err_msg":"Game is ended"}))

    cellx = data['cellx']
    celly = data['celly']
    uid = u.id
    width, height = GetGameSize()
    if width == None:
        return GetResp((400, {"msg":"no valid game"}))
    if (cellx < 0 or cellx >= width or 
            celly < 0 or celly >= height):
        return GetResp((200, {"err_code":1, "err_msg":"Invalid cell position"}))
    c = CellDb.query.with_for_update().get(cellx + celly*width)
    if c == None:
        return GetResp((200, {"err_code":1, "err_msg":"Invalid cell"}))
    success, err_code, msg = c.Attack(uid, GetCurrDbTimeSecs())
    if success:
        return GetResp((200, {"err_code":0}))
    else:
        return GetResp((200, {"err_code":err_code, "err_msg":msg}))

@app.route('/checktoken', methods=['POST'])
@require('token')
def CheckToken():
    data = request.get_json()
    u = UserDb.query.filter_by(token = data['token']).first()
    if u != None:
        return GetResp((200, {"name":u.name, "uid":u.id}))
    return GetResp((400, {"msg":"Fail"}))
    

@app.route('/')
@app.route('/index.html')
def Index():
    i = InfoDb.query.get(0)
    if i != None:
        aiOnly = i.ai_only
    else:
        aiOnly = False
    return render_template('index.html', aiOnly = aiOnly)

@app.route('/admin.html')
def Admin():
    return render_template('admin.html')
