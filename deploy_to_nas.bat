@echo off
title Deploy Laughing Pig Solar Monitor to Synology NAS
color 0A
echo ====================================================================
echo        Laughing Pig Solar Monitor - Synology NAS Deployer
echo ====================================================================
echo.
echo Target NAS: 192.168.42.184
echo NAS User:   lou
echo Repo:       https://github.com/lourusso/laughing-pig-solar-monitor.git
echo.
echo Connecting via SSH...
echo Please enter your Synology password when prompted.
echo.

ssh -t lou@192.168.42.184 "sudo sh -c 'TARGET_DIR=\"/volume1/docker/laughing-pig-solar\"; if [ ! -d \"/volume1/docker\" ]; then for v in /volume*/docker; do if [ -d \"\$v\" ]; then TARGET_DIR=\"\$v/laughing-pig-solar\"; break; fi; done; fi; mkdir -p \"\$TARGET_DIR\" && cd \"\$TARGET_DIR\" && if [ -d .git ]; then git pull; else git clone https://github.com/lourusso/laughing-pig-solar-monitor.git .; fi && (docker compose up -d --build || docker-compose up -d --build)'"

echo.
echo ====================================================================
echo If the build succeeded, your monitor is now running 24/7 on the NAS!
echo.
echo Access the live dashboard at:
echo    http://192.168.42.184:8050
echo ====================================================================
echo.
pause
