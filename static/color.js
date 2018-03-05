//hostUrl = "http://localhost:8000/"
hostUrl = "http://colorfight.herokuapp.com/"
var gameStatus = {"cellSize":20, 'cells':[], 'info':[], 'selectId': -1, 'globalDirty': false}
var once = {'once':0};
var lastUpdate = 0;
var fullInfo = false;
var attackImg = new Image();
attackImg.src = '/static/attack.png';
var baseImg = new Image();
baseImg.src = '/static/base.png';
var shieldImg = new Image();
shieldImg.src = '/static/shield.png';
var blastImg = new Image();
blastImg.src = '/static/blast.png';
var lastCurrTime = 0;
var lastClientTime = 0;

GetGameInfo = function() {
    if (!fullInfo) {
        $.ajax( {
            url: hostUrl+"getgameinfo",
            method: "POST",
            dataType: "json",
            contentType: 'application/json;charset=UTF-8',
            data: JSON.stringify({'protocol':2, 'display':true}),
            success: function(data) {
                var gameInfo = data;
                var currTime = gameInfo['info']['time'];
                ListUsers(gameInfo['users'], currTime);
                WriteTimeLeft(gameInfo['info']);
                gameStatus.cells = gameInfo['cells'];
                gameStatus.info = gameInfo['info'];
                gameStatus['globalDirty'] = true;
                lastUpdate = currTime;
                lastCurrTime = currTime;
                var d = new Date();
                lastClientTime = d.getTime()/1000.0;
            },
        }).always(function() {
            setTimeout(GetGameInfo, 400);
        });
        fullInfo = true;
    } else {
        $.ajax( {
            url: hostUrl+"getgameinfo",
            method: "POST",
            dataType: "json",
            contentType: 'application/json;charset=UTF-8',
            data: JSON.stringify({'protocol':2, 'timeAfter':lastUpdate, 'display':true}),
            success: function(data) {
                var gameInfo = data;
                var currTime = gameInfo['info']['time'];
                ListUsers(gameInfo['users'], currTime);
                WriteTimeLeft(gameInfo['info']);
                for (var idx in gameInfo['cells']) {
                    cell = gameInfo['cells'][idx];
                    gameStatus['cells'][cell.x+cell.y*gameInfo['info']['width']] = cell;
                    gameStatus['cells'][cell.x+cell.y*gameInfo['info']['width']]['dirty'] = true;
                }
                for (var idx in gameStatus['cells']) {
                    UpdateTakeTime(gameStatus['cells'][idx], currTime)
                }
                gameStatus.info = gameInfo['info'];
                lastUpdate = currTime;
                lastCurrTime = currTime;
                var d = new Date();
                lastClientTime = d.getTime()/1000.0;
            },
        }).always(function() {
            setTimeout(GetGameInfo, 400);
        });
    }
    if (gameStatus['info']['ai_only']) {
        $('#join_div').css("display", "none");
    } else {
        $('#join_div').css("display", "flex");
    }
}
GetTakeTimeEq = function(timeDiff) {
   if (timeDiff <= 0) {
       return 33
   }
   return 30*(Math.pow(2,(-timeDiff/30)))+3
}
UpdateTakeTime = function(cell, currTime) {
    if (cell['c'] == 1) {
        cell['t'] = -1;
    } else {
        if (cell['o'] == 0) {
            cell['t'] = 2;
        } else {
            var newTime = GetTakeTimeEq(currTime - cell['ot'])
            if (Math.abs(cell['t'] - newTime) > 0.5) {
                cell['t'] = newTime;
                cell['dirty'] = true;
            }
        }
    }
}
WriteTimeLeft = function(info) {
    var s = '';
    if (info['plan_start_time'] && info['plan_start_time'] > info['time']) {
        s += "The game will restart in " + parseInt(info['plan_start_time'] - info['time']).toString();
        s += ' '
    }
    if (info['join_end_time'] != 0) {
        if (info['join_end_time'] < info['time']) {
            s += 'No player is allowed to join now!';
        } else {
            s += 'Join time left: ' + parseInt(info['join_end_time'] - info['time']).toString();
        }
        s += ' '
    }
    if (info['end_time'] != 0) {
        if (info['end_time'] < info['time']) {
            s += 'Game ended!';
        } else {
            s += 'Time left: ' + parseInt(info['end_time'] - info['time']).toString();
        }
    }
    $('#time_left').text(s);
}
ListUsers = function(users, currTime) {
    $('#user_list').empty();
    console.log(users)
    users = users.sort(function(a,b) { 
        if (a['dead_time'] == 0 && b['dead_time'] == 0) {
            return b['cell_num'] - a['cell_num'];
        } else {
            if (a['dead_time'] == 0) {
                return -1;
            } else if (b['dead_time'] == 0) {
                return 1;
            } else {
                if (b['cell_num'] == a['cell_num']) {
                    return b['dead_time'] - a['dead_time'];
                }
                return b['cell_num'] - a['cell_num'];
            }
        }
        return 0;
    })
    for (idx in users) {
        user = users[idx];
        var $userRow = $("<div>").addClass("row user-row").attr("uid", user['id']);
        var $goldRow = $("<div>").addClass("progress");
        var $energyRow = $("<div>").addClass("progress");
        var userColor  = HashIdToColor(user['id']);
        if (user['dead_time'] != 0) {
            userColor = '#777777';
        }
        if (user['cd_time'] > currTime) {
            $userRow.append($("<div>").addClass("col-9 user-col").css({"padding":"0px"}).append($("<i>").addClass("fa fa-ban text-danger")).append($("<span>").text(" "+ user['name']).addClass("user_name").css("color", userColor)))
        } else {
            $userRow.append($("<div>").addClass("col-9 user-col").css({"padding":"0px"}).append($("<i>").addClass("fa fa-check text-success")).append($("<span>").text(" "+ user['name']).addClass("user_name").css("color", userColor)))
        }
        $userRow.append($("<div>").addClass("col-3").append($("<span>").text(user['cell_num'].toString()).addClass("user_name").css("color", userColor)));

        var goldBarWidth = user['gold'].toString() + '%';
        var energyBarWidth = user['energy'].toString() + '%';
        $goldRow.append($("<div>").addClass("progress-bar bg-warning").attr("role", "progressbar").css({"width":goldBarWidth, "height":"4px"}));
        $energyRow.append($("<div>").addClass("progress-bar").attr("role", "progressbar").css({"width":energyBarWidth, "height":"4px"}));
        var $userDiv = $("<div>").addClass("col-12").css({"margin-bottom":"5px"}).append($userRow);
        $userDiv.append($goldRow);
        $userDiv.append($energyRow);

        $('#user_list').append($userDiv);
    }
}
DrawGame = function() {
    var canvas = $('#my_canvas');
    var info = gameStatus['info'];
    var cells = gameStatus['cells'];

    var d = new Date();
    clientTime = d.getTime()/1000.0;

    var currTime = lastCurrTime + clientTime - lastClientTime;
    var w = canvas.parent().width();
    if (w + canvas.offset().top > window.innerHeight) {
        w = window.innerHeight - canvas.offset().top;
    }

    // If we need a global refresh, we clear the canvas
    if (w != canvas[0].width || gameStatus['globalDirty'] == true) {
        canvas[0].width = w;
        canvas[0].height = w;
        gameStatus['globalDirty'] = true;
    }

    gameStatus.cellSize = Math.floor(w/info['width']);
    var width = info['width'];
    var height = info['height'];

    if (gameStatus['globalDirty']) {
        var gDirty = true;
    }

    for (idx in cells) {
        var cell = cells[idx];
        var owner = cell['o'];
        var attacker = cell['a'];
        var strokeColor = 'white';
        var strokeWidth = 3;

        if (gDirty || cell['dirty'] || cell['c'] != 0 ||
                ('bt' in cell && cell['bt'] > 0)) {
            if (gameStatus['selectId'] == owner) {
                var fillColor = HashIdToColor(owner);
                strokeWidth = 2;
            } else {
                if (cell['c'] == 0) {
                    var fillColor = CombineColor(HashIdToColor(0), HashIdToColor(owner), Math.min(1, cell['t']/8));
                } else {
                    var fillColor = CombineColor(HashIdToColor(owner), HashIdToColor(attacker), Math.min(1, (currTime - cell['at']) / (cell['f'] - cell['at'])));
                }
            }

            if ('ct' in cell && cell['ct'] == 'gold' ) {
                strokeColor = '#999900'
            }
            if ('ct' in cell && cell['ct'] == 'energy') {
                canvas.drawPolygon( {
                    fillStyle: fillColor,
                    strokeStyle: '#4444AA',
                    strokeWidth: strokeWidth,
                    x: cell.x*gameStatus.cellSize,
                    y: cell.y*gameStatus.cellSize,
                    fromCenter: false,
                    radius: (gameStatus.cellSize-strokeWidth)/2,
                    sides: 6
                })
            } else {
                canvas.drawRect( {
                    fillStyle: fillColor,
                    strokeStyle: strokeColor,
                    strokeWidth: strokeWidth,
                    x: cell.x*gameStatus.cellSize,
                    y: cell.y*gameStatus.cellSize,
                    fromCenter: false,
                    width: gameStatus.cellSize-strokeWidth,
                    height: gameStatus.cellSize-strokeWidth,
                    cornerRadius: 8
                });
            }

            if (cell['b'] == "base" && cell['bf'] == true) {
                canvas.drawImage( {
                    source: baseImg,
                    x: cell.x*gameStatus.cellSize,
                    y: cell.y*gameStatus.cellSize,
                    fromCenter: false,
                    width: gameStatus.cellSize-2,
                    height: gameStatus.cellSize-2
                });
            }
            if (cell['c'] != 0) {
                if (cell['aty'] == "blast") {
                    canvas.drawImage( {
                        source: blastImg,
                        x: cell.x*gameStatus.cellSize,
                        y: cell.y*gameStatus.cellSize,
                        fromCenter: false,
                        width: gameStatus.cellSize-1,
                        height: gameStatus.cellSize-1
                    });

                } else if (cell['o'] != cell['a']) {
                    canvas.drawImage( {
                        source: attackImg,
                        x: cell.x*gameStatus.cellSize+3,
                        y: cell.y*gameStatus.cellSize+3,
                        fromCenter: false,
                        width: gameStatus.cellSize-7,
                        height: gameStatus.cellSize-7
                    });
                } else {
                    canvas.drawImage( {
                        source: shieldImg,
                        x: cell.x*gameStatus.cellSize+3,
                        y: cell.y*gameStatus.cellSize+3,
                        fromCenter: false,
                        width: gameStatus.cellSize-7,
                        height: gameStatus.cellSize-7
                    });
                }
            }
        }
        if (cell['dirty']) {
            cell['dirty'] = false;
        }

        // This part is animation, we draw it regardless for now 
        if (cell['b'] == 'base' && cell['bf'] == false) {
            canvas.drawImage( {
                source: baseImg,
                x: cell.x*gameStatus.cellSize,
                y: cell.y*gameStatus.cellSize,
                fromCenter: false,
                width: gameStatus.cellSize-2,
                height: gameStatus.cellSize-2,
                opacity: Math.abs(currTime - Math.floor(currTime) - 0.5)*2
            });
        }
    }

    if (gDirty) {
        gameStatus['globalDirty'] = false;
    }
}

