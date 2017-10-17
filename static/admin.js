hostUrl = "https://colorfight.herokuapp.com/"
//hostUrl = "http://localhost:8000/"
CreateGame = function(soft) {
    $.ajax( {
        url: hostUrl+"startgame",
        method: "POST",
        dataType: "json",
        contentType: 'application/json;charset=UTF-8',
        data: JSON.stringify({
            "admin_password":$('#admin_password').val(),
            "last_time":parseInt($('#last_time').val()),
            "soft":soft
        }),
        success: function(msg) {
            console.log(msg)
            $('#create_result').text(msg['msg']);
        },
    })
}
$(function() {
    $('#create').click(function() {
        CreateGame(false);
    });
    $('#restart').click(function() {
        CreateGame(true);
    })
})
