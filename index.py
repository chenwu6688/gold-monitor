# index.py —— 腾讯云 SCF 云函数入口（与 gold_monitor.py 同目录打包上传）
# 函数名: index，入口方法: index.main_handler
# 定时触发器: cron "*/10 * * * *"（每 10 分钟触发一次，对应代码里的高频层）
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gold_monitor as gm

# 云函数无状态：把穿越检测状态持久化到 /tmp。SCF 会复用 warm 实例，
# 实例复用期间状态有效，绝大多数个人监测场景足够。
# 如需跨实例 100% 可靠，把 STATE_PATH 改成对象存储 COS（见文末可选实现）。
gm.STATE_PATH = "/tmp/gold_state.json"


def main_handler(event, context):
    gm.load_state()
    cfg = gm.load_config()
    gm.run_once(cfg, save=True)
    return {"code": 0, "msg": "ok"}


# ---------------------------------------------------------------------------
# 可选：用腾讯云 COS 做跨实例状态持久化（100% 可靠，避免冷启动丢状态）
# 前置：SCF 里创建「层」安装 cos-python-sdk-v5，并配置环境变量
#       COS_BUCKET / COS_REGION / COS_SECRET_ID / COS_SECRET_KEY
# ---------------------------------------------------------------------------
# import json
# from qcloud_cos import CosConfig, CosS3Client
#
# class COSState:
#     def __init__(self, bucket, region, secret_id, secret_key, key="gold_state.json"):
#         self.key = key
#         self.bucket = bucket
#         self.client = CosS3Client(CosConfig(Region=region, SecretId=secret_id, SecretKey=secret_key))
#     def load(self):
#         try:
#             body = self.client.get_object(Bucket=self.bucket, Key=self.key)["Body"].get_raw_stream().read()
#             return json.loads(body)
#         except Exception:
#             return {}
#     def save(self, data):
#         self.client.put_object(Bucket=self.bucket, Key=self.key, Body=json.dumps(data))
#
# _cos = COSState(os.environ["COS_BUCKET"], os.environ["COS_REGION"],
#                 os.environ["COS_SECRET_ID"], os.environ["COS_SECRET_KEY"])
# gm.load_state = lambda p=None: gm.analyze_prev_sides.update(_cos.load())
# gm.save_state = lambda p=None: _cos.save(gm.analyze_prev_sides)
