//hostUrl = "http://localhost:8000/"
hostUrl = "https://colorfight.herokuapp.com/"
var gameStatus = {"cellSize":20, 'cells':[]}
var once = {'once':0};
var lastUpdate = 0;
var fullInfo = false;
var attackImg = new Image();
attackImg.src = '/static/attack.png';
GetGameInfo = function() {
    if (!fullInfo) {
        $.ajax( {
            url: hostUrl+"getgameinfo",
            method: "POST",
            dataType: "json",
            contentType: 'application/json;charset=UTF-8',
            data: JSON.stringify({'protocol':1}),
            success: function(data) {
                var gameInfo = data;
                var currTime = gameInfo['info']['time'];
                ListUsers(gameInfo['users'], currTime);
                WriteTimeLeft(gameInfo['info']);
                DrawGame($('#my_canvas'), gameInfo['info'], gameInfo['cells']);
                gameStatus.cells = gameInfo['cells'];
                lastUpdate = currTime;
            },
        }).always(function() {
            setTimeout(GetGameInfo, 200);
        });
        fullInfo = true;
    } else {
        $.ajax( {
            url: hostUrl+"getgameinfo",
            method: "POST",
            dataType: "json",
            contentType: 'application/json;charset=UTF-8',
            data: JSON.stringify({'protocol':1, 'timeAfter':lastUpdate}),
            success: function(data) {
                var gameInfo = data;
                var currTime = gameInfo['info']['time'];
                ListUsers(gameInfo['users'], currTime);
                WriteTimeLeft(gameInfo['info']);
                for (var idx in gameInfo['cells']) {
                    cell = gameInfo['cells'][idx];
                    gameStatus['cells'][cell.x+cell.y*gameInfo['info']['width']] = cell;
                }
                for (var idx in gameStatus['cells']) {
                    UpdateTakeTime(gameStatus['cells'][idx], currTime)
                }
                DrawGame($('#my_canvas'), gameInfo['info'], gameStatus['cells']);
                lastUpdate = currTime;
            },
        }).always(function() {
            setTimeout(GetGameInfo, 200);
        });
    }
}
GetTakeTimeEq = function(timeDiff) {
   if (timeDiff <= 0) {
       return 200
   }
   return 20*(Math.pow(2,(-timeDiff/20)))+2
}
UpdateTakeTime = function(cell, currTime) {
    if (cell['c'] == 1) {
        cell['t'] = -1;
    } else {
        if (cell['o'] == 0) {
            cell['t'] = 1;
        } else {
            cell['t'] = GetTakeTimeEq(currTime - cell['ot'])
        }
    }
}
WriteTimeLeft = function(info) {
    if (info['end_time'] == 0) {
        $("#time_left").text('');
    } else {
        if (info['end_time'] < info['time']) {
            $('#time_left').text('Game ended!');
        } else {
            $('#time_left').text('Time left: '+parseInt(info['end_time'] - info['time']).toString());
        }
    }
}
ListUsers = function(users, currTime) {
    $('#user_list').empty();
    users = users.sort(function(a,b) { 
        if (a['cell_num'] > b['cell_num']) {
            return -1;
        } else if (a['cell_num'] < b['cell_num']) {
            return 1;
        }
        return 0;
    });
    for (idx in users) {
        user = users[idx];
        var $userRow = $("<div>").addClass("row");
        if (user['cd_time'] > currTime) {
            $userRow.append($("<div>").addClass("col-8").append($("<i>").addClass("fa fa-ban text-danger")).append($("<span>").text(" "+ user['name']).addClass("user_name").css("color", HashIdToColor(user['id']))))
        } else {
            $userRow.append($("<div>").addClass("col-8").append($("<i>").addClass("fa fa-check text-success")).append($("<span>").text(" "+ user['name']).addClass("user_name").css("color", HashIdToColor(user['id']))))
        }
        $userRow.append($("<div>").addClass("col-4").append($("<span>").text(user['cell_num'].toString()).addClass("user_name").css("color", HashIdToColor(user['id']))));
        var $userDiv = $("<div>").addClass("col-3").append($userRow);
        $('#user_list').append($userDiv);
    }
}
DrawGame = function(canvas, info, cells) {
    var w = canvas.parent().width();
    if (w + canvas.offset().top > window.innerHeight) {
        w = window.innerHeight - canvas.offset().top;
    }
    canvas[0].width = w;
    canvas[0].height = w;
    gameStatus.cellSize = Math.floor(w/info['width']);
    var width = info['width'];
    var height = info['height'];
    var currTime = info['time'];
    for (idx in cells) {
        var cell = cells[idx];
        var owner = cell['o'];
        var attacker = cell['a'];
        var strokeColor = 'white';
        if (cell['c'] == 0) {
            var fillColor = CombineColor(HashIdToColor(0), HashIdToColor(owner), Math.min(1, cell['t']/10));
        } else {
            var fillColor = CombineColor(HashIdToColor(owner), HashIdToColor(attacker), Math.min(1, (currTime - cell['at']) / (cell['f'] - cell['at'])));
        }

        if ('ct' in cell && cell['ct'] == 'gold' ) {
            strokeColor = '#999900'
        }
        canvas.drawRect( {
            fillStyle: fillColor,
            strokeStyle: strokeColor,
            strokeWidth: 3,
            x: cell.x*gameStatus.cellSize,
            y: cell.y*gameStatus.cellSize,
            fromCenter: false,
            width: gameStatus.cellSize-3,
            height: gameStatus.cellSize-3,
            cornerRadius: 8
        });
        if (cell['c'] != 0) {
            canvas.drawImage( {
                source: attackImg,
                x: cell.x*gameStatus.cellSize+3,
                y: cell.y*gameStatus.cellSize+3,
                fromCenter: false,
                width: gameStatus.cellSize-6,
                height: gameStatus.cellSize-6
            });
        }
    }
}

