#! /bin/sh
docker rm -f discordbot
docker build --tag discordbot .
docker run -d --restart always --network database -p 127.0.0.1:8094:80 --name discordbot --hostname DiscordBotProdDocker discordbot
