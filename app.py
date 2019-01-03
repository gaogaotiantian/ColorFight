# coding=utf-8
import os
import time, datetime
import functools
import base64
import cProfile, pstats, StringIO
import random
import redis
import json

from line_profiler import LineProfiler

import flask
from flask import Flask, request, render_template, redirect
from flask_sqlalchemy import SQLAlchemy
from flask_cors import CORS
from model import db, CellDb, InfoDb, UserDb

if os.environ.get('DATABASE_URL') != None:
    DATABASE_URL = os.environ.get('DATABASE_URL')
else:
    DATABASE_URL = None
if os.environ.get('REDISCLOUD_URL') != None:
    REDIS_URL = os.environ.get('REDISCLOUD_URL')
else:
    REDIS_URL = None
if os.environ.get('ADMIN_PASSWORD') != None:
    ADMIN_PASSWORD = os.environ.get('ADMIN_PASSWORD') 
else:
    ADMIN_PASSWORD = ''
if os.environ.get('ROOM_PASSWORD') != None and os.environ.get('ROOM_PASSWORD') != '':
    ROOM_PASSWORD = os.environ.get('ROOM_PASSWORD') 
else:
    ROOM_PASSWORD = None
if os.environ.get('PROFILE') == 'True':
    pr = LineProfiler()
else:
    pr = None
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
app.config['JSONIFY_PRETTYPRINT_REGULAR'] = False
app.config['JSON_SORT_KEYS'] = False
app.secret_key = base64.urlsafe_b64encode(os.urandom(24))
CORS(app)
with app.app_context():
    db.init_app(app)
    db.create_all()
redisConn = None
if REDIS_URL:
    pool = redis.BlockingConnectionPool.from_url(REDIS_URL, max_connections=9)
    redisConn = redis.Redis(connection_pool = pool)
pr_lastPrint = 0
protocolVersion = 2

energyShop = {
    "blastAtk": 30,
    "blastDef": 40,
    "boost": 15,
    "attack": 2
}

goldShop = {
    "multiattack": 40,
    "blastDef": 40,
    "base": 60        
}

# Features for the game
BASE_ENABLE = True
GOLD_ENABLE = True
ENERGY_ENABLE = True
BOOST_ENABLE = True
BLAST_ENABLE = True
MULTIATTACK_ENABLE = True
if GAME_VERSION == 'release':
    BASE_ENABLE = True
    GOLD_ENABLE = True
    ENERGY_ENABLE = False
    BOOST_ENABLE = False
    BLAST_ENABLE = False
    MULTIATTACK_ENABLE = False
elif GAME_VERSION == 'mainline' or GAME_VERSION == 'full':
    BASE_ENABLE = True
    GOLD_ENABLE = True
    ENERGY_ENABLE = True
    BOOST_ENABLE = True
    BLAST_ENABLE = True
    MULTIATTACK_ENABLE = True

if os.environ.get('GAME_FEATURE') != None:
    try: 
        features = json.loads(os.environ.get('GAME_FEATURE'))
        for feature, enable in features.items():
            if type(enable) != bool:
                raise Exception("You need bool setting")
            if feature.lower() == 'base':
                BASE_ENABLE = enable
            elif feature.lower() == 'gold':
                GOLD_ENABLE = enable
            elif feature.lower() == 'energy':
                ENERGY_ENABLE = enable
            elif feature.lower() == 'boost':
                BOOST_ENABLE = enable
            elif feature.lower() == 'blast':
                BLAST_ENABLE = enable
            elif feature.lower() == 'multiattack':
                MULTIATTACK_ENABLE = enable
    except Exception as e:
        print(e)
        print("Failed to set up using features")

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

globalDbTime = 0
globalServerTime = 0
def GetCurrDbTimeSecs(dbtime = None):
    global globalDbTime
    global globalServerTime
    currTime = time.time()
    if currTime - globalServerTime < 5:
        return currTime - globalServerTime + globalDbTime
    if dbtime == None:
        dbtime = GetCurrDbTime()
    globalDbTime = (dbtime - datetime.datetime(1970,1,1,tzinfo=dbtime.tzinfo)).total_seconds()
    globalServerTime = time.time()
    return globalDbTime

def GetDateTimeFromSecs(secs):
    return datetime.datetime.utcfromtimestamp(secs)

