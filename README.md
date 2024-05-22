## HOW TO USE

### 01. change these in gpu_usage.py
* TARGET_WEBHOOK_URL_REALTIME = 'https://your_webhook_url'
* TARGET_WEBHOOK_URL = 'https://your_webhook_url'
* GPU_REALTIME_USAGE_DIR = "./daily/"
* GPU_DAILY_USAGE_DIR = "./daily_avg/"

### 02. change this to current path add_cron.sh
* GPU_USAGE_FILE_PATH="/home/vln/90_query_gpu_public/gpu_usage.py"

### 03. install pandas
```pip install pandas```

### 04. run 
```bash add_cron.sh```
- this command will add cronjob in your server
- to check existing cronjobs, run ```crontab -e```
- if you have to run this command twice, delete previously added jobs. (otherwise cronjob will be run multiple times)

## Troubleshooting

### GPU usage info is empty
run ```python3 /home/vln/00_backup/98_gpu_util/gpu_usage.py test_gpu_info_parse```

expected output:
```
   id power_usage power_total memory_usage memory_total gpu_usage
0   0        104W        700W         0MiB     81559MiB        0%
1   1        105W        700W         0MiB     81559MiB        0%
2   2        101W        700W         0MiB     81559MiB        0%
3   3        103W        700W         0MiB     81559MiB        0%
4   4        100W        700W         0MiB     81559MiB        0%
5   5        103W        700W         0MiB     81559MiB        0%
6   6        104W        700W         0MiB     81559MiB        0%
7   7        102W        700W         0MiB     81559MiB        0%

```

if there's error look into `parse_gpu_info` function <strong>espacially if the regex pattern matches your nvidia-smi output</strong>