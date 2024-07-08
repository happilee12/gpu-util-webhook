import os
from collections import defaultdict
from datetime import datetime
import pandas as pd
import subprocess
import time
import json
import requests
import sys
import re
from my_url import GPU_NAME, SLACK_WEBHOOK_URL, SLACK_WEBHOOK_URL_REALTIME, GPU_DAILY_USAGE_DIR, GPU_REALTIME_USAGE_DIR


def send_teams_message(content, webhook_url):
    message = {
        "type": "message",
        "attachments": [
            {
                "contentType": "application/vnd.microsoft.card.adaptive",
                "content": content
            } 
        ]
    }

    headers = {'Content-Type': 'application/json'}
    response = requests.post(webhook_url, data=json.dumps(message), headers=headers)
    if response.status_code == 200:
        print("Message sent successfully to Microsoft Teams.")
    else:
        print("Error sending message to Microsoft Teams:", response.status_code)
        print("Error sending message to Microsoft Teams:", response.text)

def send_slack_message(message, webhook_url):
    try:
        headers = {'Content-type': 'application/json'}
        response = requests.post(webhook_url, headers=headers, data=json.dumps(message))
        response.raise_for_status()
        print("Message sent successfully to Slack via webhook")
        return True
    except requests.exceptions.HTTPError as errh:
        print(f"HTTP Error: {errh}")
    except requests.exceptions.ConnectionError as errc:
        print(f"Error Connecting: {errc}")
    except requests.exceptions.Timeout as errt:
        print(f"Timeout Error: {errt}")
    except requests.exceptions.RequestException as err:
        print(f"Something went wrong: {err}")
    return False

def create_teams_table_card(df, title):
    # 테이블 데이터 생성
    rows = []

    rows.append({"type": "TableRow", "cells": [{"type": "TableCell", "items": [
                                        {
                                            "type": "TextBlock",
                                            "text": col,
                                            "wrap": True,
                                        }
                                    ]} for col in df.columns]})
    for index, row in df.iterrows():
        cells = [{"type": "TableCell", "items": [
                                        {
                                            "type": "TextBlock",
                                            "text": str(row[col]),
                                            "wrap": True,
                                        }
                                    ]} for col in df.columns]
        rows.append({"type": "TableRow", "cells": cells})
    print(rows)

    # Adaptive Card 구성

    adaptive_card_body = [
            {"type": "TextBlock", "text": title, "size": "Medium", "weight": "Bolder", "wrap": True},
            {
                    "type": "Table",
                    "gridStyle": "accent",
                    "firstRowAsHeaders": True,
                    "columns": [
                        {
                            "width": 1
                        },
                        {
                            "width": 1
                        },
                        {
                            "width": 1
                        },
                        {
                            "width": 1
                        },
                        {
                            "width": 1
                        },
                        {
                            "width": 1
                        }

                    ],
                    "rows": rows
            }
        ]

    contents = {
        "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
        "type": "AdaptiveCard",
        "version": "1.0",
        "msteams": {
            "width": "Full"
        },
        "body": 
        # original_message  + 
        adaptive_card_body
    }
    
    return contents

def create_slack_table_card(df, title):
    rows = []
    # Data rows
    for index, row in df.iterrows():
        # row_cells = [{"type": "plain_text", "text": str(row[col]), "emoji": True} for col in df.columns]
        rows.append({"type": "section", "text": {"type": "plain_text", "text": " | ".join(str(row[col]) for col in df.columns)}})

    # Adaptive Card structure
    adaptive_card_body = {
        "type": "section",
        "text": {
            "type": "mrkdwn",
            "text": f"*{title}*"
        }
    }

    contents = {
        "blocks": [
            adaptive_card_body,
            {
                "type": "divider"
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": " | ".join(df.columns)
                }
            },
            *rows
        ]
    }

    return contents

def run_nvidia_smi():
    result = subprocess.run(['nvidia-smi'], capture_output=True, text=True)
    output = result.stdout
    return output