def UpdateGame(currTime, timeDiff):
    global pr
    global gameRefreshInterval
    if (pr):
        pr.enable()
    # Refresh the cells that needs to be refreshed first because this will
    # lock stuff
    cells = CellDb.query.filter(CellDb.finish_time < currTime).filter_by(is_taking = True).with_for_update().all()

    dirtyUserIds = {}
    baseMoveList = []
    for cell in cells:
        owner = cell.owner
        isBase = cell.build_type == "base" and cell.build_finish == True
        if cell.attacker not in dirtyUserIds:
            dirtyUserIds[cell.attacker] = set()
        if cell.owner not in dirtyUserIds:
            dirtyUserIds[cell.owner] = set()
        if isBase:
            dirtyUserIds[cell.attacker].add('base')
            dirtyUserIds[cell.owner].add('base')
        if cell.cell_type == 'energy':
            dirtyUserIds[cell.attacker].add('energy')
            dirtyUserIds[cell.owner].add('energy')
        if cell.cell_type == 'gold':
            dirtyUserIds[cell.attacker].add('gold')
            dirtyUserIds[cell.owner].add('gold')
        if cell.Refresh(currTime):
            if isBase and owner != cell.owner:
                baseMoveList.append((owner, cell.x, cell.y))

    db.session.commit()

    cells = CellDb.query.filter(CellDb.build_type == "base").filter(CellDb.build_finish == False).filter(CellDb.build_time + 30 <= currTime).with_for_update().all()
    for cell in cells:
        if cell.RefreshBuild(currTime):
            if cell.owner not in dirtyUserIds:
                dirtyUserIds[cell.owner] = set()
            dirtyUserIds[cell.owner].add('base')

    db.session.commit()

    MoveBase(baseMoveList)

    users = UserDb.query.with_for_update().all()
    userInfo = []
    deadUserIds = []
    for user in users:
        if user.id in dirtyUserIds:
            if 'base' in dirtyUserIds[user.id]:
                user.bases = db.session.query(db.func.count(CellDb.id)).filter(CellDb.owner == user.id).filter(CellDb.build_type == "base").filter(CellDb.build_finish == True).scalar()
            
            if 'energy' in dirtyUserIds[user.id]:
                user.energy_cells = db.session.query(db.func.count(CellDb.id)).filter(CellDb.owner == user.id).filter(CellDb.cell_type == 'energy').scalar()

            if 'gold' in dirtyUserIds[user.id]:
                user.gold_cells = db.session.query(db.func.count(CellDb.id)).filter(CellDb.owner == user.id).filter(CellDb.cell_type == 'gold').scalar()

            cellNum = db.session.query(db.func.count(CellDb.id)).filter(CellDb.owner == user.id).scalar()
            cellNum += 9*user.gold_cells
            user.cells = cellNum

        if (user.cells == 0 or (BASE_ENABLE and user.bases == 0)) and user.dead_time == 0:
            deadUserIds.append(user.id)
            if not user.Dead(currTime):
                userInfo.append(user.ToDict())

        else:
            if timeDiff > 0:
                if user.energy_cells > 0:
                    user.energy = user.energy + timeDiff * user.energy_cells * 0.5
                    user.energy = min(100, user.energy)
                else:
                    user.energy = max(user.energy, 0)

                if GOLD_ENABLE and user.gold_cells > 0:
                    user.gold = user.gold + timeDiff * user.gold_cells * 0.5
                    user.gold = min(100, user.gold)
                else:
                    user.gold = max(user.gold, 0)
            userInfo.append(user.ToDict())

    db.session.commit()

    for uid in deadUserIds:
        ClearCell(uid)

    if pr:
        pr.disable()

    return userInfo

