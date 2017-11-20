# coding=utf-8
import os
import time, datetime
import functools
import base64
import cProfile, pstats, StringIO
import random

from line_profiler import LineProfiler

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
if os.environ.get('ROOM_PASSWORD') != None and os.environ.get('ROOM_PASSWORD') != '':
    ROOM_PASSWORD = os.environ.get('ROOM_PASSWORD') 
else:
    ROOM_PASSWORD = None
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
    pr = LineProfiler()
else:
    pr = None
pr_lastPrint = 0
protocolVersion = 1

energyShop = {
    "base": 60,
    "boomAtk": 30,
    "boomDef": 50,
    "boost": 10,
    "attack": 2
}

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
                if arg == 'token':
                    u = UserDb.query.filter_by(token = data['token']).first()
                    if u == None:
                        return GetResp((400, {"msg":"user not valid"}))

            if kw_req_args != None:
                if "action" in kw_req_args:
                    if kw_req_args['action'] == True:
                        info = InfoDb.query.get(0)
                        if info.end_time != 0 and GetCurrDbTimeSecs() > info.end_time:
                            return GetResp((200, {"err_code":4, "err_msg":"Game is ended"}))

                    width, height = GetGameSize()
                    cellx = data['cellx']
                    celly = data['celly']
                    if width == None:
                        return GetResp((400, {"msg":"no valid game"}))
                    if (cellx < 0 or cellx >= width or 
                            celly < 0 or celly >= height):
                        return GetResp((200, {"err_code":1, "err_msg":"Invalid cell position"}))

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
    is_base       = db.Column(db.Boolean, default = False)
    build_time    = db.Column(db.Float, default = 0)
    
    def Init(self, owner, currTime):
        self.owner = owner
        self.attack_time = currTime
        self.is_taking = True
        self.finish_time = currTime
        self.attacker = owner
        self.build_time = 0
        self.is_base = True

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
        return {'o':self.owner, 'a':self.attacker, 'c':int(self.is_taking), 'x': self.x, 'y':self.y, 'ot':self.occupy_time, 'at':self.attack_time, 't': self.GetTakeTime(currTime), 'f':self.finish_time, 'ct':self.cell_type, 'b':self.is_base, 'bt':self.build_time}

    def Refresh(self, currTime):
        if self.is_taking == True and self.finish_time < currTime:
            if self.is_base and self.owner != self.attacker:
                self.is_base = False
            if self.build_time != 0:
                self.build_time = 0
            self.is_taking = False
            self.owner     = self.attacker
            self.occupy_time = self.finish_time
            self.last_update = currTime
            return True
        return False

    def RefreshBuild(self, currTime):
        if self.build_time != 0 and self.build_time + 30 <= currTime:
            self.is_base = True
            self.build_time = 0
            return True
        return False

    def Attack(self, uid, currTime, boost = False):
        if self.is_taking == True:
            return False, 2, "This cell is being taken."
        # Check whether it's adjacent to an occupied cell
        adjCells = 0
        for d in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
            adjc = CellDb.query.filter_by(x = self.x + d[0], y = self.y + d[1]).first()
            if adjc != None and adjc.owner == uid:
                adjCells += 1
        if self.owner != uid and adjCells == 0:
            return False, 1, "Cell position invalid or it's not adjacent to your cell."

        user = UserDb.query.with_for_update().get(uid)
        if user.cd_time > currTime:
            return False, 3, "You are in CD time!"

        takeTime = (self.GetTakeTime(currTime) * min(1, 1 - 0.25*(adjCells - 1))) / (1 + user.energy/100.0)

        if GAME_VERSION == "mainline":
            if boost == True:
                if user.energy < energyShop['boost']:
                    return False, 5, "You don't have enough energy"
                else:
                    user.energy -= energyShop['boost']
                    takeTime = 2

        if user.energy > 0 and self.owner != 0 and uid != self.owner:
            user.energy = int(user.energy * 0.95)
        self.attacker = uid
        self.attack_time = currTime
        self.finish_time = currTime + takeTime
        self.is_taking = True
        self.last_update = currTime
        user.cd_time = self.finish_time
        db.session.commit()
        return True, None, None

    def BuildBase(self, uid, currTime):
        if self.is_taking == True:
            return False, 2, "This cell is being taken."
        if self.is_base == True:
            return False, 6, "This cell is already a base."
        
        currBuildBase = CellDb.query.filter(CellDb.owner == uid).filter(CellDb.build_time != 0).first() is not None
        if currBuildBase:
            return False, 7, "You are already building a base."
        baseNum = CellDb.query.filter_by(owner = uid, is_base = True).count()
        if baseNum >= 3:
            return False, 8, "You have reached the base number limit"
        
        user = UserDb.query.with_for_update().get(uid)
        if user.cd_time > currTime:
            return False, 3, "You are in CD time!"
        if user.energy < energyShop['base']:
            return False, 5, "Not enough energy!"
        user.energy = user.energy - energyShop['base']
        self.build_time = currTime
        db.session.commit()
        return True, None, None

    def Boom(self, uid, direction, boomType, currTime):
        if boomType == 'attack':
            energyCost = energyShop['boomAtk']
        elif boomType == 'defense':
            energyCost = energyShop['boomDef']
        else:
            return False, 1, "Invalid boomType"

        if boomType == 'attack' and self.owner != uid:
            return False, 1, "Cell position invalid!"
        if direction == "square":
            db.session.commit()
            cells = CellDb.query.filter(CellDb.x >= self.x - 1).filter(CellDb.x <= self.x + 1)\
                                .filter(CellDb.y >= self.y - 1).filter(CellDb.y <= self.y + 1)\
                                .with_for_update().all()
        elif direction == "vertical":
            db.session.commit()
            cells = CellDb.query.filter(CellDb.y >= self.y - 4).filter(CellDb.y <= self.y + 4)\
                                .filter(CellDb.x == self.x)\
                                .with_for_update().all()
        elif direction == "horizontal":
            db.session.commit()
            cells = CellDb.query.filter(CellDb.x >= self.x - 4).filter(CellDb.x <= self.x + 4)\
                                .filter(CellDb.y == self.y)\
                                .with_for_update().all()
        else:
            return False, 1, "Invalid direction"

        user = UserDb.query.with_for_update().get(uid)
        if user.cd_time > currTime:
            db.session.commit()
            return False, 3, "You are in CD time!"
        if user.energy < energyCost:
            return False, 5, "Not enough energy!"
        user.energy = user.energy - energyCost

        for cell in cells:
            if boomType == 'attack':
                if cell.x != self.x or cell.y != self.y:
                    cell.attacker = 0
                    cell.attack_time = currTime
                    cell.finish_time = currTime + 1
                    cell.is_taking = True
            elif boomType == 'defense':
                if cell.owner == uid:
                    cell.attacker = uid
                    cell.attack_time = currTime
                    cell.finish_time = currTime + 2
                    cell.is_taking = True

        if boomType == 'attack':
            user.cd_time = currTime + 1
        elif boomType == 'defense':
            user.cd_time = currTime + 2

        db.session.commit()
        return True, None, None



