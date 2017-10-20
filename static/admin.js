//hostUrl = "http://localhost:8000/"
hostUrl = "https://colorfight.herokuapp.com/"
CreateGame = function(soft) {
    var aiOnly = false;
    if ($('#ai_only').find(":selected").text() == 'Yes') {
        aiOnly = true;
    }
    $.ajax( {
        url: hostUrl+"startgame",
        method: "POST",
        dataType: "json",
        contentType: 'application/json;charset=UTF-8',
        data: JSON.stringify({
            "admin_password":$('#admin_password').val(),
            "last_time":parseInt($('#last_time').val()),
            "ai_only":aiOnly,
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