def ClearGame(currTime, softRestart, gameSize, gameId):
    width = gameSize[0]
    height = gameSize[1]

    if softRestart:
        CellDb.query.with_for_update().update({'owner' : 0, 'occupy_time' : 0, 'is_taking' : False, 'attacker' : 0, 'attack_time' : 0, 'attack_type': 'normal', 'last_update' : currTime, 'cell_type': 'normal', 'build_type': "empty", 'build_finish':"true", 'build_time':0})
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
                    c.attack_type = 'normal'
                    c.last_update = currTime
                    c.cell_type = 'normal'
                    c.build_type = 'empty'
                    c.build_finish = True

    users = UserDb.query.with_for_update().all()
    for user in users:
        db.session.delete(user)

    db.session.commit()

    totalCells = gameSize[0] * gameSize[1]

    goldenCells = CellDb.query.order_by(db.func.random()).with_for_update().limit(int(0.02*totalCells))
    for cell in goldenCells:
        cell.cell_type = 'gold'

    if ENERGY_ENABLE:
        energyCells = CellDb.query.filter_by(cell_type = 'normal').order_by(db.func.random()).with_for_update().limit(int(0.02*totalCells))
        for cell in energyCells:
            cell.cell_type = 'energy'

    db.session.commit()

    if redisConn:
        redisConn.set('gameid', str(gameId))
        info = InfoDb.query.get(0)
        redisConn.set('gameInfo', json.dumps(info.ToDict(currTime)))
        db.session.commit()
    
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
    width  = 30
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
    
    plan_start_time = 0
    if 'plan_start_time' in data and data['plan_start_time'] != 0:
        plan_start_time = data['plan_start_time']
        if endTime != 0:
            endTime += plan_start_time
        if joinEndTime != 0:
            joinEndTime += plan_start_time
        plan_start_time += currTime
    gameId = int(random.getrandbits(30))

    # dirty hack here, set end_time = 1 during initialization so Attack() and 
    # Join() will not work while initialization
    if plan_start_time == 0:
        infoId = 0
        i = InfoDb.query.with_for_update().get(infoId)
    else:
        if redisConn:
            redisConn.set("planStartTime", plan_start_time)
        infoId = 1
        i = InfoDb.query.with_for_update().get(infoId)
    if i == None:
        i = InfoDb(id = infoId, width = width, height = height, max_id = width * height, end_time = endTime, join_end_time = joinEndTime, ai_only = aiOnly, last_update = currTime, game_id = gameId, plan_start_time = plan_start_time)
        db.session.add(i)
    else:
        i.width = width
        i.height = height
        i.max_id = width*height
        i.end_time = endTime
        i.join_end_time = joinEndTime
        i.ai_only = aiOnly
        i.last_update = currTime
        i.game_id = gameId
        i.plan_start_time = plan_start_time

    if redisConn:
        redisConn.set("lastUpdate", 0)

    if plan_start_time == 0:
        ClearGame(currTime, softRestart, (width, height), gameId)
    else:
        i = InfoDb.query.with_for_update().get(0)
        i.plan_start_time = plan_start_time
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
    if data and 'timeAfter' in data:
        timeAfter = data['timeAfter']
    else:
        print('Info! Get a full cell request.')

    useSimpleDict = False

    timeDiff = 0

    retInfo = {}

    # Here we try to use redis to get a better performance
    if redisConn:
        pipe = redisConn.pipeline()
        lastUpdate, gameInfoStr, plan_start_time = pipe.get("lastUpdate").get("gameInfo").get("planStartTime").execute()
        if lastUpdate == None:
            return GetResp((400, {"msg": "No game established"}))

        retInfo['info'] = json.loads(gameInfoStr)
        retInfo['info']['time'] = currTime
        retInfo['info']['plan_start_time'] = plan_start_time
        if lastUpdate != None and currTime - float(lastUpdate) < gameRefreshInterval:
            refreshGame = False
        else:
            pipe = redisConn.pipeline()
            if plan_start_time != None and float(plan_start_time) != 0 and float(plan_start_time) < currTime:
                info = InfoDb.query.with_for_update().get(0)
                infoNext = InfoDb.query.get(1)
                info.Copy(infoNext)
                ClearGame(currTime, True, (info.width, info.height), info.game_id)
                pipe.set("planStartTime", 0)

            timeDiff = currTime - float(lastUpdate)
            pipe.set("lastUpdate", currTime)
            pipe.execute()
            refreshGame = True
            db.session.commit()
    else:
        info = InfoDb.query.with_for_update().get(0)
        if info == None:
            return GetResp((400, {"msg": "No game established"}))
        if currTime - info.last_update > gameRefreshInterval:
            timeDiff = currTime - info.last_update
            info.last_update = currTime    
            refreshGame = True
        else:
            refreshGame = False

        if info.plan_start_time != 0 and info.plan_start_time < currTime:
            infoNext = InfoDb.query.get(1)
            info.Copy(infoNext)
            ClearGame(currTime, True, (info.width, info.height), info.game_id)

        retInfo['info'] = {'width':info.width, 'height':info.height, 'time':currTime, 'end_time':info.end_time, 'join_end_time':info.join_end_time, 'game_id':info.game_id, 'game_version':GAME_VERSION, 'plan_start_time':info.plan_start_time}

        db.session.commit()

    if refreshGame:
        userInfo = UpdateGame(currTime, timeDiff)
    else:
        users = UserDb.query.all()
        userInfo = []
        for user in users:
            userInfo.append(user.ToDict(useSimpleDict))
        db.session.commit()

    retInfo['users'] = userInfo

    retCells = []

    # We give a 0.5 sec buffer so it will have a higher chance to pick up
    # all the changes even with some delay
    changedCells = CellDb.query.filter(CellDb.timestamp >= GetDateTimeFromSecs(timeAfter - 0.5)).order_by(CellDb.id).all()
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
    newUser = UserDb(id = availableId, name = data['name'], token = token, cells = 1, bases = 1, energy_cells = 0, gold_cells = 0, dirty = False, energy = 0, gold = 30, dead_time = 0)
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

    cellx = data['cellx']
    celly = data['celly']
    width, height = GetGameSize()

    if not (0 <= cellx < width and 0 <= celly < height):
        return GetResp((200, {"err_code":1, "err_msg":"Invalid cell position"}))

    currTime = GetCurrDbTimeSecs()

    u = UserDb.query.with_for_update().filter_by(token = data['token']).first()
    if u == None:
        db.session.commit()
        return GetResp((200, {"err_code":21, "err_msg":"Invalid player"}))
    if u.cd_time > currTime:
        db.session.commit()
        return GetResp((200, {"err_code":3, "err_msg":"You are in CD time!"}))

    if 'boost' in data and data['boost'] == True:
        boost = True
    else:
        boost = False

    # Check whether it's adjacent to an occupied cell
    # Query is really expensive, we try to do only one query to finish this
    adjCells = 0
    adjIds = []
    for d in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
        xx = cellx + d[0]
        yy = celly + d[1]
        if 0 <= xx < globalGameWidth and 0 <= yy < globalGameHeight:
            adjIds.append(xx + yy * globalGameWidth)

    adjCells = CellDb.query.filter(CellDb.id.in_(adjIds), CellDb.owner == u.id).count()


    c = CellDb.query.with_for_update().get(cellx + celly*width)
    if c == None:
        db.session.commit()
        return GetResp((200, {"err_code":1, "err_msg":"Invalid cell"}))
    success, err_code, msg = c.Attack(u, currTime, boost, adjCells)
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
    if not BASE_ENABLE:
        return GetResp((200, {"err_code":0}))
    data = request.get_json()
    currTime = GetCurrDbTimeSecs()
    u = UserDb.query.with_for_update().filter_by(token = data['token']).first()
    if u == None:
        db.session.commit()
        return GetResp((200, {"err_code":21, "err_msg":"Invalid player"}))

    if u.gold < goldShop['base']:
        return GetResp((200, {"err_code": 5, "err_msg":"Not enough gold!"}))
    
    if u.build_cd_time > currTime:
        return GetResp((200, {"err_code": 7, "err_msg":"You are in building cd"}))

    baseNum = db.session.query(db.func.count(CellDb.id)).filter(CellDb.owner == u.id).filter(CellDb.build_type == "base").scalar()

    if baseNum >= 3:
        return GetResp((200, {"err_code": 8, "err_msg":"You have reached the base number limit"}))

    cellx = data['cellx']
    celly = data['celly']
    c = CellDb.query.with_for_update().filter_by(x = cellx, y = celly, owner = u.id).first()
    if c == None:
        return GetResp((200, {"err_code":1, "err_msg":"Invalid cell"}))
    success, err_code, msg = c.BuildBase(u, currTime)
    # user and cell is both locked here, clear the lock
    db.session.commit()
    if success:
        return GetResp((200, {"err_code":0}))
    else:
        return GetResp((200, {"err_code":err_code, "err_msg":msg}))

