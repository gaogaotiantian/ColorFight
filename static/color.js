hostUrl = "http://localhost:8000/"
GetGameInfo = function() {
    $.get(hostUrl + "getgameinfo", 
        function(data) {
            var gameInfo = data;
            DrawGame($('#my_canvas'), gameInfo['info']['width'], gameInfo['info']['height'], gameInfo['cells']);
        }
    );
}
DrawGame = function(canvas, width, height, cells) {
    for (idx in cells) {
        cell = cells[idx];
        canvas.drawRect( {
            fillStyle: HashIdToColor(cell['o']),
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
HashIdToColor = function(id) {
    if (id == 0) {
        return "#DDDDDD";
    } else if (id == 1) {
        return "red";
    } else if (id == 2) {
        return "blue";
    } else if (id == 3) { 
        return "green";
    }
    return "black";
}
CreateGame = function() {
    $.get(hostUrl + "startgame", function(data) {
    })
}

JoinGame = function() {
    $.post(hostUrl + "joingame", {"name":"gaotian"}, function(data) {
        console.log(data);
    })
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
})