class InfoDb(db.Model):
    __tablename__ = 'info'
    id            = db.Column(db.Integer, primary_key = True)
    width         = db.Column(db.Integer, default = 0)
    height        = db.Column(db.Integer, default = 0)
    max_id        = db.Column(db.Integer, default = 0)         
    end_time      = db.Column(db.Float, default = 0)
    join_end_time = db.Column(db.Float, default = 0)
    ai_only       = db.Column(db.Boolean, default = False)
    last_update   = db.Column(db.Float, default = 0)

class UserDb(db.Model):
    __tablename__ = 'users'
    id            = db.Column(db.Integer, primary_key = True)
    name          = db.Column(db.String(50))
    token         = db.Column(db.String(32), default = "")
    cd_time       = db.Column(db.Integer, default = 0)
    cells         = db.Column(db.Integer, default = 0)
    bases         = db.Column(db.Integer, default = 0)
    energy_cells  = db.Column(db.Integer, default = 0)
    dirty         = db.Column(db.Boolean, default = False)
    energy        = db.Column(db.Integer, default = 0)

    # Pre: lock user
    # Post: lock user
    def Dead(self):
        db.session.delete(self)
        return True



db.create_all()

def ClearCell(uid):
    CellDb.query.filter_by(attacker = uid).with_for_update().update({'is_taking':False, 'attacker':0})
    db.session.commit()
    CellDb.query.filter_by(owner = uid).with_for_update().update({'owner':0, 'is_base':False, 'build_time':0})
    db.session.commit()

def MoveBase(baseMoveList):
    for baseData in baseMoveList:
        uid = baseData[0]
        x = baseData[1]
        y = baseData[2]
        directions = [(0,1), (1,0), (0,-1), (-1,0)]
        random.shuffle(directions)
        for d in directions:
            cell = CellDb.query.filter_by(x = x+d[0], y = y+d[1], owner = uid, is_base = False).with_for_update().first()
            if cell == None:
                db.session.commit()
            else:
                cell.is_base = True
                db.session.commit()
                break



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
    return datetime.datetime.utcfromtimestamp(secs)


