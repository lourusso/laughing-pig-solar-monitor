@echo off
title Deploy Laughing Pig Solar Monitor to Synology NAS
color 0A
echo ====================================================================
echo        Laughing Pig Solar Monitor - Synology NAS Deployer
echo ====================================================================
echo.
echo Target NAS: 192.168.42.184
echo NAS User:   lou
echo.
echo [1/3] Packaging project files (47 KB)...
tar -czf deploy.tar.gz Dockerfile docker-compose.yml requirements.txt config src

echo.
echo [2/3] Uploading package to Synology NAS...
echo (Enter password for lou when prompted)
scp deploy.tar.gz lou@192.168.42.184:/tmp/deploy.tar.gz
del deploy.tar.gz

if errorlevel 1 (
    echo.
    echo [ERROR] Failed to upload files to NAS. Please check password or network.
    pause
    exit /b 1
)

echo.
echo [3/3] Extracting files and starting Docker container on NAS...
echo (Enter password for sudo when prompted)
ssh -t lou@192.168.42.184 "sudo sh -c 'TARGET_DIR=\"/volume1/docker/laughing-pig-solar\"; if [ ! -d \"/volume1/docker\" ]; then for v in /volume*/docker; do if [ -d \"\$v\" ]; then TARGET_DIR=\"\$v/laughing-pig-solar\"; break; fi; done; fi; mkdir -p \"\$TARGET_DIR\" && tar -xzf /tmp/deploy.tar.gz -C \"\$TARGET_DIR/\" && rm -f /tmp/deploy.tar.gz && cd \"\$TARGET_DIR\" && (docker compose up -d --build || docker-compose up -d --build)'"

echo.
echo ====================================================================
echo Deployment script finished!
echo.
echo If the build succeeded above, access the live dashboard at:
echo    http://192.168.42.184:8050
echo ====================================================================
echo.
pause
