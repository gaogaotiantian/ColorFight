# coding=utf-8
import os
import time
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

app = Flask(__name__, static_url_path='/static')
app.config['SQLALCHEMY_DATABASE_URI'] = DATABASE_URL
app.secret_key = base64.urlsafe_b64encode(os.urandom(24))
CORS(app)
db = SQLAlchemy(app)
lastCells = None
lastUpdate = 0
pr = cProfile.Profile()
pr_lastPrint = 0
pr_interval = 5
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
        return {'o':self.owner, 'a':self.attacker, 'c':int(self.is_taking), 'x': self.x, 'y':self.y, 'ot':self.occupy_time, 'at':self.attack_time, 't': self.GetTakeTime(currTime), 'f':self.finish_time}

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
        if self.owner != uid:
            for d in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
                adjc = CellDb.query.filter_by(x = self.x + d[0], y = self.y + d[1]).first()
                if adjc != None and adjc.owner == uid:
                    break
            else:
                return False, 1, "Cell position invalid or it's not adjacent to your cell."
        user = UserDb.query.get(uid)
        if user.cd_time > currTime:
            return False, 3, "You are in CD time!"
        self.attacker = uid
        self.attack_time = currTime
        self.finish_time = currTime + self.GetTakeTime(currTime)
        self.is_taking = True
        self.last_update = currTime
        db.session.commit()
        user = UserDb.query.with_for_update().get(uid)
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

class UserDb(db.Model):
    __tablename__ = 'users'
    id            = db.Column(db.Integer, primary_key = True)
    name          = db.Column(db.String(50))
    token         = db.Column(db.String(32), default = "")
    cd_time       = db.Column(db.Integer)
    cells         = db.Column(db.Integer)
    dirty         = db.Column(db.Boolean)

    def CheckDead(self):
        if db.session.query(db.exists().where(CellDb.owner == self.id)).scalar():
            return False
        else:
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

#======================================================================
# Server side code 
#======================================================================
@app.route('/startgame', methods=['POST'])
@require('admin_password', 'last_time')
def StartGame():
    data = request.get_json()
    if data['admin_password'] != ADMIN_PASSWORD:
        return GetResp((200, {"msg":"Fail"}))
    width = 30
    height = 30
    currTime = time.time()
    if data['last_time'] != 0:
        endTime = currTime + data['last_time']
    else:
        endTime = 0
    # dirty hack here, set end_time = 1 during initialization so Attack() and 
    # Join() will not work while initialization
    i = InfoDb.query.with_for_update().get(0)
    if i == None:
        i = InfoDb(id = 0, width = width, height = height, max_id = width * height, end_time = 1)
        db.session.add(i)
    else:
        i.width = width
        i.height = height
        i.max_id = width*height
        i.end_time = 1
    db.session.commit()

    for y in range(height):
        for x in range(width):
            c = CellDb.query.with_for_update().get(x + y * width)
            if c == None:
                c = CellDb(id = x + y * width, x = x, y = y, lastUpdate = currTime)
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
    db.session.commit()

    users = UserDb.query.all()
    for user in users:
        db.session.delete(user)
    db.session.commit()

    i = InfoDb.query.with_for_update().get(0)
    i.end_time = endTime;
    db.session.commit()

    global lastUpdate
    lastUpdate = 1
    
    return GetResp((200, {"msg":"Success"}))

@app.route('/getgameinfo', methods=['POST'])
def GetGameInfo():
    data = request.get_json()
    global pr
    if (pr):
        pr.enable()
    timeAfter = 0
    if 'timeAfter' in data:
        timeAfter = data['timeAfter']

    info = InfoDb.query.get(0)
    if info == None:
        return GetResp((400, {"msg": "No game established"}))

    currTime = time.time()

    retInfo = {}
    retInfo['info'] = {'width':info.width, 'height':info.height, 'time':currTime, 'end_time':info.end_time}

    global lastCells
    global lastUpdate
    if lastCells == None:
        cells = CellDb.query.filter(CellDb.id < info.max_id).order_by(CellDb.id).all()
        cellInfo = []

        for cell in cells:
            c = cell.ToDict(currTime)
            cellInfo.append(c)
        lastCells = cellInfo

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
            user.cells = cellNum
            user.dirty = False
        if user.cells == 0:
            user.CheckDead()
        else:
            userInfo.append({"name":user.name, "id":user.id, "cd_time":user.cd_time, "cell_num":user.cells})
    db.session.commit()

    retInfo['users'] = userInfo

    # Now update the actual info
    cells = CellDb.query.filter(CellDb.id < info.max_id).filter(CellDb.last_update > lastUpdate).all()
    for cell in cells:
        lastCells[cell.id] = cell.ToDict(currTime)
    lastUpdate = currTime

    retCells = []
    if timeAfter == 0:
        fakeCell = CellDb()
        for idx in range(len(lastCells)):
            if lastCells[idx]['c'] == 0:
                if lastCells[idx]['o'] == 0:
                    lastCells[idx]['t'] = 2
                else:
                    lastCells[idx]['t'] = fakeCell.GetTakeTimeEq(currTime - lastCells[idx]['ot'])
            else:
                lastCells[idx]['t'] = -1
        retCells = lastCells
    else:
        changedCells = CellDb.query.filter(CellDb.last_update >= timeAfter).all()
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
    if info.end_time != 0 and time.time() > info.end_time:
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
    cell = CellDb.query.filter_by(is_taking = False).order_by(db.func.random()).with_for_update().limit(1).first()
    if cell != None:
        cell.Init(availableId, time.time())
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
    if info.end_time != 0 and time.time() > info.end_time:
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
    c = CellDb.query.filter_by(id = cellx + celly*width).with_for_update().first()
    if c == None:
        return GetResp((200, {"err_code":1, "err_msg":"Invalid cell"}))
    success, err_code, msg = c.Attack(uid, time.time())
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
    return render_template('index.html')

@app.route('/admin.html')
def Admin():
    return render_template('admin.html')