#======================================================================
# Server side code 
#======================================================================
@app.route('/startgame', methods=['POST'])
@require('admin_password', 'last_time', 'ai_join_time')
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
    if data['ai_join_time'] != 0:
        joinEndTime = currTime + data['ai_join_time']
    else:
        joinEndTime = 0

    # dirty hack here, set end_time = 1 during initialization so Attack() and 
    # Join() will not work while initialization
    i = InfoDb.query.with_for_update().get(0)
    if i == None:
        i = InfoDb(id = 0, width = width, height = height, max_id = width * height, end_time = endTime, join_end_time = joinEndTime, ai_only = aiOnly, last_update = currTime)
        db.session.add(i)
    else:
        i.width = width
        i.height = height
        i.max_id = width*height
        i.end_time = endTime
        i.join_end_time = joinEndTime
        i.ai_only = aiOnly
        i.last_update = currTime

    totalCells = width * height

    if softRestart:
        CellDb.query.with_for_update().update({'owner' : 0, 'occupy_time' : 0, 'is_taking' : False, 'attacker' : 0, 'attack_time' : 0, 'last_update' : currTime, 'cell_type': 'normal', 'is_base': False, 'build_time':0})
    else:
        for y in range(height):
            for x in range(width):
                c = CellDb.query.with_for_update().get(x + y * width)
                if c == None:
                    c = CellDb(id = x + y * width, x = x, y = y, last_update = currTime, is_base = False)
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
                    c.is_base = False

    users = UserDb.query.with_for_update().all()
    for user in users:
        db.session.delete(user)

    db.session.commit()

    goldenCells = CellDb.query.order_by(db.func.random()).with_for_update().limit(int(0.02*totalCells))
    for cell in goldenCells:
        cell.cell_type = 'gold'

    energyCells = CellDb.query.filter_by(cell_type = 'normal').order_by(db.func.random()).with_for_update().limit(int(0.02*totalCells))
    for cell in energyCells:
        cell.cell_type = 'energy'

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
    else:
        print('Info! Get a full cell request.')

    timeDiff = 0

    retInfo = {}

    info = InfoDb.query.with_for_update().get(0)
    if info == None:
        return GetResp((400, {"msg": "No game established"}))
    if int(currTime) - int(info.last_update) > 0:
        timeDiff = int(currTime) - int(info.last_update)
        info.last_update = max(currTime, info.last_update)    

    retInfo['info'] = {'width':info.width, 'height':info.height, 'time':currTime, 'end_time':info.end_time, 'join_end_time':info.join_end_time, 'game_version':GAME_VERSION}
    db.session.commit()


    # Refresh the cells that needs to be refreshed first because this will
    # lock stuff
    cells = CellDb.query.filter(CellDb.finish_time < currTime).filter_by(is_taking = True).with_for_update().all()

    dirtyUserIds = set()
    baseMoveList = []
    for cell in cells:
        owner = cell.owner
        isBase = cell.is_base
        dirtyUserIds.add(cell.attacker)
        dirtyUserIds.add(cell.owner)
        if cell.Refresh(currTime):
            if isBase and owner != cell.owner:
                baseMoveList.append((owner, cell.x, cell.y))

    db.session.commit()

    cells = CellDb.query.filter(CellDb.build_time != 0).filter(CellDb.build_time + 30 <= currTime).with_for_update().all()
    for cell in cells:
        if cell.RefreshBuild(currTime):
            dirtyUserIds.add(cell.owner)

    db.session.commit()

    MoveBase(baseMoveList)

    users = UserDb.query.with_for_update().all()
    userInfo = []
    deadUserIds = []
    for user in users:
        if user.id in dirtyUserIds:
            cellNum = db.session.query(db.func.count(CellDb.id)).filter(CellDb.owner == user.id).scalar()
            if GAME_VERSION == "release":
                cellNum += 4*db.session.query(db.func.count(CellDb.id)).filter(CellDb.owner == user.id).filter(CellDb.cell_type == 'gold').scalar()
            elif GAME_VERSION == "mainline":
                cellNum += 9*db.session.query(db.func.count(CellDb.id)).filter(CellDb.owner == user.id).filter(CellDb.cell_type == 'gold').scalar()
            user.cells = cellNum
            baseNum = db.session.query(db.func.count(CellDb.id)).filter(CellDb.owner == user.id).filter(CellDb.is_base == True).scalar()
            user.bases = baseNum
            user.energy_cells = db.session.query(db.func.count(CellDb.id)).filter(CellDb.owner == user.id).filter(CellDb.cell_type == 'energy').scalar()
        if user.cells == 0 or user.bases == 0:
            deadUserIds.append(user.id)
            user.Dead()
        else:
            if timeDiff > 0:
                if user.energy_cells > 0:
                    user.energy = user.energy + timeDiff * user.energy_cells
                    user.energy = min(100, user.energy)
                else:
                    user.energy = user.energy - 1
                    user.energy = max(user.energy, 0)
            userInfo.append({"name":user.name, "id":user.id, "cd_time":user.cd_time, "cell_num":user.cells, "base_num":user.bases, "energy_cell_num":user.energy_cells, "energy":user.energy})
    db.session.commit()

    retInfo['users'] = userInfo

    for uid in deadUserIds:
        ClearCell(uid)

    retCells = []

    changedCells = CellDb.query.filter(CellDb.timestamp >= GetDateTimeFromSecs(timeAfter)).order_by(CellDb.id).all()
    for c in changedCells:
        retCells.append(c.ToDict(currTime))

    retInfo['cells'] = retCells

    resp = GetResp((200, retInfo))

    if pr:
        pr.disable()
        global pr_interval
        global pr_lastPrint
        if pr_lastPrint + pr_interval < currTime:
            pr.print_stats()
            pr_lastPrint = currTime

    return resp