@app.route('/blast', methods=['POST'])
@require('cellx', 'celly', 'token', 'direction', action = True)
def Blast():
    if not BLAST_ENABLE:
        return GetResp((200, {"err_code":0}))
    data = request.get_json()
    u = UserDb.query.filter_by(token = data['token']).first()
    if u == None:
        db.session.commit()
        return GetResp((200, {"err_code":21, "err_msg":"Invalid player"}))
    cellx = data['cellx']
    celly = data['celly']
    direction = data['direction']
    uid = u.id
    c = CellDb.query.with_for_update().filter_by(x = cellx, y = celly, owner = uid).first()
    if c == None:
        return GetResp((200, {"err_code":1, "err_msg":"Invalid cell"}))
    success, err_code, msg = c.Blast(uid, direction, GetCurrDbTimeSecs())
    if success:
        return GetResp((200, {"err_code":0}))
    else:
        db.session.commit()
        return GetResp((200, {"err_code":err_code, "err_msg":msg}))

@app.route('/multiattack', methods=['POST'])
@require('cellx', 'celly', 'token', action = True)
def MultiAttack():
    if not MULTIATTACK_ENABLE:
        return GetResp((200, {"err_code":0}))
    data = request.get_json()

    cellx = data['cellx']
    celly = data['celly']
    width, height = GetGameSize()

    if not (0 <= cellx < width and 0 <= celly < height):
        return GetResp((200, {"err_code":1, "err_msg":"Invalid cell position"}))

    currTime = GetCurrDbTimeSecs()

    u = UserDb.query.with_for_update().filter_by(token = data['token']).first()
    if u == None:
        db.session.commit()
        return GetResp((200, {"err_code":21, "err_msg":"Invalid player"}))
    if u.cd_time > currTime:
        db.session.commit()
        return GetResp((200, {"err_code":3, "err_msg":"You are in CD time!"}))
    if u.gold < goldShop['multiattack']:
        return GetResp((200, {"err_code":5, "err_msg":"Not enough gold!"}))

    # Check whether it's adjacent to an occupied cell
    # Query is really expensive, we try to do only one query to finish this
    adjCells = []
    adjIds = []
    for d in [(-2, 0), (-1, -1), (0, -2), (1, -1), (2, 0), (1, 1), (0, 2), (-1, 1), (0, 0)]:
        xx = cellx + d[0]
        yy = celly + d[1]
        if 0 <= xx < globalGameWidth and 0 <= yy < globalGameHeight:
            adjIds.append(xx + yy*globalGameWidth)
    adjCells = CellDb.query.filter(CellDb.id.in_(adjIds)).filter_by(owner = u.id).all()

    atkCells = []
    atkIds = []
    adjCellDict = {}
    for d in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
        xx = cellx + d[0]
        yy = celly + d[1]

        if 0 <= xx < globalGameWidth and 0 <= yy < globalGameHeight:
            adjCellCount = 0
            for c in adjCells:
                if abs(c.x - xx) + abs(c.y-yy) == 1:
                    adjCellCount += 1
            atkId = xx + yy * globalGameWidth
            atkIds.append(atkId)
            adjCellDict[atkId] = adjCellCount

    atkCells = CellDb.query.with_for_update().filter(CellDb.id.in_(atkIds)).all()

    if not atkCells:
        db.session.commit()
        return GetResp((200, {"err_code":1, "err_msg":"Invalid cell"}))

    for c in atkCells:
        c.Attack(u, currTime, False, adjCellDict[c.id])
    u.gold -= goldShop['multiattack']
    # This commit is important because cell.Attack() will not commit
    # At this point, c and user should both be locked
    db.session.commit()
    return GetResp((200, {"err_code":0}))

