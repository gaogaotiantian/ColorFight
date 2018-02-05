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
    GAME_VERSION = 'full'

if os.environ.get('GAME_REFRESH_INTERVAL') != None:
    gameRefreshInterval = float(os.environ.get('GAME_REFRESH_INTERVAL'))
else:
    gameRefreshInterval = 0.1

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
protocolVersion = 2

energyShop = {
    "blastAtk": 30,
    "blastDef": 40,
    "boost": 10,
    "attack": 2
}

goldShop = {
    "base": 60        
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
                        return GetResp((400, {"msg":"Protocol version too low. If you are using ColorFightAI, please update(git pull) in your directory!"}))
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
    attack_type   = db.Column(db.String(15), default = "normal")
    finish_time   = db.Column(db.Float, default = 0)
    last_update   = db.Column(db.Float, default = 0)
    timestamp     = db.Column(db.TIMESTAMP, default = db.func.current_timestamp(), onupdate = db.func.current_timestamp())
    cell_type     = db.Column(db.String(15), default = "normal")
    build_type    = db.Column(db.String(15), default = "empty")
    build_finish  = db.Column(db.Boolean, default = True)
    build_time    = db.Column(db.Float, default = 0)
    
    def Init(self, owner, currTime):
        self.owner = owner
        self.attack_time = currTime
        self.is_taking = True
        self.finish_time = currTime
        self.attacker = owner
        self.build_time = 0
        self.build_type = "base"
        self.build_finish = True

    def GetTakeTimeEq(self, timeDiff):
        if timeDiff <= 0:
            return 33
        return 30*(2**(-timeDiff/30))+3

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
        return {'o':self.owner, 'a':self.attacker, 'c':int(self.is_taking), 'x': self.x, 'y':self.y, 'ot':self.occupy_time, 'at':self.attack_time, 'aty':self.attack_type, 't': self.GetTakeTime(currTime), 'f':self.finish_time, 'ct':self.cell_type, 'b':self.build_type, 'bt':self.build_time, 'bf':self.build_finish}

    def Refresh(self, currTime):
        if self.is_taking == True and self.finish_time < currTime:
            if self.build_type == "base" and self.owner != self.attacker:
                self.build_type = "empty"
            if not self.build_finish:
                self.build_finish = True
                self.build_time = 0
            self.is_taking = False
            self.owner     = self.attacker
            self.occupy_time = self.finish_time
            self.last_update = currTime
            self.attack_type = 'normal'
            return True
        return False

    def RefreshBuild(self, currTime):
        if self.build_type == "base" and self.build_finish == False and self.build_time + 30 <= currTime:
            self.build_finish = True
            return True
        return False

    # user is a locked instance of UserDb
    # user CD is ready, checked already
    # Do not commit inside this function, it will be done outside of the function
    def Attack(self, user, currTime, boost = False):
        if self.is_taking == True:
            return False, 2, "This cell is being taken."
        # Check whether it's adjacent to an occupied cell
        adjCells = 0
        for d in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
            adjc = CellDb.query.filter_by(x = self.x + d[0], y = self.y + d[1]).first()
            if adjc != None and adjc.owner == user.id:
                adjCells += 1
        if self.owner != user.id and adjCells == 0:
            return False, 1, "Cell position invalid or it's not adjacent to your cell."

        takeTime = (self.GetTakeTime(currTime) * min(1, 1 - 0.25*(adjCells - 1))) / (1 + user.energy/200.0)

        if GAME_VERSION == 'mainline' or GAME_VERSION == "full":
            if boost == True:
                if user.energy < energyShop['boost']:
                    return False, 5, "You don't have enough energy"
                else:
                    user.energy -= energyShop['boost']
                    takeTime = 1

        if user.energy > 0 and self.owner != 0 and user.id != self.owner:
            user.energy = user.energy * 0.95
        self.attacker = user.id
        self.attack_time = currTime
        self.finish_time = currTime + takeTime
        self.is_taking = True
        self.last_update = currTime
        user.cd_time = self.finish_time
        return True, None, None

    def BuildBase(self, uid, currTime):
        if self.is_taking == True:
            return False, 2, "This cell is being taken."
        if self.build_type == "base":
            return False, 6, "This cell is already a base."
        
        currBuildBase = CellDb.query.filter(CellDb.owner == uid).filter(CellDb.build_finish == False).filter(CellDb.build_type == "base").first() is not None
        if currBuildBase:
            return False, 7, "You are already building a base."
        baseNum = CellDb.query.filter_by(owner = uid, build_type = "base").count()
        if baseNum >= 3:
            return False, 8, "You have reached the base number limit"
        
        user = UserDb.query.with_for_update().get(uid)
        if user.cd_time > currTime:
            return False, 3, "You are in CD time!"
        if user.gold < goldShop['base']:
            return False, 5, "Not enough gold!"
        user.gold = user.gold - goldShop['base']
        self.build_type = "base"
        self.build_time = currTime
        self.build_finish = False
        db.session.commit()
        return True, None, None

    def Blast(self, uid, direction, blastType, currTime):
        if blastType == 'attack':
            energyCost = energyShop['blastAtk']
        elif blastType == 'defense':
            energyCost = energyShop['blastDef']
        else:
            return False, 1, "Invalid blastType"

        if blastType == 'attack' and self.owner != uid:
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
            return False, 3, "You are in CD time!"
        if user.energy < energyCost:
            return False, 5, "Not enough energy!"
        user.energy = user.energy - energyCost

        for cell in cells:
            if blastType == 'attack':
                if (cell.x != self.x or cell.y != self.y) and cell.owner != uid:
                    cell.attacker = 0
                    cell.attack_time = currTime
                    cell.finish_time = currTime + 1
                    cell.attack_type = 'blast'
                    cell.is_taking = True
            elif blastType == 'defense':
                if cell.owner == uid:
                    cell.attacker = uid
                    cell.attack_time = currTime
                    cell.finish_time = currTime + 2
                    cell.is_taking = True

        if blastType == 'attack':
            user.cd_time = currTime + 1
        elif blastType == 'defense':
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
    gold_cells    = db.Column(db.Integer, default = 0)
    dirty         = db.Column(db.Boolean, default = False)
    energy        = db.Column(db.Float, default = 0)
    gold          = db.Column(db.Float, default = 0)

    # Pre: lock user
    # Post: lock user
    def Dead(self):
        db.session.delete(self)
        return True


db.create_all()

def ClearCell(uid):
    CellDb.query.filter_by(attacker = uid).with_for_update().update({'is_taking':False, 'attacker':0})
    db.session.commit()
    CellDb.query.filter_by(owner = uid).with_for_update().update({'owner':0, 'build_type':'empty', 'build_finish':True, 'build_time':0})
    db.session.commit()

def MoveBase(baseMoveList):
    for baseData in baseMoveList:
        uid = baseData[0]
        x = baseData[1]
        y = baseData[2]
        directions = [(0,1), (1,0), (0,-1), (-1,0)]
        random.shuffle(directions)
        for d in directions:
            cell = CellDb.query.filter_by(x = x+d[0], y = y+d[1], owner = uid, build_type = "empty").with_for_update().first()
            if cell == None:
                db.session.commit()
            else:
                cell.build_type = "base"
                cell.build_finish = True
                db.session.commit()
                break



# Utility
globalGameWidth = None
globalGameHeight = None
def GetGameSize():
    global globalGameWidth
    global globalGameHeight

    if globalGameWidth == None:
        i = InfoDb.query.get(0)
        if i == None:
            return None, None
        else:
            globalGameWidth = i.width
            globalGameHeight = i.height
    return globalGameWidth, globalGameHeight


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

def UpdateGame(currTime, timeDiff):
    # Refresh the cells that needs to be refreshed first because this will
    # lock stuff
    cells = CellDb.query.filter(CellDb.finish_time < currTime).filter_by(is_taking = True).with_for_update().all()

    dirtyUserIds = set()
    baseMoveList = []
    for cell in cells:
        owner = cell.owner
        isBase = cell.build_type == "base" and cell.build_finish == True
        dirtyUserIds.add(cell.attacker)
        dirtyUserIds.add(cell.owner)
        if cell.Refresh(currTime):
            if isBase and owner != cell.owner:
                baseMoveList.append((owner, cell.x, cell.y))

    db.session.commit()

    cells = CellDb.query.filter(CellDb.build_type == "base").filter(CellDb.build_finish == False).filter(CellDb.build_time + 30 <= currTime).with_for_update().all()
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
            cellNum += 9*db.session.query(db.func.count(CellDb.id)).filter(CellDb.owner == user.id).filter(CellDb.cell_type == 'gold').scalar()
            user.cells = cellNum
            baseNum = db.session.query(db.func.count(CellDb.id)).filter(CellDb.owner == user.id).filter(CellDb.build_type == "base").filter(CellDb.build_finish == True).scalar()
            user.bases = baseNum
            user.energy_cells = db.session.query(db.func.count(CellDb.id)).filter(CellDb.owner == user.id).filter(CellDb.cell_type == 'energy').scalar()
            user.gold_cells = db.session.query(db.func.count(CellDb.id)).filter(CellDb.owner == user.id).filter(CellDb.cell_type == 'gold').scalar()

        if user.cells == 0 or user.bases == 0:
            deadUserIds.append(user.id)
            user.Dead()
        else:
            if timeDiff > 0:
                if user.energy_cells > 0:
                    user.energy = user.energy + timeDiff * user.energy_cells
                    user.energy = min(100, user.energy)
                else:
                    user.energy = max(user.energy, 0)

                if user.gold_cells > 0:
                    user.gold = user.gold + timeDiff * user.gold_cells
                    user.gold = min(100, user.gold)
                else:
                    user.gold = max(user.gold, 0)

    db.session.commit()

    for uid in deadUserIds:
        ClearCell(uid)



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
    width =  30
    height = 30
    global globalGameWidth
    global globalGameHeight

    globalGameWidth = width
    globalGameHeight = height

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
        CellDb.query.with_for_update().update({'owner' : 0, 'occupy_time' : 0, 'is_taking' : False, 'attacker' : 0, 'attack_time' : 0, 'last_update' : currTime, 'cell_type': 'normal', 'build_type': "empty", 'build_finish':"true", 'build_time':0})
    else:
        for y in range(height):
            for x in range(width):
                c = CellDb.query.with_for_update().get(x + y * width)
                if c == None:
                    c = CellDb(id = x + y * width, x = x, y = y, last_update = currTime, build_type = "empty", build_finish = True)
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
                    c.build_type = 'base'
                    c.build_finish = True

    users = UserDb.query.with_for_update().all()
    for user in users:
        db.session.delete(user)

    db.session.commit()

    goldenCells = CellDb.query.order_by(db.func.random()).with_for_update().limit(int(0.02*totalCells))
    for cell in goldenCells:
        cell.cell_type = 'gold'

    if GAME_VERSION == 'full' or GAME_VERSION == 'mainline':
        energyCells = CellDb.query.filter_by(cell_type = 'normal').order_by(db.func.random()).with_for_update().limit(int(0.02*totalCells))
        for cell in energyCells:
            cell.cell_type = 'energy'

    db.session.commit()

    return GetResp((200, {"msg":"Success"}))

@app.route('/getgameinfo', methods=['POST'])
def GetGameInfo():
    global pr
    global gameRefreshInterval
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
    if currTime - info.last_update > gameRefreshInterval:
        timeDiff = currTime - info.last_update
        info.last_update = currTime    
        refreshGame = True
    else:
        refreshGame = False

    retInfo['info'] = {'width':info.width, 'height':info.height, 'time':currTime, 'end_time':info.end_time, 'join_end_time':info.join_end_time, 'game_version':GAME_VERSION}

    db.session.commit()

    if refreshGame:
        UpdateGame(currTime, timeDiff)

    users = UserDb.query.all()
    userInfo = []
    for user in users:
        userInfo.append({"name":user.name, "id":user.id, "cd_time":user.cd_time, "cell_num":user.cells, "base_num":user.bases, "energy_cell_num":user.energy_cells, "gold_cell_num":user.gold_cells, "energy":user.energy, "gold":user.gold})
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
    newUser = UserDb(id = availableId, name = data['name'], token = token, cells = 1, bases = 1, energy_cells = 0, gold_cells = 0, dirty = False, energy = 0, gold = 0)
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

    u = UserDb.query.with_for_update().filter_by(token = data['token']).first()
    if u == None:
        db.session.commit()
        return GetResp((200, {"err_code":21, "err_msg":"Invalid player"}))
    cellx = data['cellx']
    celly = data['celly']
    currTime = GetCurrDbTimeSecs()
    if u.cd_time > currTime:
        db.session.commit()
        return GetResp((200, {"err_code":3, "err_msg":"You are in CD time!"}))

    if GAME_VERSION == 'full' and 'boost' in data and data['boost'] == True:
        boost = True
    else:
        boost = False
    width, height = GetGameSize()
    c = CellDb.query.with_for_update().get(cellx + celly*width)
    if c == None:
        db.session.commit()
        return GetResp((200, {"err_code":1, "err_msg":"Invalid cell"}))
    success, err_code, msg = c.Attack(u, GetCurrDbTimeSecs(), boost)
    # This commit is important because cell.Attack() will not commit
    # At this point, c and user should both be locked
    db.session.commit()
    if success:
        return GetResp((200, {"err_code":0}))
    else:
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

@app.route('/blast', methods=['POST'])
@require('cellx', 'celly', 'token', 'direction', 'blastType', action = True)
def Blast():
    data = request.get_json()
    if GAME_VERSION != "full":
        return GetResp((400, {"err_code":20, "err_msg":"Invalid version"}))
    u = UserDb.query.filter_by(token = data['token']).first()
    cellx = data['cellx']
    celly = data['celly']
    direction = data['direction']
    blastType = data['blastType']
    uid = u.id
    c = CellDb.query.with_for_update().filter_by(x = cellx, y = celly, owner = uid).first()
    if c == None:
        return GetResp((200, {"err_code":1, "err_msg":"Invalid cell"}))
    success, err_code, msg = c.Blast(uid, direction, blastType, GetCurrDbTimeSecs())
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