@app.route('/joingame', methods=['POST'])
@require('name')
def JoinGame():
    info = InfoDb.query.get(0)
    if info.end_time != 0 and GetCurrDbTimeSecs() > info.end_time:
        return GetResp((200, {'err_code':4, "err_msg":"Game is ended"}))

    if info.join_end_time != 0 and GetCurrDbTimeSecs() > info.join_end_time:
        return GetResp((200, {'err_code':4, "err_msg":"Join time is ended"}))

    data = request.get_json()

    if ROOM_PASSWORD != None:
        if 'password' not in data or data['password'] != ROOM_PASSWORD:
            return GetResp((403, {'err_code':11, "err_msg":"You need password to enter the room"}))

    users = UserDb.query.order_by(UserDb.id).with_for_update().all()
    availableId = 1
    for u in users:
        if u.id != availableId:
            break
        availableId += 1

    token = base64.urlsafe_b64encode(os.urandom(24))
    newUser = UserDb(id = availableId, name = data['name'], token = token, cells = 1, bases = 1, energy_cells = 0, dirty = False, energy = 0)
    db.session.add(newUser)
    db.session.commit()
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
@require('cellx', 'celly', 'token', action = True)
def Attack():
    data = request.get_json()

    u = UserDb.query.filter_by(token = data['token']).first()
    cellx = data['cellx']
    celly = data['celly']
    uid = u.id
    if GAME_VERSION == 'mainline' and 'boost' in data and data['boost'] == True:
        boost = True
    else:
        boost = False
    width, height = GetGameSize()
    c = CellDb.query.with_for_update().get(cellx + celly*width)
    if c == None:
        return GetResp((200, {"err_code":1, "err_msg":"Invalid cell"}))
    success, err_code, msg = c.Attack(uid, GetCurrDbTimeSecs(), boost)
    if success:
        return GetResp((200, {"err_code":0}))
    else:
        db.session.commit()
        return GetResp((200, {"err_code":err_code, "err_msg":msg}))

@app.route('/buildbase', methods=['POST'])
@require('cellx', 'celly', 'token', action = True)
def BuildBase():
    data = request.get_json()
    u = UserDb.query.filter_by(token = data['token']).first()
    cellx = data['cellx']
    celly = data['celly']
    uid = u.id
    c = CellDb.query.with_for_update().filter_by(x = cellx, y = celly, owner = uid).first()
    if c == None:
        return GetResp((200, {"err_code":1, "err_msg":"Invalid cell"}))
    success, err_code, msg = c.BuildBase(uid, GetCurrDbTimeSecs())
    if success:
        return GetResp((200, {"err_code":0}))
    else:
        db.session.commit()
        return GetResp((200, {"err_code":err_code, "err_msg":msg}))

@app.route('/boom', methods=['POST'])
@require('cellx', 'celly', 'token', 'direction', 'boomType', action = True)
def Boom():
    data = request.get_json()
    if GAME_VERSION == "release":
        return GetResp((400, {"err_code":20, "err_msg":"Invalid version"}))
    u = UserDb.query.filter_by(token = data['token']).first()
    cellx = data['cellx']
    celly = data['celly']
    direction = data['direction']
    boomType = data['boomType']
    uid = u.id
    c = CellDb.query.with_for_update().filter_by(x = cellx, y = celly, owner = uid).first()
    if c == None:
        return GetResp((200, {"err_code":1, "err_msg":"Invalid cell"}))
    success, err_code, msg = c.Boom(uid, direction, boomType, GetCurrDbTimeSecs())
    if success:
        return GetResp((200, {"err_code":0}))
    else:
        db.session.commit()
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

if pr:
    pr.add_function(GetGameInfo)