@app.route('/checktoken', methods=['POST'])
@require('token')
def CheckToken():
    data = request.get_json()
    u = UserDb.query.filter_by(token = data['token']).first()
    if u != None:
        return GetResp((200, {"name":u.name, "uid":u.id}))
    return GetResp((400, {"msg":"Fail"}))
    

@app.route('/addai', methods=['POST'])
@require('name')
def AddAi():
    data = request.get_json()
    name = data['name']
    if redisConn:
        availableAI = redisConn.lrange("availableAI", 0, -1)
        if name in availableAI:
            redisConn.lpush("aiList", name)
            return GetResp((200, {"msg":"Success"}))
    return GetResp((200, {"msg":"Fail"}))

@app.route('/getailist', methods=['POST'])
def GetAiList():
    ret = []
    if redisConn:
        availableAI = redisConn.lrange("availableAI", 0, -1)
        ret = [name for name in availableAI]
    return GetResp((200, {"aiList":ret}))

@app.route('/')
@app.route('/index.html')
def Index():
    if request.url.startswith('https://'):
        url = request.url.replace('https://', "http://", 1)
        return redirect(url, 301)
    i = InfoDb.query.get(0)
    if i != None:
        aiOnly = i.ai_only
    else:
        aiOnly = False
    return render_template('index.html', aiOnly = aiOnly)

@app.route('/admin.html')
def Admin():
    if request.url.startswith('https://'):
        url = request.url.replace('https://', "http://", 1)
        return redirect(url, 301)
    return render_template('admin.html')

if pr:
    pr.add_function(GetGameInfo)
    pr.add_function(CellDb.Attack)
    pr.add_function(UpdateGame)
