## HOW TO USE

### change these in gpu_usage.py
TARGET_WEBHOOK_URL_REALTIME = 'https://your_webhook_url'
TARGET_WEBHOOK_URL = 'https://your_webhook_url'
GPU_REALTIME_USAGE_DIR = "./daily/"
GPU_DAILY_USAGE_DIR = "./daily_avg/"

### change this to current path add_cron.sh
GPU_USAGE_FILE_PATH="/home/vln/90_query_gpu_public/gpu_usage.py"

### run 
```bash add_cron.sh```
- this command will add cronjob in your server
- to check existing cronjobs, run ```crontab -e```
- if you have to run this command twice, delete previously added jobs. (otherwise cronjob will be run multiple times)