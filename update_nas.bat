@echo off
title Update Laughing Pig Solar Monitor on Synology NAS
color 0A
echo ====================================================================
echo        Updating Laughing Pig Solar Monitor on Synology NAS
echo ====================================================================
echo.
echo Connecting to NAS to pull latest updates from GitHub...
echo Please enter password for lou when prompted:
echo.

ssh -t lou@192.168.42.184 "sudo env PATH=/bin:/usr/bin:/sbin:/usr/sbin:/usr/local/bin:/var/packages/Git/target/bin sh -c 'cd /volume1/docker/laughing-pig-solar && git pull && if [ -x /usr/local/bin/docker ]; then /usr/local/bin/docker compose up -d --build; elif [ -x /var/packages/ContainerManager/target/usr/bin/docker ]; then /var/packages/ContainerManager/target/usr/bin/docker compose up -d --build; fi'"

echo.
echo ====================================================================
echo Update pulled on the NAS!
echo.
echo If the container did not auto-restart, go to Container Manager:
echo    1. Click 'Project' on the left menu
echo    2. Click 'laughing-pig-solar' -^> Action -^> 'Build' (or 'Restart')
echo.
echo Dashboard URL: http://192.168.42.184:8050
echo ====================================================================
echo.
pause
