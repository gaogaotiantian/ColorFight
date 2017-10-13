//hostUrl = "http://localhost:8000/"
hostUrl = "http://colorfight.herokuapp.com/"
var gameStatus = {}
var once = {'once':0};
GetGameInfo = function() {
    $.get(hostUrl + "getgameinfo", 
        function(data) {
            var gameInfo = data;
            ListUsers(gameInfo['users']);
            DrawGame($('#my_canvas'), gameInfo['info'], gameInfo['cells']);
        }
    );
}
ListUsers = function(users) {
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
        $('#user_list').append($("<div>").append($("<span>").text(user['name'] + ' | ' + user['cell_num'].toString()).css("color", HashIdToColor(user['id']))));
    }
}
DrawGame = function(canvas, info, cells) {
    var width = info['width'];
    var height = info['height'];
    var currTime = info['time'];
    for (idx in cells) {
        var cell = cells[idx];
        var owner = cell['o'];
        var attacker = cell['a'];
        if (cell['c'] == 0) {
            if (cell['t'] < 1) {
                console.log(cell)
            }
            canvas.drawRect( {
                fillStyle: CombineColor(HashIdToColor(0), HashIdToColor(owner), Math.min(1, cell['t']/20)),
                strokeStyle: 'white',
                strokeWidth: 3,
                x: cell.x*20,
                y: cell.y*20,
                fromCenter: false,
                width: 20,
                height: 20
            });
        } else {
            canvas.drawRect( {
                fillStyle: CombineColor(HashIdToColor(owner), HashIdToColor(attacker), Math.min(1, (currTime - cell['at']) / (cell['f'] - cell['at']))),
                strokeStyle: 'white',
                strokeWidth: 3,
                x: cell.x*20,
                y: cell.y*20,
                fromCenter: false,
                width: 20,
                height: 20
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
    return "#" + HexCombine(src.slice(1, 3), dest.slice(1, 3), per) + 
        HexCombine(src.slice(3, 5), dest.slice(3, 5), per) +
        HexCombine(src.slice(5), dest.slice(5), per)
}
HashIdToColor = function(id) {
    var colors = ['#DDDDDD', '#FF0000', '#00FF00', '#0000FF', '#00FFFF', 
        '#FF00FF', '#FFFF00', '#FF8800', '#FF0088', '#88FF00', '#00FF88', 
        '#8800FF', '#0088FF']
    if (id < colors.length) {
        return colors[id];
    } else {
        return "#000000";
    }
}
CreateGame = function() {
    $.get(hostUrl + "startgame", function(data) {
    })
}

JoinGame = function() {
    console.log($('#name').val())
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

Attack = function(x, y, token) {
    $.ajax( {
        url: hostUrl+"attack",
        method: "POST",
        dataType: "json",
        contentType: 'application/json;charset=UTF-8',
        data: JSON.stringify({"cellx":x, "celly":y, "token":token}),
        success: function(msg) {
            console.log(msg);
        },
    })
}

CanvasToXY = function(canvasX, canvasY) {
    return [Math.floor(canvasX/20), Math.floor(canvasY/20)]
}
$(function() {
    var canvas = $('#my_canvas');
    setInterval(GetGameInfo, 200);

    $('#create').click(function() {
        CreateGame();
    });

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