HexCombine = function(src, dest, per) {
    var isrc = parseInt(src, 16);
    var idest = parseInt(dest, 16);
    var curr = Math.floor(isrc + (idest - isrc)*per);
    return ("0"+curr.toString(16)).slice(-2).toUpperCase()
}

CombineColor = function(src, dest, per) {
    if (per < 0) {
        per = 0;
    }
    return "#" + HexCombine(src.slice(1, 3), dest.slice(1, 3), per) + 
        HexCombine(src.slice(3, 5), dest.slice(3, 5), per) +
        HexCombine(src.slice(5), dest.slice(5), per)
}
GetRandomColor = function() {
    var r = ("0"+Math.floor(Math.random()*255).toString(16)).slice(-2).toUpperCase();
    var g = ("0"+Math.floor(Math.random()*255).toString(16)).slice(-2).toUpperCase();
    var b = ("0"+Math.floor(Math.random()*255).toString(16)).slice(-2).toUpperCase();

    return '#' + r + g + b;
}
var colors = ['#DDDDDD', '#FF0000', '#00FF00', '#0000FF', '#00FFFF', 
    '#FF00FF', '#FFFF00', '#FF8800', '#FF0088', '#88FF00', '#00FF88', 
    '#8800FF', '#0088FF']
HashIdToColor = function(id) {
    if (id < colors.length) {
        return colors[id];
    } else {
        while (colors.length <= id) {
            colors.push(GetRandomColor());
        }
        return colors[id];
    }
}

JoinGame = function() {
    if ($('#name').val() != '') {
        $.ajax( {
            url: hostUrl+"joingame",
            method: "POST",
            dataType: "json",
            contentType: 'application/json;charset=UTF-8',
            data: JSON.stringify({"name":$('#name').val()}),
            success: function(msg) {
                gameStatus.token = msg['token'];
            },
        })
    }
}

Attack = function(x, y, token) {
    $.ajax( {
        url: hostUrl+"attack",
        method: "POST",
        dataType: "json",
        contentType: 'application/json;charset=UTF-8',
        data: JSON.stringify({"cellx":x, "celly":y, "token":token}),
        success: function(msg) {
        },
    })
}

CanvasToXY = function(canvasX, canvasY) {
    return [Math.floor(canvasX/gameStatus.cellSize), Math.floor(canvasY/gameStatus.cellSize)]
}
$(function() {
    var canvas = $('#my_canvas');
    canvas[0].width = canvas.parent().width()
    canvas[0].height = canvas[0].width
    GetGameInfo();

    $('#join').click(function() {
        JoinGame();
    })

    $('#my_canvas').click(function(e) {
        if (gameStatus.token) {
            xy = CanvasToXY(e.offsetX, e.offsetY);
            Attack(xy[0], xy[1], gameStatus.token);
        }
    })
})

