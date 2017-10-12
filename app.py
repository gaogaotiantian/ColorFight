# coding=utf-8
import os
import time
import functools
import base64

import flask
from flask import Flask, request, render_template
from flask_sqlalchemy import SQLAlchemy
from flask_cors import CORS

if os.environ.get('DATABASE_URL') != None:
    DATABASE_URL = os.environ.get('DATABASE_URL')
else:
    DATABASE_URL = "postgresql+psycopg2://gaotian:password@localhost:5432/colorfight"
app = Flask(__name__, static_url_path='/static')
app.config['SQLALCHEMY_DATABASE_URI'] = DATABASE_URL
CORS(app)
db = SQLAlchemy(app)

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
            return func(*args, **kw)
        return wrapper
    return decorator

class CellDb(db.Model):
    __tablename__ = 'cells'
    id            = db.Column(db.Integer, primary_key = True)
    owner         = db.Column(db.Integer, default = 0)
    occupy_time   = db.Column(db.Float, default = 0)
    is_taking     = db.Column(db.Boolean, default = False)
    attacker      = db.Column(db.Integer, default = 0)
    attack_time   = db.Column(db.Float, default = 0)
    finish_time   = db.Column(db.Float, default = 0)
    
    def GetTakeTimeEq(timeDiff):
        if timeDiff <= 0:
            return 200
        return 100/timeDiff

    def GetTakeTime(self, currTime):
        if self.is_taking == False:
            if self.owner != 0:
                takeTime  = self.GetTakeTimeEq(currTime - self.occupy_time)
            else:
                takeTime = 1
        else:
            takeTime = -1

    def Refresh(self, currTime):
        if self.is_taking == True and self.finish_time < currTime:
            self.is_taking = False
            self.owner     = self.attacker
            self.occupy_time = self.finish_time

    def Attack(self, uid, currTime):
        if self.is_taking == True:
            return False
        self.attacker = uid
        self.attack_time = currTime
        self.is_taking = True
        if self.owner == 0:
            self.finish_time = currTime + 1
        elif self.owner == uid:
            self.finish_time = currTime + 2
        else:
            self.finish_time = currTime + self.GetTakeTimeEq(currTime - self.occupy_time)
        db.session.commit()
        return True

class InfoDb(db.Model):
    __tablename__ = 'info'
    id            = db.Column(db.Integer, primary_key = True)
    width         = db.Column(db.Integer, default = 0)
    height        = db.Column(db.Integer, default = 0)
    max_id        = db.Column(db.Integer, default = 0)         

class UserDb(db.Model):
    __tablename__ = 'user'
    id            = db.Column(db.Integer, primary_key = True)
    name          = db.Column(db.String(50))
    token         = db.Column(db.String(32), default = "")
    cd_time       = db.Column(db.Integer)

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
@app.route('/startgame', methods=['GET'])
def StartGame():
    width = 30
    height = 30
    i = InfoDb.query.get(0)
    if i == None:
        i = InfoDb(id = 0, width = width, height = height, max_id = width * height)
        db.session.add(i)
    else:
        i.width = width
        i.height = height
        i.max_id = width*height
    db.session.commit()

    for y in range(height):
        for x in range(width):
            c = CellDb.query.get(x + y * width)
            if c == None:
                c = CellDb(id = x + y * width)
                db.session.add(c)
            else:
                c.owner = 0
                c.occupy_time = 0
                c.is_taking = False
                c.attacker = 0
                c.attack_time = 0
                db.session.commit()
    db.session.commit()
    return "Success"

@app.route('/getgameinfo', methods=['GET'])
def GetGameInfo():
    info = InfoDb.query.get(0)
    if info == None:
        return GetResp((400, {"msg": "No game established"}))
    cells = CellDb.query.filter(CellDb.id < info.max_id).with_for_update().order_by(CellDb.id).all()
    retInfo = {}
    retInfo['info'] = {'width':info.width, 'height':info.height}
    cellInfo = []
    currTime = time.time()
    for cell in cells:
        takeTime = cell.GetTakeTime(currTime)
        cell.Refresh(currTime)
        c = {'o':cell.owner, 'a':cell.attacker, 'c':int(cell.is_taking), 'x': cell.id%info.width, 'y':cell.id/info.height, 't': takeTime, 'f':cell.finish_time}
        cellInfo.append(c)
    db.session.commit()
    retInfo['cells'] = cellInfo
    return GetResp((200, retInfo))

@require('name')
@app.route('/joingame', methods=['POST'])
def JoinGame():
    data = request.get_json()
    users = UserDb.query.order_by(UserDb.id).with_for_update().all()
    availableId = 1
    for u in users:
        if u.id != availableId:
            break
        availableId += 1

    token = base64.urlsafe_b64encode(os.urandom(24))
    newUser = UserDb(id = availableId, name = data['name'], token = token)
    db.session.add(newUser)
    db.session.commit()
    ret = flask.jsonify({'token':token})
    ret.status_code = 200
    return ret
    
@require('cellx', 'celly', 'token')
@app.route('/attack', methods=['POST'])
def Attack():
    data = request.get_json()
    u = UserDb.query.filter_by(token = data['token']).first()
    if u == None:
        return GetResp((400, {"msg":"user not valid"}))
    cellx = data['cellx']
    celly = data['celly']
    uid = u.id
    width, height = GetGameSize()
    if width == None:
        return GetResp((400, {"msg":"no valid game"}))
    if (cellx < 0 or cellx >= width or 
            celly < 0 or celly >= height):
        return GetResp((200, {"err_code":1, "err_msg":"Invalid cell position"}))
    c = CellDb.query.filter_by(id = cellx + celly*width).first()
    if c == None:
        return GetResp((200, {"err_code":1, "err_msg":"Invalid cell"}))
    if c.Attack(uid, time.time()):
        return GetResp((200, {"err_code":0}))
    else:
        return GetResp((200, {"err_code":2, "err_msg":"Can't attack this cell"}))
    
    

@app.route('/index.html')
def Index():
    return render_template('index.html')