'''nvidia-smi output에서 gpu사용량 관련 행만 파싱'''
def parse_gpu_info(output):
    gpu_info = {}
    lines = output.split('\n')
    gpu_count = 0
    pattern = r"^\|\s+(\d+)\s+NVIDIA\s+(\w+)\s+(\d+)GB\s+(\w+)\s+Off\s+\|\s+(\S+)\s+Off\s+\|\s+(\d+)\s+\|"

    output = []
    for ln, line in enumerate(lines):
        if re.match(pattern, line):
            output.append(lines[ln+1].split())
    return output

def get_gpu_info(nvidia_smi_result):
    try:
        gpu_info = parse_gpu_info(nvidia_smi_result)
        gpu_df = pd.DataFrame(columns=['id', 'power_usage', 'power_total', 'memory_usage', 'memory_total', 'gpu_usage'])
        for idx, gpu in enumerate(gpu_info):
            gpu_df.loc[len(gpu_df)] = [idx, gpu[4], gpu[6], gpu[8], gpu[10], gpu[12] ]
        return gpu_df
    except Exception as e:
        print("Error while getting GPU info:", e)
        return None

def get_gpu_info_int(nvidia_smi_result):
    try:
        gpu_info = parse_gpu_info(nvidia_smi_result)
        gpu_df = pd.DataFrame(columns=['id', 'power_usage', 'power_total', 'memory_usage', 'memory_total', 'gpu_usage'])
        for idx, gpu in enumerate(gpu_info):
            gpu_df.loc[len(gpu_df)] = [idx, gpu[4][:-1], gpu[6][:-1], gpu[8][:-3], gpu[10][:-3], gpu[12][:-1] ]
        return gpu_df
    except Exception as e:
        print("Error while getting GPU info:", e)
        return None

def save_to_daily_usage(df):
    date = datetime.now().strftime('%Y%m%d')
    month = datetime.now().strftime('%m')
    period = get_period(month)
    output_file = GPU_DAILY_USAGE_DIR+"%d/%s.csv"%(period, date)
    create_directory(output_file)
    df.to_csv(output_file, index=False)

def save_to_realtime_usage(df):
# def record_gpu_usage(df):
    date = datetime.now().strftime('%Y%m%d')
    dir_name=GPU_REALTIME_USAGE_DIR+date
    year = datetime.now().strftime('%Y')
    month = datetime.now().strftime('%m')
    period = get_period(month)
    date_time = datetime.now().strftime('%Y%m%d_%H:%M:%S')
    file_path = '%s/%s.csv'%(dir_name, date_time)
    print(file_path)
    create_directory(file_path)
    df.to_csv(file_path, index=False)


def create_directory(filename):
    abs_path = os.path.abspath(filename)
    folder_path = os.path.dirname(abs_path)
    if not os.path.exists(folder_path):
        os.makedirs(folder_path)

def calculate_average_gpu_usage(directory):
    dfs = []
    # 디렉토리 내의 모든 파일에 대해 반복
    for filename in os.listdir(directory):
        # print(filename)
        filepath = os.path.join(directory, filename)
        if os.path.isfile(filepath) and filename.endswith('.csv'):
            # CSV 파일에서 데이터프레임으로 읽어오기
            df = pd.read_csv(filepath)
            dfs.append(df)
            # print(df)

    total_df = pd.DataFrame()
    for df in dfs:
        if total_df.empty:
            total_df = df
        else:
            total_df += df
    print(total_df, len(dfs))
    average_df = total_df / len(dfs)

    return average_df

def get_period(month):
    if month == '01' or month == '02' or month == '03':
        return 1 
    if month == '04' or month == '05' or month == '06':
        return 2    
    if month == '07' or month == '08' or month == '09':
        return 3 
    if month == '10' or month == '11' or month == '12':
        return 4


def get_daily_usage():
    # Path to the file containing GPU usage data
    date = datetime.now().strftime('%Y%m%d')
    directory_path = GPU_REALTIME_USAGE_DIR+date
    daily_avg = calculate_average_gpu_usage(directory_path)
    return daily_avg

