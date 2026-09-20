@echo off
title Deploy Laughing Pig Solar Monitor to Synology NAS
color 0A
echo ====================================================================
echo        Laughing Pig Solar Monitor - Synology NAS Deployer
echo ====================================================================
echo.
echo Target NAS: 192.168.42.184
echo NAS User:   lou
echo Repo:       https://github.com/lourusso/laughing-pig-solar-monitor.git (Public)
echo.
echo Connecting via SSH to deploy container using Git on the NAS...
echo Please enter your Synology password when prompted.
echo.

ssh -t lou@192.168.42.184 "sudo env PATH=/bin:/usr/bin:/sbin:/usr/sbin:/usr/local/bin:/var/packages/Git/target/bin sh -c 'mkdir -p /volume1/docker/laughing-pig-solar && cd /volume1/docker/laughing-pig-solar && if [ -d .git ]; then git pull; else git clone https://github.com/lourusso/laughing-pig-solar-monitor.git .; fi && (docker compose up -d --build || docker-compose up -d --build)'"

echo.
echo ====================================================================
echo If the build succeeded, your monitor is now running 24/7 on the NAS!
echo.
echo Access the live dashboard at:
echo    http://192.168.42.184:8050
echo ====================================================================
echo.
pause