CreateTitle = function() {
    var s = "COLORFIGHT!";
    for (var i = 0; i < s.length; i++) {
        var c = s.charAt(i);
        var $letter = $('<span>').text(c).css({"color":HashIdToColor(i+1)})
        $('#title').append($letter);
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
//https://sashat.me/2017/01/11/list-of-20-simple-distinct-colors/
var colors = ['#DDDDDD', '#E6194B', '#3Cb44B', '#FFE119', '#0082C8', '#F58231', 
    '#911EB4', '#46F0F0', '#F032E6', '#D2F53C', '#008080', 
    '#AA6E28', '#800000', '#AAFFC3', '#808000', '#000080', '#FABEBE', '#E6BEFF']
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

UpdateAiList = function() {
    $.ajax( {
        url: hostUrl+"getailist",
        method: "POST",
        dataType: "json",
        contentType: 'application/json;charset=UTF-8',
        data: "",
        success: function(msg) {
            console.log(msg);
            var aiList = msg['aiList'];
            $('#ai_list').empty();
            for (i in aiList) {
                var name = aiList[i];
                $('#ai_list').append($('<option>').val(name).html(name));
            }
        },
    })
}

AddAi = function() {
    var name = $('#ai_list').find(":selected").text();
    $.ajax( {
        url: hostUrl+"addai",
        method: "POST",
        dataType: "json",
        contentType: 'application/json;charset=UTF-8',
        data: JSON.stringify({"name":name}),
        success: function(msg) {
        },
    })
    
}
$(function() {
    var canvas = $('#my_canvas');
    canvas[0].width = canvas.parent().width()
    canvas[0].height = canvas[0].width
    CreateTitle();
    UpdateAiList();
    GetGameInfo();

    $('#join').click(function(event) {
        event.preventDefault();
        JoinGame();
    })
    $('#addai').click(function(event) {
        event.preventDefault();
        AddAi();
    })

    $('#my_canvas').click(function(e) {
        if (gameStatus.token) {
            xy = CanvasToXY(e.offsetX, e.offsetY);
            Attack(xy[0], xy[1], gameStatus.token);
        }
    })

    $('body').on("mouseenter", '.user-row', function() {
        gameStatus['selectId'] = $(this).attr("uid");
        gameStatus['globalDirty'] = true;
    })
    $('body').on("mouseleave", '.user-row', function() {
        gameStatus['selectId'] = -1;
        gameStatus['globalDirty'] = true;
    })
    $('body').on("mouseleave", '#user_list', function() {
        gameStatus['selectId'] = -1;
        gameStatus['globalDirty'] = true;
    })
    setInterval(DrawGame, 50);
    setInterval(function() {
        gameStatus['globalDirty'] = true;
    }, 1000);
})

