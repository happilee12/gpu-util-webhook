# path to gpu_usage.py file 
GPU_USAGE_FILE_PATH="/PATH/TO/gpu_usage.py/FILE/gpu_usage.py"

# backup current cron
crontab -l > mycron
# 01. send realtime gpu usage to slack
new_cron="*/10 * * * * /usr/bin/python3 $GPU_USAGE_FILE_PATH send_realtime_usage"
echo "$new_cron" >> mycron
# 02. save gpu usage 
new_cron="* * * * * /usr/bin/python3 $GPU_USAGE_FILE_PATH save_realtime_usage"
echo "$new_cron" >> mycron
# 03. calculate daily gpu usage  and send to slack
new_cron="59 23 * * * /usr/bin/python3 $GPU_USAGE_FILE_PATH send_daily_usage"
echo "$new_cron" >> mycron
# 04. calculate gpu usage for this period and send to slack 
new_cron="0 0 * * * /usr/bin/python3 $GPU_USAGE_FILE_PATH send_period_average"
echo "$new_cron" >> mycron

crontab mycron

rm mycron