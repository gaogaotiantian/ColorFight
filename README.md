# ColorFight!

ColorFight is a game where you try to occupy as many cells as possible on the map.

This is the server code.

## Website for the game

[https://colorfight.herokuapp.com/](https://colorfight.herokuapp.com/)

## Python API and example AI

[https://github.com/gaogaotiantian/colorfightai](https://github.com/gaogaotiantian/colorfightai)

## Admin guide

The admin for the game is at [https://colorfight.herokuapp.com/admin.html](https://colorfight.herokuapp.com/admin.html)

You need to input the admin password to restart the game. Normally just leave it blank.
This is a privilege information for the server owner. 

You can set:
    
+ Game Time, the total game time in seconds.

+ Join Time, the time when users are allowed to join after the game starts, in seco      nds.

+ Start Delay Time, so you have a fancy count down for the offical game, in seconds

+ AI Only, whether manual join is allowed in the game

You should always use *Restart Game* rather than *Create Game* except for the very 
first time after you create the server.

## Installation guide

If you want to fork and build your own colorfight server on heroku, here's what
you need to do.

+ Get a heroku account. Bind a credit card to verify the account.

+ Create an app in your heroku account, name it anything(my-colorfight for example).

+ Fork this repo, clone to your local machine.

+ Link the repo to the heroku app with ```heroku remote:git -a my-colorfight```

+ Create the addons. You need Heroku Postgres ```heroku addons:create heroku-postgresql:hobby-dev``` and Redis Cloud ```heroku addons:create rediscloud:30```.(These are
both free addons for a verified account)

+ Run ```heroku config``` to verify that you have two environment variables for heroku
```DATABASE_URL``` and ```REDISCLOUD_URL```.

+ You need some extra settings to make it work.

    + ```heroku config:set ADMIN_PASSWORD=``` sets the admin password to restart the ga      me. You should probably set this for an official game otherwise anyone has the
      to restart your game

    + ```heroku config:set GAME_FEATURE='{"base":true, "gold":true, "energy":true, "boost":true, "blast":true, "multiattack":true}'``` 
      sets the feature in the game.
      This will enable you to change the features in enviroment variable instead of
      changing the code.

    + (optional) ```heroku config:set GAME_REFRESH_INTERVAL=``` sets the interval
      for game refresh. The smaller this value is, the faster the game will calculate
      everything, thus slower your server. The default value is 0.1.

+ You need to change the server address in some js files to point it to your own server.

    + ```static/color.js```

    + ```static/admin.js```

+ Push the repo to heroku ```git push heroku master``` (Notice, if you are not pushing
the master branch to heroku, heroku forces you to explicitly label it. ```git push 
heroku my-branch:master)

+ Go to your website's admin page, do a *Create Game*, this may takes several seconds.

+ Enjoy the game.