def construct_message(title, gpu_usage_list):
    print("gpu usage list")
    print(gpu_usage_list)
    average_usage_per_gpu = [{
                    "type": "TextBlock",
                    "text": "GPU : %d  - usage: %d %%"%(idx, gpu_usage)
                } for idx, gpu_usage in enumerate(gpu_usage_list)]

    content = {
        "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
        "type": "AdaptiveCard",
        "version": "1.0",
        "body": [
            {
            "type": "TextBlock",
            "text": '%s 사용률'%(title),
            "size": "large"
            }
        ] + average_usage_per_gpu + [
            {
            "type": "TextBlock",
            "text": '평균 사용률 : %d %%'%(sum(gpu_usage_list) / len(gpu_usage_list)),
            "weight": "bolder"
            }
        ]
    }

    return content


def construct_slack_message(title, gpu_usage_list):
    blocks = []

    # Title block
    blocks.append({
        "type": "section",
        "text": {
            "type": "mrkdwn",
            "text": f"*{title} 사용률*",
        }
    })

    # GPU usage details
    for idx, gpu_usage in enumerate(gpu_usage_list):
        blocks.append({
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"GPU {idx}: {gpu_usage}%"
            }
        })

    # Average usage block
    average_usage = sum(gpu_usage_list) / len(gpu_usage_list)
    blocks.append({
        "type": "section",
        "text": {
            "type": "mrkdwn",
            "text": f"*평균 사용률: {average_usage:.2f}%*",
        }
    })

    message = {
        "blocks": blocks
    }

    return message

def get_daily_usage():
    # Path to the file containing GPU usage data
    date = datetime.now().strftime('%Y%m%d')
    directory_path = GPU_REALTIME_USAGE_DIR+date
    daily_avg = calculate_average_gpu_usage(directory_path)
    return daily_avg

def test_gpu_info_parse():
    nvidia_smi_result = run_nvidia_smi()
    gpu_df = get_gpu_info(nvidia_smi_result)
    print(gpu_df)

def send_realtime_usage():
    nvidia_smi_result = run_nvidia_smi()
    gpu_df = get_gpu_info(nvidia_smi_result)
    # card_content = create_teams_table_card(gpu_df, 'TITLE')
    # send_teams_message(card_content, TARGET_WEBHOOK_URL_REALTIME)
    slack_content = create_slack_table_card(gpu_df, GPU_NAME)
    send_slack_message(slack_content, SLACK_WEBHOOK_URL_REALTIME)

def save_realtime_usage():
    nvidia_smi_result = run_nvidia_smi()
    gpu_df = get_gpu_info_int(nvidia_smi_result)
    save_to_realtime_usage(gpu_df)

def send_daily_usage():
    daily_avg = get_daily_usage()
    save_to_daily_usage(daily_avg)
    gpu_usage_list = daily_avg['gpu_usage'].tolist()
    date = datetime.now().strftime('%Y.%m.%d')
    # content = construct_message(date, gpu_usage_list)
    # send_teams_message(content, TARGET_WEBHOOK_URL)
    slack_content = construct_slack_message("[%s] %s 일일사용률"%(GPU_NAME, date), gpu_usage_list)
    send_slack_message(slack_content, SLACK_WEBHOOK_URL)

def send_period_average():
    month = datetime.now().strftime('%m')
    period = get_period(month)
    directory=GPU_DAILY_USAGE_DIR+str(period)+'/'
    average_usage = calculate_average_gpu_usage(directory)
    gpu_usage_list = average_usage['gpu_usage'].tolist()
    month = datetime.now().strftime('%m')
    period = get_period(month)
    # content = construct_message(GPU_NAME+" "+str(period)+"분기", gpu_usage_list)
    # send_teams_message(content, TARGET_WEBHOOK_URL)
    slack_content = construct_slack_message("[%s] %s분기사용률"%(GPU_NAME, str(period)), gpu_usage_list)
    send_slack_message(slack_content, SLACK_WEBHOOK_URL)

if __name__ == "__main__":
    if len(sys.argv) == 1:
        print("지원하지 않는 함수입니다.")
    if sys.argv[1] == 'send_realtime_usage':
        send_realtime_usage()
    elif sys.argv[1] == 'save_realtime_usage':
        save_realtime_usage()
    elif sys.argv[1] == 'send_daily_usage':
        send_daily_usage()
    elif sys.argv[1] == 'send_period_average': 
        send_period_average()
    elif sys.argv[1] == 'test_gpu_info_parse': 
        test_gpu_info_parse()
    else:
        print("지원하지 않는 함수입니다.")

