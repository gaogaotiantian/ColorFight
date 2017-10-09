# coding=utf-8
import os

import flask
from flask import Flask, request
from flask_sqlalchemy import SQLAlchemy

if os.environ.get('DATABASE_URL') != None:
    DATABASE_URL = os.environ.get('DATABASE_URL')
else:
    DATABASE_URL = "postgresql+psycopg2://gaotian:password@localhost:5432/colorfight"
app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = DATABASE_URL
db = SQLAlchemy(app)

class CellDb(db.Model):
    __tablename__ = 'cells'
    id            = db.Column(db.Integer, primary_key = True)
    owner         = db.Column(db.Integer, default = 0)
    occupy_time   = db.Column(db.Float, default = 0)
    is_taking     = db.Column(db.Boolean, default = False)
    attacker      = db.Column(db.Integer, default = 0)
    attack_time   = db.Column(db.Float, default = 0)

class InfoDb(db.Model):
    __tablename__ = 'info'
    id            = db.Column(db.Integer, primary_key = True)
    width         = db.Column(db.Integer, default = 0)
    height        = db.Column(db.Integer, default = 0)
    max_id        = db.Column(db.Integer, default = 0)         

db.create_all()


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
    cells = CellDb.query.filter(CellDb.id < info.max_id).order_by(CellDb.id).all()
    retInfo = {}
    retInfo['info'] = {'width':info.width, 'height':info.height}
    cellInfo = []
    for cell in cells:
        c = {}
    return str(retInfo)
