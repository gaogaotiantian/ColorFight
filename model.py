import flask
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()

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
        if BASE_ENABLE:
            self.build_type = "base"
        else:
            self.build_type = "empty"
        self.build_finish = True

    def GetTakeTimeEq(self, timeDiff):
        if timeDiff <= 0:
            return 33
        return 30*(2**(-timeDiff/30.0))+3

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
        return {
            'o':int(self.owner), 
            'a':int(self.attacker), 
            'c':int(self.is_taking), 
            'x':int(self.x), 
            'y':int(self.y), 
            'ot':float(self.occupy_time), 
            'at':float(self.attack_time), 
            'aty':str(self.attack_type), 
            't': self.GetTakeTime(currTime), 
            'f':float(self.finish_time), 
            'ct':str(self.cell_type), 
            'b':str(self.build_type), 
            'bt':float(self.build_time), 
            'bf':bool(self.build_finish)
        }

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
    # Here we already made sure x and y is valid
    # Do not commit inside this function, it will be done outside of the function
    def Attack(self, user, currTime, boost = False, adjCells = 0):
        global pr
        global gameRefreshInterval
        if (pr):
            pr.enable()

        if self.is_taking == True:
            return False, 2, "This cell is being taken."

        if self.owner != user.id and adjCells == 0:
            return False, 1, "Cell position invalid or it's not adjacent to your cell."

        takeTime = (self.GetTakeTime(currTime) * min(1, 1 - 0.25*(adjCells - 1))) / (1 + user.energy/200.0)

        if BOOST_ENABLE:
            if boost == True:
                if user.energy < energyShop['boost']:
                    return False, 5, "You don't have enough energy"
                else:
                    user.energy -= energyShop['boost']
                    takeTime = max(1, takeTime * 0.25)
            else:
                if user.energy > 0 and self.owner != 0 and user.id != self.owner:
                    user.energy = user.energy * 0.95
        self.attacker = user.id
        self.attack_time = currTime
        self.finish_time = currTime + takeTime
        self.is_taking = True
        self.last_update = currTime
        self.attack_type = 'normal'
        user.cd_time = max(user.cd_time, self.finish_time)
        if pr:
            pr.disable()
        return True, None, None

    def BuildBase(self, user, currTime):
        if not BASE_ENABLE:
            return True, None, None
        if self.is_taking == True:
            return False, 2, "This cell is being taken."
        if self.build_type == "base":
            return False, 6, "This cell is already a base."

        user.gold = user.gold - goldShop['base']
        user.build_cd_time = currTime + 30
        self.build_type = "base"
        self.build_time = currTime
        self.build_finish = False
        return True, None, None

    def Blast(self, uid, direction, currTime):
        energyCost = 0
        goldCost = 0
        if not BLAST_ENABLE:
            return True, None, None
        energyCost = energyShop['blastAtk']

        if self.owner != uid:
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
            if (cell.x != self.x or cell.y != self.y) and (cell.owner != uid or (cell.is_taking and cell.attacker != uid)):
                cell.attacker = 0
                cell.attack_time = currTime
                cell.finish_time = currTime + 1
                cell.attack_type = 'blast'
                cell.is_taking = True

        user.cd_time = currTime + 1

        db.session.commit()
        return True, None, None



class InfoDb(db.Model):
    __tablename__ = 'info'
    id              = db.Column(db.Integer, primary_key = True)
    width           = db.Column(db.Integer, default = 0)
    height          = db.Column(db.Integer, default = 0)
    max_id          = db.Column(db.Integer, default = 0)         
    end_time        = db.Column(db.Float, default = 0)
    join_end_time   = db.Column(db.Float, default = 0)
    ai_only         = db.Column(db.Boolean, default = False)
    last_update     = db.Column(db.Float, default = 0)
    game_id         = db.Column(db.Integer, default = 0)
    plan_start_time = db.Column(db.Float, default = 0)

    def Copy(self, other):
        self.width = other.width
        self.height = other.height
        self.max_id = other.max_id
        self.end_time = other.end_time
        self.join_end_time = other.join_end_time
        self.ai_only = other.ai_only
        self.last_update = other.last_update
        self.game_id = other.game_id
        self.plan_start_time = 0

    def ToDict(self, currTime):
        return {
            'width':int(self.width), 
            'height':int(self.height), 
            'time':float(currTime), 
            'end_time':float(self.end_time), 
            'join_end_time':float(self.join_end_time), 
            'game_id':int(self.game_id), 
            'game_version':str(GAME_VERSION), 
            'plan_start_time':float(self.plan_start_time),
            'ai_only':bool(self.ai_only)
        }

class UserDb(db.Model):
    __tablename__ = 'users'
    id            = db.Column(db.Integer, primary_key = True)
    name          = db.Column(db.String(50))
    token         = db.Column(db.String(32), default = "")
    cd_time       = db.Column(db.Float, default = 0)
    build_cd_time = db.Column(db.Float, default = 0)
    cells         = db.Column(db.Integer, default = 0)
    bases         = db.Column(db.Integer, default = 0)
    energy_cells  = db.Column(db.Integer, default = 0)
    gold_cells    = db.Column(db.Integer, default = 0)
    dirty         = db.Column(db.Boolean, default = False)
    energy        = db.Column(db.Float, default = 0)
    gold          = db.Column(db.Float, default = 0)
    dead_time     = db.Column(db.Float, default = 0)

    # Pre: lock user
    # Post: lock user
    def Dead(self, currTime):
        info = InfoDb.query.get(0);
        if info.end_time != 0:
            self.dead_time    = currTime
            self.token        = ""
            self.energy       = 0
            self.gold         = 0
            self.energy_cells = 0
            self.gold_cells   = 0
            self.bases        = 0
            return False
        else:
            db.session.delete(self)
            return True
    
    def ToDict(self, simple = False):
        # Web display will request for a simple version
        if simple:
            return {"name":self.name, "id":self.id, "cd_time":self.cd_time, "cell_num":self.cells, "energy":self.energy, "gold":self.gold, "dead_time":self.dead_time}
        return {
            "name":self.name.encode("utf-8", "ignore"), 
            "id":int(self.id), 
            "cd_time":float(self.cd_time), 
            "build_cd_time":float(self.build_cd_time), 
            "cell_num":int(self.cells), 
            "base_num":int(self.bases), 
            "energy_cell_num":int(self.energy_cells), 
            "gold_cell_num":int(self.gold_cells), 
            "energy":float(self.energy), 
            "gold":float(self.gold), 
            "dead_time":float(self.dead_time)
        }
